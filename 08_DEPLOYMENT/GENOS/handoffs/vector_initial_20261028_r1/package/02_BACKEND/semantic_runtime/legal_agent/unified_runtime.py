"""One Pipeline/coordinator entry for questions, corrections and confirmed experience."""
import json
from .investigation_contracts import claim_evidence
from pathlib import Path
from .case_repository import CaseRepository
from .knowledge_repository import KnowledgeRepository
from .domain_control import DomainCatalogue
from .memory_binding import RuntimeModel
from .unified_rag import UnifiedRag,UnifiedExecution
from .corrected_memory import Conflict, MemoryError, digest, encoded


def open_cases(pipeline,runtime,body,principal,*,lease=None,run_id=None,release=None):
    catalogue=DomainCatalogue.load(pipeline.contracts.root,pipeline.term_agent.config['legal_agent']['catalogue'])
    model=RuntimeModel(pipeline,runtime,body,principal,admission_lease=lease,run_id=run_id,release=release)
    flags=dict(pipeline.contracts.pipeline.get('shortcut_v4',{}).get('features',{}))
    from .shortcut_store import selected_store
    from ..ad_store import features
    from ..state_sqlite import readonly
    shortcut_disabled=False
    selected=selected_store(runtime)
    if selected.is_file():
        db=readonly(selected)
        try:state=features(db,principal['team_id'])
        finally:db.close()
        if not state['shortcut']:flags['capture']=False;shortcut_disabled=True
        if not state['wiki']:
            for name in ('hint','procedure','judgment','core_evidence_route','bounded_recall'):flags[name]=False
    from .source_handoff import enabled as source_mode
    if source_mode():
        flags['capture']=False;shortcut_disabled=True
        for name in ('hint','procedure','judgment','core_evidence_route','bounded_recall'):flags[name]=False
    from ..basis_links.native import has_approvals
    flags['basis_live']=has_approvals(pipeline,principal)
    if flags.get('capture'):
        from .shortcut_cases import ShortcutCases
        from .shortcut_store import selected_store
        cases=ShortcutCases(selected_store(runtime),UnifiedRag(pipeline,runtime,model,catalogue),model.invoke,flags=flags)
    else:
        cases=CaseRepository(Path(runtime)/'case-memory'/'cases-v3.sqlite',UnifiedRag(pipeline,runtime,model,catalogue),model.invoke)
    if shortcut_disabled:cases.candidates=lambda *_:[]
    cases.model_resource=model
    model.cases=cases
    return cases


