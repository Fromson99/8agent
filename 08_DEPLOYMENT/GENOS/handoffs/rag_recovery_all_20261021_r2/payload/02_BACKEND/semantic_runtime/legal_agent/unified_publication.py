"""A native response may publish only an accepted, still-current case commit."""
import json
from pathlib import Path
import sqlite3
from ..contracts import digest, sha
from .errors import ContractError
from .investigation_contracts import claim_evidence


def _commit(repo):
    row=repo.db.execute('SELECT * FROM case_commit WHERE singleton=1').fetchone()
    if row is None:raise ContractError('unified publication requires case commit guard')
    c=dict(row)
    if digest({k:c[k] for k in c if k!='payload_hash'})!=c['payload_hash']:raise ContractError('case commit hash changed')
    return c


def validate_saved(repo,result):
    c=_commit(repo)
    meta=result.get('assembly',{}).get('term_agent',{})
    case=meta.get('case',{})
    if (case.get('question_id'),case.get('revision'),case.get('route_id'))!=(c['question_id'],c['revision'],c['route_id']):
        raise ContractError('response case binding mismatch')
    evidence=repo.evidence()
    by_source={}
    for e in evidence:by_source.setdefault(e['source_id'],[]).append(e)
    for claim in result['answer']['claims']:
        if not set(claim['source_ids'])<=set(by_source):raise ContractError('answer references unread sources')
    if c['question_id'] is None:
        if result['answer']['claims'] or case.get('judgment_refs'):raise ContractError('clarification has no accepted legal judgment')
        return
    path=Path(c['case_db'])
    # The native journal and its case authority share the same runtime root.
    runtime=repo.path.parents[4]
    from .shortcut_store import selected_store
    if path.resolve() not in {(runtime/'case-memory'/'cases-v3.sqlite').resolve(),selected_store(runtime).resolve()}:raise ContractError('case authority path mismatch')
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        g=db.execute('SELECT * FROM goal WHERE id=? AND session=?',(c['question_id'],c['session_id'])).fetchone()
        principal=json.loads(c['principal_json'])
        owner=db.execute('SELECT owner,team FROM session WHERE id=?',(c['session_id'],)).fetchone()
        if not owner or tuple(owner)!=(principal['user_id'],principal['team_id']):raise ContractError('case principal changed')
        if not g or g['revision']!=c['revision'] or g['status']!='READY':raise ContractError('late or incomplete case publication')
        state=json.loads(g['state'])
        if not set(state['document_ids'])<=set(principal['document_ids']):raise ContractError('case documents inaccessible')
        route=db.execute("SELECT * FROM route WHERE id=? AND goal=? AND revision=? AND status='ACTIVE'",
            (c['route_id'],g['id'],g['revision'])).fetchone()
        if not route:raise ContractError('case route no longer current')
        payload=json.loads(route['payload'])
        if digest(payload)!=route['hash'] or payload['judgment_refs']!=case.get('judgment_refs'):raise ContractError('accepted judgment refs changed')
        for stage,ref in payload['judgment_refs'].items():
            node=db.execute('SELECT n.*,r.ref FROM node n JOIN judgment_ref r ON r.node=n.id WHERE n.id=?',
                (payload['nodes'][stage],)).fetchone()
            if (not node or node['goal']!=g['id'] or node['stage']!=stage or json.loads(node['ref'])!=ref
                    or digest(json.loads(node['payload']))!=ref['payload_hash'] or node['hash']!=ref['payload_hash']):
                raise ContractError('case judgment lineage changed')
            if ref['run_id']==repo.run()['run_id']:
                _ref(repo.db,ref,stage)
            else:
                journals=list(repo.path.parents[2].glob('*/'+ref['run_id']+'/journal.sqlite'))
                if len(journals)!=1:raise ContractError('origin judgment journal missing')
                with sqlite3.connect('file:'+str(journals[0])+'?mode=ro',uri=True) as native:
                    _ref(native,ref,stage)
        if meta.get('judgment_view'):
            from .judgment_view import build
            parts={stage:{'payload':json.loads(db.execute('SELECT payload FROM node WHERE id=?',
                   (node,)).fetchone()[0])} for stage,node in payload['nodes'].items()}
            accepted=[json.loads(row[0]) for row in repo.db.execute(
                "SELECT payload_json FROM event WHERE kind='CASE_JUDGMENT_ACCEPTED' ORDER BY seq")]
            executed=[event['stage'] for event in accepted if event.get('origin') is None]
            scope=set(state['document_ids'])
            context=repo.db.execute("SELECT payload_json FROM event WHERE kind='CASE_EXECUTION_CONTEXT' ORDER BY seq DESC LIMIT 1").fetchone()
            if context:scope &= set(json.loads(context[0])['documents'])
            expected_view=build(parts,case,state=state,run_id=repo.run()['run_id'],
                                allowed_documents=scope,executed=executed)
            if meta['judgment_view']!=expected_view:
                raise ContractError('published judgment display differs from current route')
        read=json.loads(db.execute('SELECT payload FROM node WHERE id=?',(payload['nodes']['READ'],)).fetchone()[0])
        selection=json.loads(db.execute('SELECT payload FROM node WHERE id=?',(payload['nodes']['SELECT'],)).fetchone()[0])
        originals={x['source_id']:x for x in selection.get('selected_originals',read['originals'])}
        assessment=json.loads(db.execute('SELECT payload FROM node WHERE id=?',(payload['nodes']['ASSESS'],)).fetchone()[0])
        if assessment.get('completion_contract'):
            from .completion_contracts import verify_composition, verify_span_claim
            composition=json.loads(db.execute('SELECT payload FROM node WHERE id=?',(payload['nodes']['COMPOSE'],)).fetchone()[0])
            verify_composition(assessment,composition)
            expected_text=composition['text']
            presentation=meta.get('answer_presentation')
            if presentation:
                from .memory_methods import history_answer
                if presentation.get('method_id')!='HISTORY_EXPLAIN':raise ContractError('unsupported history presentation')
                events=[];ordinal=0
                for row in db.execute('SELECT * FROM event WHERE goal=? AND after_state IS NOT NULL ORDER BY id',(g['id'],)):
                    event=dict(row);event['before']=json.loads(event.pop('before_state')) if event['before_state'] else None
                    event['after']=json.loads(event.pop('after_state'));event['command']=json.loads(event['command'])
                    if event['kind']=='CORRECT':ordinal+=1;event['correction_ordinal']=ordinal
                    events.append(event)
                expected,history=history_answer(events,composition)
                if presentation!={'method_id':'HISTORY_EXPLAIN','history_hash':digest(history)}:
                    raise ContractError('history events differ from accepted current case')
                expected_text=expected['text']
            if result['answer']['text']!=expected_text or result['answer']['unresolved']!=[{'reason':v} for v in assessment['limitations']]:
                raise ContractError('public answer differs from verified rendering')
            for claim in assessment['claims']:verify_span_claim(claim,list(originals.values()))
            if assessment.get('source_excerpt_reply'):
                from .completion_contracts import verify_source_excerpt_reply
                verify_source_excerpt_reply(assessment,
                    [s for s in originals.values() if s['source_id'] in selection['final_ids']])
        selected=set(json.loads(db.execute('SELECT payload FROM node WHERE id=?',(payload['nodes']['SELECT'],)).fetchone()[0])['final_ids'])
        for claim in [e for c in assessment['claims'] for e in claim_evidence(c)]:
            if claim['source_id'] not in selected or claim['source_id'] not in originals or not claim['quote'].strip() or claim['quote'] not in originals[claim['source_id']]['text']:
                raise ContractError('unsupported current case claim')
        expected=[{'id':'claim:'+str(i+1),'text':x['text'],'source_ids':list(dict.fromkeys(e['source_id'] for e in claim_evidence(x)))} for i,x in enumerate(assessment['claims'])]
        if result['answer']['claims']!=expected:raise ContractError('published claims differ from current judgment')


