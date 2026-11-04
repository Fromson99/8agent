"""Active evidence and deterministic bounded views; old revisions stay in audit."""
from copy import deepcopy
import json
from .contracts import digest, WorkflowError
from .adapters.projection import project_sources


def valid_results(state):
    values=list(state.get('rag_results',{}).values())
    for results in state.get('rag_valid_results',{}).values():
        values.extend(r for r in results if r not in values)
    return values


def active_ids(state):
    return {i for r in valid_results(state) for i in r.get('evidence_ids', [])} | set(state.get('context_evidence', []))


def evidence(ctx, state, ids=None):
    active=active_ids(state)
    derived={i for i,origin in state.get('packet_evidence',{}).items() if origin in active}
    selected = active if ids is None else set(ids)
    if selected-(active|derived):
        raise WorkflowError('WORKFLOW_STALE_EVIDENCE','현재 근거 묶음에 없는 근거입니다.',409)
    values = ctx.rag.evidence()
    by_id = {e['evidence_id']:e for e in values}
    if selected-set(by_id):
        raise WorkflowError('WORKFLOW_ACTIVE_EVIDENCE_MISSING', '현재 판단의 근거가 저장 원장에 없습니다.',409)
    # Completeness must use the presented set, never historical parent evidence.
    from importlib import import_module
    native=import_module(ctx.rag.port.services.__class__.__module__.rsplit('.',1)[0]+'.legal_agent.source_recall')
    out=[deepcopy(by_id[i]) for i in sorted(selected)]
    issue_refs={}
    for result in valid_results(state):
        for claim in result.get('bundle',{}).get('claims',[]):
            for ident in claim.get('evidence_ids',[]):
                if ident in by_id:
                    key=ident if state.get('task_board') else by_id[ident]['source_id']
                    issue_refs.setdefault(key,set()).update(claim.get('parent_issue_refs',[]))
    for e in out:
        key=state.get('packet_evidence',{}).get(e['evidence_id'],e['evidence_id']) if state.get('task_board') else e['source_id']
        e['parent_issue_refs']=sorted(issue_refs.get(key,set()))
        e['source_complete']=native.spans_complete(ctx.rag.port.session.tools.sources[e['source_id']],out)
    return out


def source_context(ctx, state, ids, issue_id):
    """Keep active originals from the exact selected source, not model adoption.

    Identity, side and issue boundaries are preserved. Selection does not fetch
    another document, restore an inactive bundle or invent a semantic relation.
    """
    selected=evidence(ctx,state,ids)
    roots={(e['side'],e['document_id'],e['source_id']) for e in selected}
    return set(ids)|{e['evidence_id'] for e in evidence(ctx,state)
        if (e['side'],e['document_id'],e['source_id']) in roots
        and (not e['parent_issue_refs'] or issue_id in e['parent_issue_refs'])}


def compact_results(ctx, state):
    from importlib import import_module
    native=import_module(ctx.rag.port.services.__class__.__module__.rsplit('.',1)[0]+'.workflow_evidence')
    return {side:native.compact_result(r) for side,r in state.get('rag_results', {}).items()}


def size(value):
    return len(json.dumps(value,ensure_ascii=False))


def projected_size(value):
    # This is the same source projection used by ModelAdapter.prepare. Raw
    # text/spans are retained in the journal but delivered only once on the wire.
    return size(project_sources(value)[0])


def view(ctx,state,values,*,compact=False):
    results=compact_results(ctx,state)
    if compact:
        # Complete answers/rules remain in the bound export. Omitting them from
        # a packet explicitly prevents a full-closure compliance judgment.
        results={side:{k:r[k] for k in ('side','status','bundle_hash','audit_ref')} for side,r in results.items()}
    return {'question':ctx.request['question'],'as_of':ctx.request['as_of'],
        'scope':state['scope'],'gaps':state['gaps'],
        'sources':[{k:e[k] for k in ('evidence_id','side','document_id','metadata','text',
                                   'version_verified','source_complete','citation_names','spans','parent_issue_refs')} for e in values],
        'rag_results':results,'basis':state.get('basis'),
        'budget':ctx.repo.work.budget(),'deadline_at':ctx.context.deadline_at,
        **state.get('_presentation_extra',{})}


