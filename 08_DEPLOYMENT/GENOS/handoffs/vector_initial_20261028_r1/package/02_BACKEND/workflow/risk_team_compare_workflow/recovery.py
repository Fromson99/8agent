"""Targeted followups use the same RAG case; the other side stays unchanged."""
from ..contracts import digest
from .retrieval import discover


def recover(ctx,state):
    if state['recovery_count'] >= ctx.definition.manifest['max_recoveries']:
        if any(g['action'] for g in state['basis']['gaps']):state['gaps'].append('추가 조사 한도를 소진했습니다.')
        return False
    requests={};affected=set();context_requests=[]
    for gap in state['basis']['gaps']:
        action=gap['action']
        if action is None or gap['kind'] in ('NOT_REGISTERED','TOOL_FAILURE'):continue
        side=action['side']
        required={'EXTERNAL_SCOPE':'external','INTERNAL_SCOPE':'internal'}.get(gap['kind'])
        if required and side!=required:continue
        if state.get('rag_attempts',{}).get(side,{}).get('status')=='failed':continue
        old=state.get('rag_results',{}).get(side,{})
        if old.get('status') not in ('completed','partial') or not old.get('continuation',{}).get('goal_id'):continue
        key=digest([side,gap['issue_id'],gap['kind'],action['question']])
        if key in state.get('recovery_seen',[]):continue
        if action.get('context_evidence'):
            context_requests.append((key,side,gap['issue_id'],action))
        else:requests.setdefault(side,[]).append((key,action['question']))
        affected.add(gap['issue_id'])
    if not requests and not context_requests:return False
    state['recovery_count']+=1
    ctx.repo.save(state)
    for key,side,issue,action in context_requests:
        before=set(state.get('context_evidence',[])) | set(state['rag_results'][side]['evidence_ids'])
        call_id='context:'+key
        old=ctx.repo.intent(call_id,'context',{'side':side,'evidence_ids':action['context_evidence']})
        if old['status']=='COMPLETE':ids=old['result']['evidence_ids']
        elif old['status']=='FAILED':ids=[]
        else:
            ids=ctx.rag.port.saved_context(action['context_evidence'],call_id)
            ctx.repo.finish(call_id,{'evidence_ids':ids})
        if set(ids)-before:
            state['context_evidence']=sorted(set(state.get('context_evidence',[])) | set(ids))
            state.setdefault('context_by_side',{}).setdefault(side,[]).extend(ids)
            state.setdefault('recovery_seen',[]).append(key)
            ctx.repo.save(state)
        else:requests.setdefault(side,[]).append((key,action['question']))
    for side,items in requests.items():
        discover(ctx,state,side,question='기존 질문의 조사 기록과 확보 근거를 유지하고 다음 부족만 추가 조사해 주세요.\n'+ '\n'.join(q for _,q in items))
        state.setdefault('recovery_seen',[]).extend(k for k,_ in items)
        ctx.repo.save(state)
    from ..presentation import active_ids
    active=active_ids(state)
    state['retained_pairs']=[p for p in state['basis']['pairs'] if p['issue_id'] not in affected and
        set(p['internal']+p['external']+[e[k] for e in p['basis_path'] for k in ('from_evidence','to_evidence')])<=active]
    state['reopened_issues']=sorted(affected)
    return True
