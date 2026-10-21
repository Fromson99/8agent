import json
import pytest
from test_legal_agent_double_harness import work
from test_genos_output_unlimited import adapter, SCHEMA
from semantic_runtime.legal_agent.errors import ProposalError


@pytest.mark.parametrize('phase',['bounded-question-plan','source-query-plan','source-reference-1',
    'source-law-navigation-1','memory-assess','memory-compose','workflow-compare'])
def test_actual_gateway_restores_minimal_output_and_keeps_raw(work,phase):
    session,calls=adapter(work,values=[{}])
    assert session.structured('system',{},SCHEMA,phase,60)=={'ok':True}
    assert len(calls)==1 and work.budget()['model_reserved']==1
    assert calls[0]['response_format']['json_schema']['schema']['properties']=={}
    row=work.db.execute('SELECT response_json FROM model_attempt').fetchone()
    assert json.loads(json.loads(row[0])['body_json']['choices'][0]['message']['content'])=={}
    assert work.db.execute("SELECT COUNT(*) FROM event WHERE kind='MODEL_OUTPUT_RECONSTRUCTED'").fetchone()[0]==1


def test_wrong_host_constant_fails_without_extra_stage_retry(work):
    session,calls=adapter(work,values=[{'ok':False}])
    with pytest.raises(ProposalError):session.structured('system',{},SCHEMA,'source-law-navigation-1',60)
    assert len(calls)==1 and work.budget()['model_reserved']==1
