import pytest
from test_wiki_workspace import env, ws, seed, compiled, wire_normalization
from test_domain_profile_workflow import normalized_output
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.ontology_work.wiki_projection import compare_judgment

@pytest.mark.parametrize('relation,quote,accepted',[('NEW',True,True),('NEW',False,False),('SAME',True,False),('CONTRADICTION',True,False)])
def test_new_standalone_requires_original_but_not_an_existing_node(env,ws,relation,quote,accepted):
    item=seed(env,ws)
    draft,_=compiled(env,ws,item)
    raw=ws.import_payload('별도 참고 판단',event_id='new-other',run_id='different-question')
    def model(prompt,ctx,schema):
        if 'raw' in ctx:return wire_normalization(normalized_output(ctx)),{}
        return {k:{'relation':relation,'verdict':'CONTRADICTED' if relation=='CONTRADICTION' else 'SUPPORTED',
                   'reason':'서로 다른 원문 역할','basis':[{'source':'S1','quote':env.source['text']}] if quote else [],
                   'node_ids':[]} for k in ctx['judgments']},{}
    ws.generate=model
    req=dict(bundle_id=draft['bundle_id'],revision=draft['revision'],work_hash=draft['work_hash'],raw_id=raw['bundle_id'])
    if accepted:
        saved=compare_judgment(env.w,ws,**req)
        assert saved['revision']==draft['revision']+1 and ws.load(draft['bundle_id'])['judgment_review']['requires_graph_review']
    else:
        with pytest.raises(ContractError):compare_judgment(env.w,ws,**req)
        assert ws.load(draft['bundle_id'])['revision']==draft['revision']
