import pytest
from copy import deepcopy
from test_ingress import app,generation
from test_authority import WHO,BODY,review_body
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.law_navigation import Investigation
from semantic_runtime.basis_links.resolver import acquire


def test_native_priority_exact_read_and_resume(app,tmp_path):
    p=app.state.pipeline
    with p.basis_factory() as authority:
        row=authority.propose(WHO,BODY);authority.review(WHO,review_body(row))
        expected=authority.list(WHO)['items'][0]['binding']['external'][0]
    request={'question':'모의내규 근거 외규','document_ids':WHO['document_ids'],'use_llm':False}
    with p.term_agent.open_session(request,query=p.plan(request['question'],WHO['document_ids']),runtime=tmp_path/'native') as s:
        s.sources.source.basis_factory=p.basis_factory;s.sources.source.basis_principal=WHO
        rec=SourceRecall(s.sources).prepare()
        def no_model(*args,**kwargs):raise AssertionError('approval reuse must not invoke model')
        inv=Investigation(s.sources,request['question'],rec,no_model,120,None,lambda *_:None)
        acquire(inv)
        reads=inv.p['basis_links']['reads'];assert len(reads)==1,inv.p['basis_links']
        assert next(iter(reads.values()))['status']=='COMPLETE'
        source=s.work.evidence(next(iter(reads.values()))['evidence_ids'][0])
        assert source['document_id']=='outside'
        assert [{k:v for k,v in z.items() if k in ('block_id','start_cp','end_cp','text','block_hash','span_hash')} for z in source['spans']]==expected['spans']
        assert inv.p['selected'] and inv.p['window']=='read'
        view=inv.view();assert view
        count=inv.p['read_state']['count'];budget=s.work.budget()
        acquire(inv)
        assert inv.p['read_state']['count']==count and s.work.budget()==budget
        with p.basis_factory() as authority:
            authority.review(WHO,review_body(authority.list(WHO)['items'][0],'revoke','cancel'))
        acquire(inv)
        assert inv.p['read_state']['count']==count


def test_native_cocited_candidate_capture_uses_read_receipts(app,tmp_path):
    from types import SimpleNamespace
    from semantic_runtime.basis_links.native import finish
    p=app.state.pipeline;request={'question':'모의내규와 모의외규 비교','document_ids':WHO['document_ids'],'use_llm':False}
    with p.term_agent.open_session(request,query=p.plan(request['question'],WHO['document_ids']),runtime=tmp_path/'native') as s:
        refs=[]
        for did in WHO['document_ids']:
            src=s.sources.source;node=src.node(did,'0');out=src.execute({'tool':'read_node','args':{'node':node,'cursor':None},'reason':'합성 직접 원문'})
            e=s.work.evidence(out['items'][0]['evidence_id']);refs.append({'source_id':e['source_id'],'quote':e['spans'][0]['text']})
        claim={'text':'합성 내규와 외규의 승인 기준을 함께 읽었습니다.',**refs[0],'evidence':refs[1:]}
        cases=SimpleNamespace(parts=lambda _: {'COMPOSE':{'payload':{'claims':[claim]}}})
        envelope={'run_id':s.context.run_id,'answer':{'text':'원래 법률 답변','claims':[]}}
        value=finish(p,cases,{'goal_id':'g'},WHO,request,envelope,s.work)
        assert value['answer']['text']==envelope['answer']['text']
        assert len(value['basis_links']['items'])==1
        row=value['basis_links']['items'][0];assert row['link']['status']=='PROPOSED'
        again=finish(p,cases,{'goal_id':'g'},WHO,request,envelope,s.work)
        assert again['basis_link_ids']==value['basis_link_ids']