def packets(ctx,state,stage,*,ids=None,basis=None,extra=None):
    """No silent truncation: every active span is included or an explicit failure.

    Whole-scope view is preferred. Oversize views retain all originals in
    deterministic packets and mark dependency closure incomplete. A later
    complete pair may be checked in a separate comparison view.
    """
    if ids is not None and not state.get('task_board'):
        # Preserve the original context restored for these exact source IDs.
        # No lexical search or unrelated source expansion occurs here.
        known={e['evidence_id']:e for e in ctx.rag.evidence()}
        selected=evidence(ctx,state,ids)
        roots={e['source_id'] for e in selected}
        ids=set(ids)|{i for i in active_ids(state) if i in known and known[i]['source_id'] in roots}
    if ids is None and state.get('task_board') and 'review_evidence_ids' in state:ids=state['review_evidence_ids']
    values=evidence(ctx,state,ids)
    local={**state, **({'basis':basis} if basis is not None else {}), '_presentation_extra':extra or {}}
    full=view(ctx,local,values)
    limit=ctx.model.services.profile['max_context_chars']
    # Reserve room for gateway view IDs and one concrete validation error.
    cap=max(0,limit-6000)
    def bounded(data,es,index,count,complete):
        # The final digest has this exact serialized length. Include all other
        # packet metadata while planning instead of estimating its overhead.
        return {**data,**({'sources':[{**e,'source_complete':False} for e in data['sources']]} if not complete else {}),
                'packet':{'plan_hash':digest(None),'index':index,'count':count,
                          'dependency_closure_complete':complete,
                          'evidence_ids':[e['evidence_id'] for e in es]}}
    if projected_size(bounded(full,values,0,1,True))<=cap:
        raw=[(full,values,True)]
    else:
        base=view(ctx,local,[],compact=True)
        if projected_size(bounded(base,[],0,1,False))>cap:
            raise WorkflowError('WORKFLOW_CONTEXT_UNIT_TOO_LARGE','질문·비교 조건이 입력 한도를 초과했습니다. 원문과 미완료 상태를 보존했습니다.')
        pieces=list(values);count=1
        while True:
            raw=[];batch=[];replacement=None
            for offset,e in enumerate(pieces):
                candidate=view(ctx,local,batch+[e],compact=True)
                if projected_size(bounded(candidate,batch+[e],len(raw),count,False))<=cap:
                    batch.append(e);continue
                if batch:
                    raw.append((view(ctx,local,batch,compact=True),batch,False));batch=[]
                one=view(ctx,local,[e],compact=True)
                if projected_size(bounded(one,[e],len(raw),count,False))<=cap:
                    batch=[e];continue
                available=cap-projected_size(bounded(base,[],len(raw),count,False))
                if available<=0 or len(e.get('spans',[]))<=1:
                    raise WorkflowError('WORKFLOW_CONTEXT_UNIT_TOO_LARGE','하나의 원문 좌표도 입력 한도에 들어가지 않습니다.')
                # Native splitting retains whole existing spans and records a
                # verified receipt. Raw characters are only a safe lower bound;
                # each resulting unit is checked with its exact projected JSON.
                split=ctx.rag.port.split_evidence(e,available)
                for part in split:part['parent_issue_refs']=list(e['parent_issue_refs'])
                if not split:
                    raise WorkflowError('WORKFLOW_CONTEXT_UNIT_TOO_LARGE','전달할 원문 좌표를 보존할 수 없습니다.')
                state.setdefault('packet_evidence',{}).update({p['evidence_id']:e['evidence_id'] for p in split})
                ctx.repo.save(state)
                replacement=(offset,split);break
            if replacement is not None:
                offset,split=replacement
                pieces=[part for index,e in enumerate(pieces) for part in (split if index==offset else [e])]
                continue
            if batch or not raw:raw.append((view(ctx,local,batch,compact=True),batch,False))
            # A larger packet count can add decimal digits to every packet.
            # Repack only when that changes its serialized size; no source is
            # reread and no retry/model allowance is consumed by planning.
            if len(str(len(raw)))>len(str(count)):
                count=len(raw);continue
            break
    out=[]
    plan_hash=digest({'stage':stage,'bundles':{s:r.get('bundle',{}).get('bundle_hash') for s,r in state.get('rag_results',{}).items()},
                      'sources':[[e['evidence_id'] for e in es] for _,es,_ in raw],'basis':basis})
    for index,(data,es,complete) in enumerate(raw):
        data['packet']={'plan_hash':plan_hash,'index':index,'count':len(raw),'dependency_closure_complete':complete,
                        'evidence_ids':[e['evidence_id'] for e in es]}
        if not complete:
            for e in data['sources']:e['source_complete']=False
        if projected_size(data)>cap:raise WorkflowError('WORKFLOW_CONTEXT_UNIT_TOO_LARGE','원문 전달 묶음이 입력 한도를 초과했습니다.')
        out.append((data,es))
    return out


def checkpoint(ctx,state,stage,data,result):
    # Idempotent ModelAdapter receipts own replay; this cursor makes unfinished
    # packets explicit to status/resume without resetting global counters.
    p=data['packet'];state.setdefault('packets',{})[stage]={'plan_hash':p['plan_hash'],
        'completed_index':p['index'],'count':p['count'],'result_hash':digest(result)}
    ctx.repo.save(state)
