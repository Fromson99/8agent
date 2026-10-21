"""Full Pipeline question/answer calls and verified return packages for workflows."""
import json
from pathlib import Path
from .contracts import digest
from .legal_agent.errors import ContractError, LegalAgentError
from .legal_agent.corrected_memory import MemoryError, Conflict
from .legal_agent.unified_repository import UnifiedRepository
from .legal_agent.workflow_execution import child_execution


def verify_returns(port):
    """Saved comparison responses remain bound to the child's actual record."""
    db=port.session.repo.db
    table=db.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_child_run'").fetchone()
    if not table:return
    import sqlite3
    for call_id, raw, result_hash in db.execute("SELECT call_id,result_json,result_hash FROM workflow_call WHERE kind='rag' AND status='COMPLETE'"):
        result=json.loads(raw)
        if digest(result)!=result_hash:raise ContractError('workflow child result hash changed')
        for record in result.get('records',[]):
            row=db.execute('SELECT * FROM workflow_child_run WHERE run_id=?',(record['run_id'],)).fetchone()
            if row is None:raise ContractError('saved RAG journal reference missing')
            path=Path(row['journal']).resolve()
            root=port.services.runtime/'workflows'/port.session.context.run_id/'children'
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ContractError('saved child journal outside workflow')
            child=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);child.row_factory=sqlite3.Row
            try:
                run=child.execute('SELECT * FROM run').fetchone()
                observations=[dict(r) for r in child.execute('SELECT observation_id,request_json,result_json FROM observation ORDER BY created_seq')]
                if (run['binding_hash']!=record['binding_hash'] or digest(json.loads(run['binding_json']))!=record['binding_hash']
                        or digest(observations)!=record['observation_hash']):
                    raise ContractError('saved child RAG record integrity mismatch')
                if result.get('schema_version') in ('workflow-rag-result-v2','workflow-rag-result-v3') and result.get('bundle',{}).get('producer',{}).get('run_id')==record['run_id']:
                    from .workflow_evidence import verify_export
                    # Read-only adapter: verification must not migrate/write a child journal.
                    from types import SimpleNamespace
                    from .legal_agent.repository import WorkRepository
                    native=SimpleNamespace(db=child,path=path,run=lambda:dict(run),binding=json.loads(run['binding_json']))
                    native.evidence=lambda ident=None:WorkRepository.evidence(native,ident)
                    verify_export(port.session.repo,call_id,native,result,port)
            finally:child.close()


def failed_child_receipt(port, action, call_id):
    """A failed model operation is not reexecuted to reconstruct its read export."""
    rows=port.session.repo.db.execute(
        "SELECT payload_json,payload_hash FROM event WHERE kind='WORKFLOW_CHILD_FAILED' AND json_extract(payload_json,'$.call_id')=? ORDER BY seq",
        (call_id,)).fetchall()
    if not rows:return None
    if len(rows)!=1:raise ContractError('ambiguous workflow child failure receipt')
    raw,expected=rows[0]
    receipt=json.loads(raw)
    canonical={k:action[k] for k in ('operation','side','args')}
    if (digest(receipt)!=expected or receipt.get('schema_version')!='workflow-child-failure-v1'
            or receipt.get('side')!=action['side'] or receipt.get('action_hash')!=digest(canonical)
            or receipt.get('parent_binding_hash')!=port.session.context.binding_hash
            or not isinstance(receipt.get('export_reads'),bool) or not isinstance(receipt.get('error_code'),str)):
        raise ContractError('workflow child failure receipt changed or cannot safely resume')
    return receipt


def validate_internal_anchors(port, anchors):
    port.verify_all()
    by={e['evidence_id']:e for e in port.evidence()}
    for anchor in anchors:
        for source in anchor['sources']:
            e=by.get(source['evidence_id'])
            if (e is None or e['side']!='internal' or e['document_id'] not in port.all_scope or
                    e['document_id']!=source['document_id'] or
                    e['metadata']['document_name']!=source['document_name'] or
                    e['metadata'].get('heading','')!=source['heading'] or
                    not any(source['quote'] in s['text'] for s in e['spans'])):
                raise ContractError('internal concept anchor source/ACL mismatch')