def _ref(db,ref,stage):
    row=db.execute('SELECT payload_json,payload_hash FROM entity_version WHERE kind=? AND entity_id=? AND version=?',
        (ref['kind'],ref['entity_id'],ref['version'])).fetchone()
    if not row or row[1]!=ref['payload_hash'] or digest(json.loads(row[0]))!=row[1]:raise ContractError('native judgment ref changed')
    offered=db.execute('SELECT stage,offer_json,choice_json FROM domain_choice WHERE id=?',(ref['choice_id'],)).fetchone()
    if not offered or offered[0]!=stage:raise ContractError('judgment has no pre-execution domain choice')
    offer,choice=json.loads(offered[1]),json.loads(offered[2])
    if (choice['method_id']!=offer['method_id'] or choice['path'] not in offer['paths'] or
            not set(choice['concept_ids'])<={c['id'] for c in offer['concepts']} or
            not set(choice['relation_ids'])<={r['id'] for r in offer['relations']}):raise ContractError('unoffered domain selection')
    if stage=='ASSESS':
        assessment = json.loads(row[0])
        references = [e for c in assessment['claims'] for e in claim_evidence(c)]
        references += assessment.get('source_excerpt_reply', {}).get('sources', [])
        for claim in references:
            presented=db.execute('''SELECT 1 FROM evidence_dependency d JOIN evidence_unit e USING(evidence_id)
              JOIN presentation p USING(evidence_id) JOIN model_attempt a USING(view_id)
              WHERE d.kind=? AND d.entity_id=? AND d.version=? AND e.source_id=? AND a.status='SUCCEEDED' LIMIT 1''',
                (ref['kind'],ref['entity_id'],ref['version'],claim['source_id'])).fetchone()
            if not presented:raise ContractError('judgment source was not delivered in a successful model call')


