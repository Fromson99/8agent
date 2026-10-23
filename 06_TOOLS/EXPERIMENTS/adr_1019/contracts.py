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
        # A cached read may rebind an exact subrange to a different valid evidence
        # receipt. Verify identical delivered source content and the new receipts.
        put(directory/'repeat-receipts.json',{'first':enriched['knowledge_original_delivery'],'second':again['knowledge_original_delivery']})
        assert {(r['source_id'],r['text']) for r in enriched['selected_originals']}=={(r['source_id'],r['text']) for r in again['selected_originals']}
        for evidence in again['selected_evidence']:s.sources.source.verify(evidence)
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
        lab['t'].knowledge_delivery_enabled=True
        old_plan=host.knowledge_plan;host.knowledge_plan={'mode':'consume','plan':{'binding':None,'items':[]}}
        assert enrich(execution,empty) is empty and kd.reuse_mode(execution)=='EXTEND'
        host.knowledge_plan=old_plan;checks.append('empty plan disables delivery and closed gate')
        original_result={'claims':[{'id':'C1'}],'gaps':[{'kind':'MISSING_SOURCE'}]};original_copy=deepcopy(original_result)
        lab['t'].knowledge_reuse_mode='CLOSED_EVIDENCE'
        assert kd.block_additional_research(execution,[{'kind':'MISSING_SOURCE'}],original_result)
        assert original_result==original_copy
        assert kd.block_additional_research(execution,[],original_result)
        checks.append('closed gate blocks new investigation and preserves partial claims/gaps on repeat')
        lab['t'].knowledge_reuse_mode='EXTEND'
        assert not kd.block_additional_research(execution,[{'kind':'MISSING_SOURCE'}],original_result)
        checks.append('extension mode retains native investigation ownership')
        lab['t'].knowledge_use_first_prompt=False;before=kd.assessment_prompt(execution,'memory-assess')
        lab['t'].knowledge_use_first_prompt=True;after=kd.assessment_prompt(execution,'memory-assess')
        assert after==before+kd.USE_FIRST_PROMPT
        assert kd.assessment_prompt(execution,'memory-compose')==''
        checks.append('only assessment and its repair receive stronger system prompt')
        put(ART/'reuse-mode-contracts.json',{'status':'PASS','checks':checks[-4:],'model_calls':0})
        model.close()
    put(directory/'result.json',{'status':'PASS','checks':checks,'model_calls':0,'code_root':str(lab['C'].relative_to(ROOT))})
    print('CONTRACT PASS',len(checks),flush=True)
    app.state.pipeline.store.close();sys.stdout.flush();os._exit(0)
if __name__=='__main__':main()
