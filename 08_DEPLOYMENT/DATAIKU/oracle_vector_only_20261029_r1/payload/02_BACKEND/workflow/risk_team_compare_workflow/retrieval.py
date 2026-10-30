"""Ask the existing RAG once per side, preserving full answers and native records."""
from ..contracts import digest


def discover(ctx, state, side, *, question=None, research_task=None, previous_result=None):
    previous=state.get('rag_results',{}).get(side) if question is not None else None
    if previous_result is not None:previous=previous_result
    text=question or ctx.request['question']
    if ctx.request['as_of']:
        text+='\n기준일: '+ctx.request['as_of']
    action={'operation':'ask_rag','side':side,'args':{'question':text,'previous':previous,'task':{'source_category':side,
            'search_hints':list(state['scope'][side+'_queries']),
            **({'issues':[{'id':i['id'],'question':i[side+'_task'],'numeric':i['numeric']} for i in state['scope']['issues']],
                'facts':state['scope']['facts']} if state['scope'].get('facts') is not None and
                all(side+'_task' in i for i in state['scope']['issues']) else {})}},
            'reason':'기존 RAG 전체 실행에 질문하고 답변·근거·기록 수신'}
    if state.get('task_board'):action['args']['task']['comparison_fields']={i['id']:i['requested_fields'] for i in state['scope']['issues']}
    from .query_scope import enabled,POLICY
    if enabled(ctx):
        action['args']['task'].update(research_policy=POLICY,
            research_requirements=[{'issue_id':i['id'],'task':i[side+'_task'],
                'requirements':i.get('requirements',[])} for i in state['scope']['issues']])
    if research_task is not None:
        action['args']['task']['research_task']=research_task
        from semantic_runtime.research_state import ResearchLedger
        action['args']['task']['research_continuity']=ResearchLedger(state['task_board']).child_context(side,research_task['binding_hash'],research_task)
    if ctx.definition.manifest.get('source_return_contract') in ('source-investigation-v1','source-investigation-v2'):
        from semantic_runtime.comparison_research_bridge import preferred_documents
        action['args']['task'].update(return_mode='sources',preferred_document_ids=preferred_documents(ctx.rag.port,ctx.request['question'],side))
    from semantic_runtime.basis_links.integration import parent_task
    parent_task(ctx,state,side,action)
    if side=='external' and state.get('concept_plan'):
        from .concepts import anchors,originals
        action['args']['task']['internal_anchors']=anchors(state,originals(ctx,state))
        action['reason']='확인한 내규 개념·조항을 출발점으로 대응 외규 원문 조사'
    key='rag:'+digest(action)
    if key in state.get('seen',[]):
        saved=ctx.repo.call(key)
        return bool(saved and saved['status']=='COMPLETE' and saved['result']['status'] in ('completed','partial'))
    result=ctx.rag.call(action,call_id=key)
    state.setdefault('seen',[]).append(key)
    state.setdefault('rag_attempts',{})[side]=result
    valid=result['status'] in ('completed','partial')
    readable=valid or bool(result.get('evidence_ids') and result.get('bundle',{}).get('export_mode')=='READ_ORIGINALS')
    if readable:
        history=state.setdefault('rag_valid_results',{}).setdefault(side,[])
        old=state.get('rag_results',{}).get(side)
        if old and old.get('status') in ('completed','partial') and old not in history:history.append(old)
        if result not in history:history.append(result)
    if readable or side not in state.get('rag_results',{}):
        state.setdefault('rag_results',{})[side]=result
    # Failure is a separate attempt; prior verified evidence and contexts survive.
    # Every use still passes the native ACL/generation/hash and child-export checks.
    state['history'].append({'side':side,'call_id':key,'status':result['status'],
                             'run_id':result.get('run_id'),'reason':action['reason']})
    state['gaps'].extend(result['unresolved'] if result['status'] in ('failed','not_registered') else [])
    ctx.repo.save(state)
    return result['status'] in ('completed','partial')


def restore_context(ctx,state):
    """Restore complete already-read originals for current adopted sources."""
    for side,result in state.get('rag_results',{}).items():
        adopted=sorted(result.get('evidence_ids',[]))
        if not adopted:continue
        key='source-context:'+digest([side,result.get('bundle',{}).get('bundle_hash'),adopted])
        old=ctx.repo.intent(key,'context',{'side':side,'evidence_ids':adopted})
        if old['status']=='COMPLETE':ids=old['result']['evidence_ids']
        elif old['status']=='FAILED':continue
        else:
            ids=ctx.rag.port.saved_context(adopted,key)
            ctx.repo.finish(key,{'evidence_ids':ids})
        state['context_evidence']=sorted(set(state.get('context_evidence',[]))|set(ids))
        by_side=state.setdefault('context_by_side',{})
        by_side[side]=sorted(set(by_side.get(side,[]))|set(ids))
        ctx.repo.save(state)
