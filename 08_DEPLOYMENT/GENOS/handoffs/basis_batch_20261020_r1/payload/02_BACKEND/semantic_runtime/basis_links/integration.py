"""Shared capture/presentation for discoveries and existing comparison results."""
from copy import deepcopy
import sqlite3
from .contracts import BasisUnavailable
from .contracts import BasisError,require,digest
from .resolver import snapshot,targets


def selection(e):
    return {'document_id':e['document_id'],'unit_id':e['unit_id'],
            **({'scope':'document'} if e['unit_id'] is None else {}),'spans':[{k:p[k] for k in ('block_id','start_cp','end_cp','text','block_hash','span_hash')} for p in e['spans']]}


def save_proposal(service,who,body,by):
    # Provenance is server-owned here. Candidate endpoints still pass the same
    # immutable source/side validation as explicit human selections.
    for side in ('internal','external'):
        refs=body['provenance'][side+'_refs']
        for ident in refs:
            e=by[ident]
            require(e['side']==side,'BASIS_SIDE','읽은 근거의 내규·외규 구분이 다릅니다.',409)
        require(body[side]==[selection(by[i]) for i in refs],'BASIS_SOURCE_HASH','제안과 실제 읽은 근거 범위가 다릅니다.',409)
    # The same exact candidate reappearing must not revive a rejected relation.
    documents=sorted({e['document_id'] for e in body['internal']})
    for item in (item for did in documents for item in service.list(who,did)['items']):
        link=item['link']
        if link['kind']!=body['kind']:continue
        def spans(ends):return sorted(digest(selection(e)) for e in ends)
        if all(spans(link[side])==sorted(digest(v) for v in body[side]) for side in ('internal','external')):
            if (body['provenance'].get('method')=='BATCH_DISCOVERY_V1' and link['status']=='PROPOSED'
                    and link['provenance'].get('method')!='BATCH_DISCOVERY_V1'):
                continue  # Preserve the old candidate; register this opt-in retrieval provenance.
            return item
    return service.propose(who,body)


def parent_task(ctx,state,side,action):
    factory=getattr(ctx.rag.port.services.pipeline,'basis_factory',None)
    if factory is None:
        pipeline=ctx.rag.port.services.pipeline
        runtime=getattr(pipeline,'basis_shared_runtime',None)
        if runtime is not None:
            from .api import enabled_shared_factory
            factory=enabled_shared_factory(pipeline,runtime)
            pipeline.basis_factory=factory
    if not factory or side!='external':return
    who={**ctx.request['principal'],'document_ids':ctx.request['document_ids']}
    evidence=ctx.rag.evidence();internal=[e for e in evidence if e['side']=='internal']
    documents=sorted({e['document_id'] for e in internal})
    if not documents:return
    try:
        with factory() as service:
            if 'basis_snapshot' not in state:
                state['basis_snapshot']=snapshot(service,who,documents,{d:[p for e in internal if e['document_id']==d for p in e['spans']] for d in documents},ctx.request.get('as_of'))
                ctx.repo.save(state)
            action['args']['task'].update(basis_snapshot=state['basis_snapshot'],basis_targets=targets(service,who,state['basis_snapshot']))
    except (sqlite3.OperationalError,OSError,BasisUnavailable) as exc:
        state['gaps'].append('승인 관계 조회 미완료: '+type(exc).__name__);ctx.repo.save(state)


def finish_workflow(ctx,result):
    factory=getattr(ctx.rag.port.services.pipeline,'basis_factory',None)
    if not factory:return result
    state=ctx.repo.state()['checkpoint'];who={**ctx.request['principal'],'document_ids':ctx.request['document_ids']}
    if ctx.request['workflow_id']=='internal_basis_discovery_workflow':return present(ctx.rag.port.services.pipeline,ctx.request,result)
    if not state.get('basis_capture_complete'):
        by={e['evidence_id']:e for e in ctx.rag.evidence()}
        try:
            with factory() as service:
                for pair in state.get('basis',{}).get('pairs',[]):
                    if pair['basis_relation'] in ('UNKNOWN','UNRELATED') or not pair['internal'] or not pair['external']:continue
                    external={}
                    for ident in pair['external']:external.setdefault(by[ident]['document_id'],[]).append(ident)
                    for did,refs in external.items():
                        body={'request_id':'comparison:'+ctx.context.run_id+':'+digest([pair['pair_id'],did]),
                            'internal':[selection(by[i]) for i in pair['internal']], 'external':[selection(by[i]) for i in refs],
                            'kind':'BASIS' if pair['basis_relation'] in ('DIRECT','INDIRECT') else 'RELATED',
                            'reason':pair.get('reason') or '대사 중 발견한 관계 후보. 원문과 적용 범위 검토가 필요합니다.',
                            'provenance':{'type':'MODEL_OBSERVATION','run_id':ctx.context.run_id,'pair_id':pair['pair_id'],
                                'relation':pair['basis_relation'],'basis_path':pair.get('basis_path',[]),
                                'internal_refs':pair['internal'],'external_refs':refs}}
                        saved=save_proposal(service,who,body,by)
                        state.setdefault('basis_proposals',[])
                        if saved['link']['link_id'] not in state['basis_proposals']:state['basis_proposals'].append(saved['link']['link_id'])
                state['basis_capture_complete']=True
                result={**result,'basis_link_ids':state.get('basis_proposals',[])}
                result=ctx.repo.save(state,status=result['status'],result=result)
        except (sqlite3.OperationalError,OSError,BasisUnavailable) as exc:
            result={**result,'basis_capture_status':'pending','basis_capture_error':type(exc).__name__}
    return present(ctx.rag.port.services.pipeline,ctx.request,result)


def present(pipeline,request,result):
    factory=getattr(pipeline,'basis_factory',None)
    if not factory:return result
    value=deepcopy(result);who={**request['principal'],'document_ids':request['document_ids']}
    try:
        with factory() as service:
            listed=service.view(who,request.get('input',{}).get('internal_document_id'),
                None if request['workflow_id']=='internal_basis_discovery_workflow' else set(result.get('basis_link_ids',[])),as_of=request.get('as_of'))
            wanted=set(result.get('basis_link_ids',[]))
            # Comparison exposes only relations recorded by this run.
            if request['workflow_id']!='internal_basis_discovery_workflow':listed['items']=[r for r in listed['items'] if r['link']['link_id'] in wanted]
            value['basis_links']=listed
            lines=['','근거 외규 연결 — 원문을 확인한 뒤 관리 화면에서 행을 선택해 승인·반려·취소할 수 있습니다.',
                   '| 번호 | 내규 | 외규 | 관계 | 승인 상태 | 위치 상태 |','|---|---|---|---|---|---|']
            from html import escape
            def cell(x):return escape(str(x)).replace('|','\\|').replace('\n',' ')
            for n,row in enumerate(listed['items'],1):
                link=row['link'];ends=row['binding'] or link
                lines.append('| '+' | '.join(cell(x) for x in [n,'; '.join(e['document_name']+' '+e['title'] for e in ends['internal']),
                    '; '.join(e['document_name']+' '+e['title'] for e in ends['external']),link['reason'],link['status'],row['current_status']])+' |')
            if listed['items']:
                value['basis_review_text']='\n'.join(lines)
                if request['workflow_id']!='native_rag':value['answer']['text']+=value['basis_review_text']
    except (sqlite3.OperationalError,OSError,BasisUnavailable) as exc:
        value['basis_links']={'status':'unavailable','error_type':type(exc).__name__}
    return value