def validate_current(repo,result,store,*,allowed_documents=None):
    validate_saved(repo,result)
    from ..storage import verify_store_binding
    oracle=getattr(store,'is_oracle_query',False)
    if oracle: store.check_unchanged()
    current=store.manifest if oracle else json.loads((store.path/'manifest.json').read_text())
    for key in ('generation_id','store_sha256','export_allowed'):
        if current[key]!=repo.binding[key]:raise ContractError('unified source generation changed')
    try:
        if not oracle: verify_store_binding(store.path/'store.sqlite',current['store_sha256'])
    except ValueError as exc:raise ContractError('unified source store changed') from exc
    allowed=set(current['scope']['document_version_ids'])
    if oracle: allowed &= store.oracle_request.sources.allowed
    c=_commit(repo);principal=json.loads(c['principal_json'])
    if principal.get('team_scope_bound') is True:
        from ..team_scope import select_documents
        allowed &= set(select_documents(store,principal['team_id']))
    allowed &= set(principal['document_ids'])
    if allowed_documents is not None:allowed &= set(allowed_documents)
    if set(repo.binding['scope']['document_version_ids'])-allowed:raise ContractError('unified request authorization changed')
    if repo.binding.get('catalogue_binding'):
        catalog=repo.binding['catalogue_binding']
        if sha(Path(repo.binding['contract_root'])/catalog['path'])!=catalog['sha256']:raise ContractError('domain catalogue changed before publication')
    if Path(c['case_db']).name=='cases-v4.sqlite':
        from .shortcut_repository import ShortcutRepository
        authority=ShortcutRepository(Path(c['case_db']))
        try:
            fresh={**principal,'document_ids':sorted(allowed)}
            for row in repo.db.execute("SELECT payload_json FROM event WHERE kind='WIKI_JUDGMENT_USED'"):
                use=json.loads(row[0]);value=authority.current(use['unit_id'],use['revision'],fresh)
                if value['hash']!=use['hash']:raise ContractError('wiki judgment changed before publication')
        finally:authority.close()
    from .repository import text_hash
    for e in repo.evidence():
        if e['document_id'] not in allowed:raise ContractError('case evidence outside current authorization')
        for span in e['spans']:
            raw=store.source(e['document_id'],span['block_id'])
            if (raw['source_artifact_sha256']!=e['source_artifact_hash'] or text_hash(raw['text'])!=span['block_hash'] or
                    raw['text'][span['start_cp']:span['end_cp']]!=span['text']):raise ContractError('current case evidence changed')


def recover_guard(repo,value,source_guard):
    if source_guard is None:raise ContractError('unified recovery requires current source authorization')
    validate_saved(repo,value)
    source_guard(repo,value)