def result_port(pipeline,session,cases,result):
    gid=result.get('goal_id');parts=cases.parts(gid) if gid else {}
    route=cases.route(gid) if gid else None
    raw=result.get('answer') or {'text':result.get('reason') or '수정할 질문이나 조건을 지정해 주세요.','claims':[],'limitations':[]}
    initial=parts.get('READ',{}).get('payload',{}).get('originals',[])
    originals=parts.get('SELECT',{}).get('payload',{}).get('selected_originals',initial)
    selected=parts.get('SELECT',{}).get('payload',{}).get('final_ids',[])
    contexts=[{'id':x['source_id'],'document_id':x['document_id'],
        'document_name':x.get('document_name') or x['document_id'],'text':x['text'],
        'ancestors':[{'title':x.get('heading') or x.get('unit_id') or x['source_id']}]}
        for x in originals if x['source_id'] in selected]
    case={'question_id':gid,'revision':result.get('revision'),'route_id':route['id'] if route else None,
          'judgment_refs':route['payload']['judgment_refs'] if route else {},
          'experience_id':result.get('knowledge_id'),'status':result['status']}
    pipeline.contracts.validate_port('legal.case-binding-v1',case)
    query=session.context.query
    meta={'case':case,'final':True,'unified':True,'ontology_legal_coverage':cases.executor.domain.value.get('legal_coverage')}
    from .knowledge_bridge import public_metadata
    knowledge_usage=public_metadata(session.work)
    if knowledge_usage is not None:meta['legal_knowledge']=knowledge_usage
    investigation=parts.get('SELECT',{}).get('payload',{})
    if investigation.get('investigation_chain'):
        meta.update(investigation_chain=investigation['investigation_chain'],return_points=investigation.get('return_points',[]))
    if investigation.get('control_contract'):
        assessment=parts['ASSESS']['payload']
        meta.update(investigation_status='COMPLETED',answer_coverage=assessment['answer_coverage'],
            issue_assessments=assessment['issue_assessments'],gaps=assessment['gaps'],
            evidence_inventory=investigation['saved_inventory'],control_contract=investigation['control_contract'],
            semantic_quality_certified=False)
    if investigation.get('completion_contract'):
        from .completion_contracts import verify_composition
        composition=parts['COMPOSE']['payload']
        verify_composition(parts['ASSESS']['payload'],composition)
        if result.get('method_id')=='HISTORY_EXPLAIN':
            from .memory_methods import history_answer
            from .errors import ContractError
            expected,history=history_answer(cases.events(gid),composition)
            if raw!=expected:raise ContractError('history answer differs from recorded events')
            meta['answer_presentation']={'method_id':'HISTORY_EXPLAIN','history_hash':digest(history)}
        else:verify_composition(parts['ASSESS']['payload'],raw)
        meta.update(completion_contract=investigation['completion_contract'],
            stop_reason=parts['ASSESS']['payload'].get('stop_reason'),
            text_integrity=('SOURCE_BOUND_NARRATIVE' if composition.get('composition_plan',{}).get('presentation') == 'grounded-narrative-v1' else 'ACCEPTED_CLAIMS_RENDERED'),citation_integrity='ORIGINAL_SPANS')
        if composition.get('source_excerpt_reply'):
            meta['text_integrity'] = 'VERIFIED_SOURCE_EXCERPTS'
            meta['source_reply_contract'] = composition['source_excerpt_reply']['schema_version']
        if composition.get('composition_plan',{}).get('presentation'):
            meta['narrative_presentation']={'version':composition['composition_plan']['presentation'],
                'streaming':'text-deltas-during-generation', 'semantic_quality_certified':False}
        assessment=parts['ASSESS']['payload']
        meta['accepted_outcome']={'schema_version':'accepted-outcome-v1',
            'basis':'committed-ASSESS-and-verified-COMPOSE','assessment_hash':digest(assessment),
            'answer_coverage':assessment['answer_coverage'],'disposition':assessment['disposition'],
            'stop_reason':assessment.get('stop_reason'),'semantic_quality_certified':False}
    if investigation.get('law_navigation'):
        meta.update({key:investigation[key] for key in ('law_navigation','completion_policy','completed_with_unresolved_connections','reference_navigation')})
        # A completion has already committed its exact limitations with its text.
        # Preserve old duplicate-bearing commits too; normalization belongs before commit.
        limits=(list(raw.get('limitations',[])) if investigation.get('completion_contract') else
                list(dict.fromkeys(raw.get('limitations',[])+investigation.get('completion_limitations',[]))))
        missing=[] if investigation.get('completion_contract') else [value for value in investigation.get('completion_limitations',[]) if value not in raw['text']]
        raw={**raw,'limitations':limits,'text':raw['text']+('\n\n'+'\n'.join(missing) if missing else '')}
    view=None
    if route:
        from .judgment_view import build
        state=route['payload']['state']
        view=build(parts,case,state=state,run_id=session.context.run_id,
                   allowed_documents=set(state['document_ids']) & set(session.sources.scope),
                   executed=result.get('executed',[]))
    routing=result.get('request_routing') or getattr(cases,'request_routing',None)
    if routing is not None:meta['request_routing']=routing
    return {'request':session.context.request,'query':query,
        'retrieval':{'candidates':originals,'routes':{},'vector_status':'NOT_USED','generation_id':query['generation_id'],'term_agent':meta},
        'selection':{'selected':contexts,'discarded_ids':[x['source_id'] for x in originals if x['source_id'] not in selected],
                     'method':'term-agent','term_agent':meta},
        'assembly':{'context':contexts,'unresolved':raw.get('limitations',[]),
                    'data_status':pipeline.store.manifest['data_status'],
                    'term_agent':{**meta,**({'judgment_view':view} if view else {})}},
        'answer':{'schema_version':'term-runtime-v1','id':'answer:'+session.context.run_id,
            'scope':session.work.binding['scope'],'query_id':query['id'],'generation_id':query['generation_id'],
            'source_store_sha256':session.work.binding['store_sha256'],'text':raw['text'],
            'claims':[{'id':'claim:'+str(i+1),'text':c['text'],'source_ids':list(dict.fromkeys(e['source_id'] for e in claim_evidence(c)))} for i,c in enumerate(raw.get('claims',[]))],
            'unresolved':[{'reason':reason} for reason in raw.get('limitations',[])],
            'provider_receipt':{'backend':'legal_agent','model':session.profile['model_binding'],
                'quality_certified':False,'unified':True,
                'assessment_review_policy':'disabled','assessment_review_status':'SKIPPED',
                'final_review_policy':'disabled','final_review_status':'SKIPPED',
                'claim_review_status':'UNREVIEWED'}}}



