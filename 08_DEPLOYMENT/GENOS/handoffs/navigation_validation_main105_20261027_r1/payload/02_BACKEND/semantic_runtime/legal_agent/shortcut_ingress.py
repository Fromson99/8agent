"""Durable ingress around every v6 route, including greetings and catalogue reads."""
import json
from pathlib import Path
import uuid
from .shortcut_repository import ShortcutRepository
from .corrected_memory import encoded


def capture(pipeline, question, documents, use_llm, scope, options, team_id, lease):
    options=dict(options or {})
    if 'runtime' not in options:
        from lawrag.platform.workspace import load_layout
        options['runtime']=load_layout(pipeline.contracts.root).path('runtime')/'semantic'
    from .shortcut_store import selected_store
    from ..ad_store import features
    from ..state_sqlite import readonly
    selected=selected_store(options['runtime'])
    if selected.is_file():
        db=readonly(selected)
        try:enabled=features(db,team_id or 'request')['shortcut']
        finally:db.close()
        if not enabled:
            options['_shortcut_ingress']=True
            options['_shortcut_disabled']=True
            return pipeline._run(question,documents,use_llm,scope,execution_context=options,team_id=team_id,admission_lease=lease)
    body=options.get('case_body')
    if body is None:
        plan=pipeline.plan(question,documents,scope,team_id=team_id)
        body={'question':question,'document_ids':plan['scope']['document_version_ids'],
              'session_id':'ephemeral:'+uuid.uuid4().hex,'request_id':uuid.uuid4().hex,
              'public_question':options.get('external_public_question') is True}
    principal=options.get('principal') or {'user_id':'ephemeral:'+body['session_id'],
        'team_id':team_id or 'request','document_ids':body['document_ids'],'authenticated':False}
    from ..team_scope import prepared_catalogue
    if not set(body['document_ids']) <= prepared_catalogue(pipeline.store)['ids']:
        raise ValueError('request includes unavailable or excluded document versions')
    selection = getattr(getattr(pipeline.store, 'selection', None), 'fingerprint', None)
    options.update(case_body=body,principal=principal,_shortcut_ingress=True)
    from .shortcut_store import selected_store
    repo=ShortcutRepository(selected_store(options['runtime']))
    try:
        intake=repo.intake(body,principal)
        noncase=not use_llm
        if noncase and intake['status']=='COMPLETED' and intake['response']:
            saved=json.loads(intake['response'])
            if (saved.get('generation')==pipeline.store.manifest['store_sha256'] and
                    saved.get('search_selection')==selection):
                # System results contain no adopted legal judgment. Document ACL is
                # still checked on every replay, and a new source generation misses.
                if set(body['document_ids'])<=set(principal['document_ids']):return saved['envelope']
        try:
            value=pipeline._run(question,documents,use_llm,scope,execution_context=options,
                team_id=team_id,admission_lease=lease)
        except BaseException:
            repo.db.execute("UPDATE sw_intake SET status='FAILED' WHERE id=? AND status<>'COMPLETED'",(intake['id'],))
            raise
        if noncase:
            with repo.transaction():
                case=repo.connect(intake['id'],principal)
                repo.advance(case['id'],principal,case['revision'],'SYSTEM_RESPONSE_ACCEPTED',
                    {'intake_id':intake['id'],'run_id':value.get('run_id'),'legal_judgment':False},session=body['session_id'])
                value={**value,'intake_id':intake['id'],'investigation_id':case['id']}
                repo.db.execute("UPDATE sw_intake SET status='COMPLETED',response=? WHERE id=?",(
                    encoded({'envelope':value,'generation':pipeline.store.manifest['store_sha256'],
                             'search_selection':selection}),intake['id']))
        return value
    finally:repo.close()
