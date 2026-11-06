import pytest
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.ontology_work.wiki_projection import compare_judgment
from test_wiki_workspace import env, ws, seed, compiled, wire_normalization
from test_domain_profile_workflow import normalized_output


@pytest.mark.parametrize('scenario',['supported','contradicted','wrong-quote','stale','duplicate'])
def test_append_comparison_preserves_graph_and_original_evidence(env,ws,scenario):
    item=seed(env,ws)
    row,_=compiled(env,ws,item)
    bid=row['bundle_id']
    before=ws.load(bid)
    source=ws.import_payload('독립된 실제 판단',event_id='second-question',run_id='independent')
    request=dict(bundle_id=bid,revision=row['revision'],work_hash=row['work_hash'],raw_id=source['bundle_id'])
    calls=[]
    def model(prompt,context,schema):
        calls.append(context.get('operation','NORMALIZE'))
        if 'raw' in context:
            return wire_normalization(normalized_output(context)),{}
        changed=scenario=='contradicted'
        return {key:{'relation':'CONTRADICTION' if changed else 'SAME','verdict':'CONTRADICTED' if changed else 'SUPPORTED',
                    'reason':'저장된 원문 기준과 새 관찰을 비교함','basis':[{'source':'S1','quote':'없는 인용' if scenario=='wrong-quote' else env.source['text']}],
                    'node_ids':['N1']} for key in context['judgments']},{}
    ws.generate=model
    if scenario=='stale':
        with pytest.raises(ContractError,match='stale'):
            compare_judgment(env.w,ws,**{**request,'work_hash':'different'})
        assert calls==[]
        return
    if scenario=='wrong-quote':
        with pytest.raises(ContractError):
            compare_judgment(env.w,ws,**request)
        assert ws.load(bid)['revision']==row['revision']
        return
    saved=compare_judgment(env.w,ws,**request)
    after=ws.load(bid)
    assert saved['revision']==row['revision']+1 and after['base_work_hash']==row['work_hash']
    assert after['proposal']['graph']==before['proposal']['graph']
    assert after['workspace_projection']==before['workspace_projection']
    assert after['comparison_history'][:-1]==before['comparison_history']
    assert len(after['observation_ledger'])>len(before['observation_ledger'])
    assert after['review_state']==('REVIEW_CONFLICT' if scenario=='contradicted' else 'REVIEW_REQUIRED')
    assert ws.preview(bid)['authority']=='PREVIEW'
    count=len(calls)
    assert compare_judgment(env.w,ws,**request)['reused']
    if scenario=='duplicate':
        with pytest.raises(ContractError,match='already recorded'):
            compare_judgment(env.w,ws,**{**request,'revision':saved['revision'],'work_hash':saved['work_hash']})
    assert len(calls)==count