def run(pipeline,body,principal,options,lease):
    runtime=Path(options['runtime'])
    cases=open_cases(pipeline,runtime,body,principal,lease=lease,
                     run_id=options.get('run_id'),release=options.get('release'))
    try:
        with cases.owner(body,principal):return execute(pipeline,body,principal,options,cases)
    except BaseException as exc:
        if hasattr(cases,'shortcut'):
            from .successful_answer import fail
            fail(cases,principal)
        if cases.model_resource.session is not None:
            from .investigation_diagnostics import exception_diagnostics
            cases.model_resource.session.work.fail(getattr(exc,'code',type(exc).__name__),
                diagnostics=exception_diagnostics(exc))
        raise
    finally:cases.close()


def execute(pipeline,body,principal,options,cases):
    from .publication import prepare,export
    runtime=Path(options['runtime'])
    result=cases.execute(body,principal)
    cases.validate_response(result,principal,body['session_id'])
    if result.get('kind')=='SOURCE_HANDOFF':
        from .source_handoff import publish
        return publish(cases,result,body,principal,runtime)
    if result.get('public_run_id'):
        # Repeated requests return the durable response only after the same
        # currentness checks as a new publication. No new model session.
        from .unified_repository import UnifiedRepository
        from .unified_publication import validate_current
        paths=list((runtime/'legal-agent'/'runs').glob('*/'+result['public_run_id']+'/journal.sqlite'))
        if len(paths)!=1:raise MemoryError('accepted request journal missing')
        from .publication import owner_lock
        with owner_lock(paths[0].parent):
            repo=UnifiedRepository(paths[0])
            try:
                repo.publication_guard=lambda value:validate_current(repo,value,pipeline.store,allowed_documents=principal['document_ids'])
                envelope=export(repo,runtime/'runs')
                finish_shortcut(cases,result,principal,envelope,repo)
                project(cases,result,principal,runtime)
                from ..basis_links.native import finish
                return finish(pipeline,cases,result,principal,body,envelope,repo)
            finally:repo.close()
    session=cases.model_resource.ensure()
    gid=result.get('goal_id')
    if gid:
        g=cases.goal(gid,body['session_id'])
        execution=UnifiedExecution(cases.executor,session,g['state'],principal)
        execution.bind_previous(cases.parts(gid))
    port=result_port(pipeline,session,cases,result)
    pipeline.contracts.validate_port('runtime.result',port)
    route=cases.route(gid) if gid else None
    commit={'singleton':1,'case_db':str(Path(cases.path).resolve()),'session_id':getattr(cases,'internal_session',body['session_id']),
        'question_id':gid,'revision':result.get('revision'),'route_id':route['id'] if route else None,
        'principal_json':encoded(principal)}
    with session.work.transaction():
        session.work.db.execute('INSERT INTO case_commit VALUES(?,?,?,?,?,?,?,?)',tuple(commit.values())+(digest(commit),))
        session.work.event('CONTROL',{'decision':'FINAL','reason':'current case route accepted'})
    extra={'response_schema':'legal-agent-unified-response-v1','quality_certified':False,
        'request_id':body['request_id'],'session_id':body['session_id'],'case_id':body['session_id'],
        'question_id':gid,'goal_id':gid,'revision':result.get('revision'),'status':result['status'],
        'question_revision':result.get('revision'),
        'case_revision':cases.db.execute('SELECT COALESCE(SUM(revision),0) FROM goal WHERE session=?',(body['session_id'],)).fetchone()[0],
        'experience_id':result.get('knowledge_id'),'knowledge_id':result.get('knowledge_id'),
        'executed':result.get('executed',[]),'method_id':result.get('method_id')}
    if hasattr(cases,'shortcut'):
        extra.update(response_schema='legal-agent-shortcut-response-v1',investigation_id=result['investigation_id'],
                     investigation_revision=result['investigation_revision'],intake_id=result['intake_id'])
    session.work.event('CASE_RESPONSE_METADATA',extra)
    session.work.save_artifact('answer',port)
    prepare(session.work,port,options.get('release'),pipeline.contracts,metadata=extra)
    key=cases.request_key(body,principal)
    with cases.transaction():
        cases.db.execute('UPDATE request SET response=? WHERE id=?',(encoded({**result,'public_run_id':session.context.run_id}),key))
    envelope=export(session.work,runtime/'runs')
    finish_shortcut(cases,result,principal,envelope,session.work)
    if (hasattr(cases,'procedure') and result.get('status')=='READY' and not cases.flags.get('core_evidence_route')
            and procedure_replayable(cases,result)):cases.procedure.activate()
    project(cases,result,principal,runtime)
    from ..basis_links.native import finish
    return finish(pipeline,cases,result,principal,body,envelope,session.work)


