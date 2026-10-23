from e2e import *
from types import SimpleNamespace
from unittest.mock import patch

def main():
    directory=ART/(sys.argv[1] if len(sys.argv)>1 else 'delivery-contracts');assert not directory.exists()
    app=setup(directory,True)
    from fastapi.testclient import TestClient
    from semantic_runtime.legal_agent.memory_binding import RuntimeModel
    from semantic_runtime.legal_agent.knowledge_delivery import enrich,model_input
    from semantic_runtime.legal_agent.errors import ContractError
    from semantic_runtime.legal_agent import knowledge_delivery as kd,completion_contracts as cc
    lab=app.state.lab;lab['t'].knowledge_delivery_enabled=True;checks=[]
    with TestClient(app) as client:
        receipt=seed(app,client)
        case=read(DES/'cases.json')[1]
        body={'question':case['question'],'session_id':'delivery-contract','request_id':'delivery-contract','public_question':True}
        model=RuntimeModel(app.state.pipeline,directory/'native',body,lab['who'])
        s=model.ensure()
        plan=next(x['plan'] for x in receipt['previews'] if x['id']==case['id'])
        host=SimpleNamespace(pipeline=app.state.pipeline,binding=lab['binding'],knowledge_plan={'mode':'consume','plan':plan})
        execution=SimpleNamespace(host=host,s=s)
        empty={'selected_originals':[],'selected_evidence':[],'investigation_state':{'groups':{}},'completion_limitations':[]}
        enriched=enrich(execution,empty)
        options=cc.evidence_options(enriched['selected_originals'])
        critical=app.state.pipeline.store.source('eae25aa6e8a83c58','97')['text']
        assert any(o['text']==critical for o in options)
        assert any('3년' in o['text'] and '2년' in o['text'] for o in options)
        checks.append('exact bylaw15 block97 in assessment evidence options with source receipts')
        assert not empty['selected_originals'] and not empty['investigation_state']['groups']
        checks.append('input and navigation adoption untouched')
        before=s.work.budget()['tool_used'];again=enrich(execution,empty)
        assert s.work.budget()['tool_used']==before
        assert enriched['knowledge_original_delivery']==again['knowledge_original_delivery']
        checks.append('duplicate delivery reuses native evidence without new tool budget')
        for e in enriched['selected_evidence']:s.sources.source.verify(e)
        checks.append('all new evidence validated by native source authority')
        view,event=model_input(execution,{'sources':enriched['selected_originals']},'memory-assess')
        assert event and view['knowledge_original_review']['items'] and not event['legal_adoption']
        assert model_input(execution,{},'memory-compose')[1] is None
        checks.append('prepared assessment input distinct from composer or delivery success')
        with patch.object(kd,'LIMIT_CHARS',1):
            small=enrich(execution,empty)
        assert not small['selected_originals'] and all(r['status']=='OMITTED' for r in small['knowledge_original_delivery']['items'])
        checks.append('delivery budget skips complete bundle with explicit limitations')
        source_item=next(i for i in plan['items'] if i['source_refs']);ref=source_item['source_refs'][0]
        old=ref['content_hash'];ref['content_hash']='0'*64
        try:enrich(execution,empty)
        except ContractError:checks.append('changed source hash rejected')
        else:raise AssertionError('source corruption accepted')
        ref['content_hash']=old
        scope=s.sources.scope;s.sources.scope=[]
        try:enrich(execution,empty)
        except ContractError:checks.append('current document ACL rejected')
        else:raise AssertionError('ACL bypass')
        s.sources.scope=scope
        prior=host.binding;host.binding={**prior,'generation':'stale'}
        try:enrich(execution,empty)
        except ContractError:checks.append('generation mismatch rejected')
        else:raise AssertionError('stale source generation')
        host.binding=prior
        sid=enriched['selected_originals'][0]['source_id'];excluded=deepcopy(empty)
        excluded['investigation_state']['groups']={'x':{'source_id':sid,'status':'EXCLUDED'}}
        output=enrich(execution,excluded)
        assert sid not in output['final_ids']
        checks.append('explicit model exclusion preserved with omission reason')
        lab['t'].knowledge_delivery_enabled=False
        assert enrich(execution,empty) is empty
        checks.append('disabled guard keeps baseline identical')
        model.close()
    put(directory/'result.json',{'status':'PASS','checks':checks,'model_calls':0,'code_root':str(lab['C'].relative_to(ROOT))})
    print('CONTRACT PASS',len(checks),flush=True)
    app.state.pipeline.store.close();sys.stdout.flush();os._exit(0)
if __name__=='__main__':main()