def execute(port, action, call_id):
    service, session = port.services, port.session
    side = action['side']
    if side not in ('internal', 'external') or action['operation'] != 'ask_rag':
        raise ContractError('workflow requires one scoped complete RAG question')
    docs = sorted(d for d in port.all_scope if port.categories[d] == side)
    args = action['args']
    if set(args) not in ({'question','previous'},{'question','previous','task'}) or not isinstance(args['question'], str) or not args['question'].strip():
        raise ContractError('invalid workflow RAG question')
    task=args.get('task')
    if task is not None and (not isinstance(task,dict) or set(task)-{'research_task','comparison_fields','return_mode','preferred_document_ids','basis_snapshot','basis_targets','research_policy','research_requirements','research_continuity','internal_anchors'} not in ({'source_category','search_hints'},{'source_category','search_hints','issues','facts'}) or task['source_category']!=side or
            not isinstance(task['search_hints'],list) or len(task['search_hints'])>4 or
            any(not isinstance(q,str) or not 0<len(q)<=500 for q in task['search_hints'])):
        raise ContractError('invalid trusted workflow task context')
    from .legal_agent.workflow_execution import validate_task
    validate_task(task,session.context.request.get('question',args['question']),verify_requirements=True)
    if task and task.get('internal_anchors'):
        validate_internal_anchors(port,task['internal_anchors'])
    if task and task.get('research_continuity') and task['research_continuity']['binding_hash']!=session.context.binding_hash:
        raise ContractError('research continuity parent binding changed')
    if task and task.get('research_task'):
        from .comparison_research_bridge import validate_parent
        validate_parent(port,task['research_task'],side)
    if task and not set(task.get('preferred_document_ids',[]))<=set(docs):raise ContractError('preferred document outside side/ACL')
    question = ('내규: ' if side == 'internal' else '외규: ') + args['question']
    child_session = 'workflow:' + session.context.run_id + ':' + side
    result = dict(schema_version='workflow-rag-result-v2', side=side, question=question,
                  session_id=child_session, request_id=call_id, status='not_registered',
                  answer=None, evidence_ids=[], records=[], unresolved=[], continuation=None)
    if not docs:
        result['unresolved'] = ['허용된 '+side+' 문서가 등록되어 있지 않습니다.']
        return result
    previous = args['previous']
    target = None
    body = dict(question=question, document_ids=docs, session_id=child_session, request_id=call_id)
    if previous is not None:
        if previous.get('session_id') != child_session or previous.get('side') != side:
            raise ContractError('followup belongs to another workflow side')
        target = previous.get('continuation')
        if not target or not target.get('goal_id'):
            raise ContractError('previous RAG result has no resumable case')
        body['expected_revision'] = target['revision']
        for key in ('investigation_id', 'investigation_revision'):
            if target.get(key) is not None:
                body[key] = target[key]
    principal = {**session.context.request['principal'], 'authenticated':True, 'document_ids':docs}
    runtime = service.runtime/'workflows'/session.context.run_id/'children'/side
    options = dict(runtime=runtime, release=service.release, case_body=body, principal=principal)
    if task and task.get('return_mode')=='sources':
        options['_shortcut_ingress']=True
        result['schema_version']='workflow-rag-result-v3'
    envelope = None
    export_reads = False
    failure=failed_child_receipt(port,action,call_id)
    if failure is None:
        try:
            from .legal_agent.answer_stream import suppress
            with child_execution(session.repo, session.context, call_id, docs, target, task=task), suppress():
                envelope = service.pipeline.run(question, documents=docs,
                    use_llm=session.context.request['use_llm'], execution_context=options)
        except (ContractError, Conflict):
            raise
        except (LegalAgentError, MemoryError, TimeoutError) as exc:
            from .legal_agent.errors import InvestigationPending, BudgetExhausted, TransportError
            # The original failure is durable before source export or parent commit.
            # Reuse it after interruption; never reexecute an unknown model operation.
            failure=dict(schema_version='workflow-child-failure-v1',call_id=call_id,side=side,
                action_hash=digest({k:action[k] for k in ('operation','side','args')}),
                parent_binding_hash=session.context.binding_hash,error_type=type(exc).__name__,
                cause=str(exc),error_code=getattr(exc,'code',type(exc).__name__),
                export_reads=isinstance(exc,(InvestigationPending,BudgetExhausted,TimeoutError,TransportError)))
            session.repo.event('WORKFLOW_CHILD_FAILED',failure)
    if failure is not None:
        export_reads=failure['export_reads']
        result.update(status='failed',error_code=failure['error_code'],
            unresolved=['RAG 조사를 완료하지 못했습니다. 조회 실패는 규정 부재를 뜻하지 않습니다.'])
    if envelope is not None and envelope.get('kind')=='SOURCE_HANDOFF':
        handoff=envelope['handoff']
        result.update(status='partial' if handoff.get('stop_reason') or not handoff['read_evidence_ids'] else 'completed',
            run_id=envelope['run_id'],answer=None,investigation_return=handoff,
            unresolved=[handoff['reason']] if handoff.get('stop_reason') or not handoff['read_evidence_ids'] else [],
            continuation={key:envelope.get(key) for key in ('goal_id','revision','investigation_id','investigation_revision')})
    elif envelope is not None:
        meta=envelope.get('assembly',{}).get('term_agent',{})
        result.update(status='completed' if meta.get('answer_coverage') == 'COVERED' else 'partial',
            answer=envelope.get('answer'), run_id=envelope.get('run_id'),
            unresolved=[v.get('reason',str(v)) if isinstance(v,dict) else str(v)
                        for v in envelope.get('answer',{}).get('unresolved',[])],
            assessment={key:meta.get(key) for key in ('accepted_outcome','gaps','stop_reason','issue_assessments')},
            continuation={key:envelope.get(key) for key in
                ('goal_id','revision','investigation_id','investigation_revision')})
    table=session.repo.db.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_child_run'").fetchone()
    rows=session.repo.db.execute('SELECT * FROM workflow_child_run WHERE call_id=? ORDER BY rowid',(call_id,)).fetchall() if table else []
    for row in rows:
        path=Path(row['journal']).resolve()
        if not path.is_relative_to(runtime.resolve()) or not path.is_file():
            raise ContractError('child journal missing or outside workflow runtime')
        child=UnifiedRepository(path)
        try:
            if child.run()['binding_hash'] != row['binding_hash'] or child.run()['run_id'] != row['run_id']:
                raise ContractError('child journal identity changed')
            if set(child.binding['scope']['document_version_ids']) != set(docs):
                raise ContractError('child evidence scope changed')
            evidence=[]
            if envelope is not None and row['run_id']==envelope.get('run_id'):
                from .workflow_evidence import compile_bundle, save_export
                if envelope.get('kind')=='SOURCE_HANDOFF':
                    from .workflow_evidence import compile_source_bundle
                    bundle,evidence=compile_source_bundle(child,envelope,side,session.verify,session.store,docs)
                else:bundle,evidence=compile_bundle(child,envelope,side,session.verify,session.store,docs)
                result['bundle']=bundle
                session.repo.record_observation({'tool':'rag_answer_return','args':{'call_id':call_id,'run_id':row['run_id']}},
                    {'status':'OK','child_status':result['status'],'bundle_hash':bundle['bundle_hash']}, evidence, verify=session.verify)
                save_export(session.repo,call_id,child,envelope,bundle)
                result['evidence_ids'].extend(e['evidence_id'] for e in evidence)
            elif export_reads and row==rows[-1]:
                from .workflow_evidence import compile_read_bundle, save_export
                bundle,evidence=compile_read_bundle(child,side,session.verify,session.store,docs)
                result.update(bundle=bundle,run_id=row['run_id'])
                session.repo.record_observation({'tool':'rag_read_return','args':{'call_id':call_id,'run_id':row['run_id']}},
                    {'status':'OK','child_status':result['status'],'bundle_hash':bundle['bundle_hash']},evidence,verify=session.verify)
                save_export(session.repo,call_id,child,None,bundle)
                result['evidence_ids'].extend(e['evidence_id'] for e in evidence)
            observations=[dict(r) for r in child.db.execute('SELECT observation_id,request_json,result_json FROM observation ORDER BY created_seq')]
            result['records'].append(dict(run_id=row['run_id'], binding_hash=row['binding_hash'],
                budget=child.budget(), journal_ref=row['run_id'], observation_count=len(observations),
                observation_hash=digest(observations)))
        finally:
            child.close()
    if envelope is not None and (envelope.get('answer') or {}).get('claims') and not result.get('bundle'):
        raise ContractError('accepted RAG answer has no bound child export')
    result['evidence_ids']=sorted(set(result['evidence_ids']))
    return result