def finish_shortcut(cases,result,principal,envelope,work):
    if not hasattr(cases,'shortcut'):return
    from .successful_answer import record
    from .core_evidence_route import finalize
    # The receipt cannot become visible if core validation/finalization fails.
    with cases.transaction():
        if record(cases,result,principal,envelope,work):finalize(cases,result,principal)


def procedure_replayable(cases,result):
    """Replay only a route that fully covered the request without a bounded stop.

    A partial or limit-stopped route replayed on an identical re-ask would
    reproduce the same partial answer instead of investigating again."""
    gid=result.get('goal_id')
    assessment=cases.parts(gid).get('ASSESS',{}).get('payload',{}) if gid else {}
    if 'answer_coverage' not in assessment:return True  # pre-control routes keep their contract
    return assessment.get('answer_coverage')=='COVERED' and not assessment.get('stop_reason')


def project(cases,result,principal,runtime):
    # Legal wiki reads the authority even if materializing files fails.
    from .core_evidence_route import enabled
    if result['status']=='STORED' or (enabled(cases) and result.get('goal_id')):
        import sqlite3
        try:KnowledgeRepository(cases).rebuild(principal,Path(runtime)/'case-memory'/'wikis')
        except (OSError,ValueError,sqlite3.Error):
            from .. import observability as obs
            obs.event(obs.get_logger('case_memory'),'wiki.projection_pending',level=40)


def bind_system_result(session,result,runtime):
    """Source-only, greetings and catalogues stay on legal_agent's existing engines."""
    case={'question_id':None,'revision':None,'route_id':None,'judgment_refs':{}}
    result['assembly']['term_agent']['case']=case
    commit={'singleton':1,'case_db':str((Path(runtime)/'case-memory'/'cases-v3.sqlite').resolve()),
        'session_id':'ephemeral:'+session.context.run_id,'question_id':None,'revision':None,'route_id':None,
        'principal_json':encoded({'user_id':'ephemeral','team_id':'request','authenticated':False,
            'document_ids':session.work.binding['scope']['document_version_ids']})}
    with session.work.transaction():
        session.work.db.execute('INSERT INTO case_commit VALUES(?,?,?,?,?,?,?,?)',tuple(commit.values())+(digest(commit),))
        session.work.event('SYSTEM_REQUEST_ACCEPTED',{'case':case})
    session.work.save_artifact('answer',result)
