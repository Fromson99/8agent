import json
from types import SimpleNamespace as NS
import pytest
from semantic_runtime.genos import from_env
from semantic_runtime.oracle_query_vector import PublishedEncoder
from semantic_runtime.initial_vector import VectorError
from semantic_runtime.oracle_query_service import environment_binding
from test_vector import PROFILE, fixture


def field_env():
    return {'GENOS_URL':'https://genos.invalid','GENOS_EMBED_ID':'19','GENOS_EMBED_TOKEN':'fixture-only'}


@pytest.mark.parametrize('base_name',['GENOS_URL','GENOS_BASE_URL'])
@pytest.mark.parametrize('profile_pin',[None,'',' '])
def test_field_names_need_neither_profile_hash_nor_model(base_name,profile_pin):
    env=field_env();env[base_name]=env.pop('GENOS_URL')
    if profile_pin is not None:env['GENOS_EMBED_PROFILE_SHA256']=profile_pin
    calls=[]
    def post(url,**kw):
        calls.append((url,kw))
        return NS(status_code=200,json=lambda:{'data':[{'index':0,'embedding':[2.,0.,0.]}]})
    enc=PublishedEncoder(PROFILE,env=env,post=post)
    assert enc.encode(['승인'])==[[1.,0.,0.]]
    assert calls[0][0]=='https://genos.invalid/api/gateway/rep/serving/19/embeddings'
    assert calls[0][1]['headers']['Authorization']=='Bearer fixture-only'
    assert calls[0][1]['json']=={'model':'genos','input':['승인']}
    assert calls[0][1]['allow_redirects'] is False and enc.calls==1


def test_new_names_take_precedence_and_whitespace_falls_back():
    e={**field_env(),'GENOS_BASE_URL':'https://base.invalid','GENOS_EMBED_SERVING_ID':'27','GENOS_EMBED_KEY':'legacy-fixture'}
    target,_=from_env('embed',environ=e)
    assert target.root=='https://base.invalid/api/gateway/rep/serving/19'
    assert target.headers['Authorization']=='Bearer fixture-only'
    e.update(GENOS_EMBED_ID=' ',GENOS_EMBED_TOKEN=' ')
    target,_=from_env('embed',environ=e)
    assert target.root.endswith('/27') and target.headers['Authorization']=='Bearer legacy-fixture'


def test_direct_server_requires_model_and_preserves_url_precedence():
    e={**field_env(),'GENOS_EMBED_URL':'https://direct.invalid'}
    with pytest.raises(VectorError,match='MODEL required'):PublishedEncoder(PROFILE,env=e)
    e['GENOS_EMBED_MODEL']='fixture-kure'
    enc=PublishedEncoder(PROFILE,env=e)
    assert enc.target.url('/embeddings')=='https://direct.invalid/v1/embeddings'
    assert enc.profile['model']=='fixture-kure'
    e['GENOS_EMBED_URL']='https://direct.invalid/api/gateway/rep/serving/33';e.pop('GENOS_EMBED_MODEL')
    assert PublishedEncoder(PROFILE,env=e).profile['model']=='genos'


@pytest.mark.parametrize('key',['GENOS_EMBED_ID','GENOS_EMBED_TOKEN','GENOS_URL'])
def test_missing_connection_settings_fail_without_network_or_secrets(key):
    e=field_env();e.pop(key)
    with pytest.raises(VectorError) as error:PublishedEncoder(PROFILE,env=e)
    assert 'fixture-only' not in str(error.value)


@pytest.mark.parametrize('key',['GENOS_EMBED_ID','GENOS_EMBED_TOKEN','GENOS_URL'])
def test_alias_changes_invalidate_request_environment(monkeypatch,key):
    before=environment_binding();monkeypatch.setenv(key,'fixture-changed')
    assert before!=environment_binding()


def test_llm_environment_unchanged_by_embedding_aliases():
    e={**field_env(),'GENOS_BASE_URL':'https://llm.invalid','GENOS_LLM_SERVING_ID':'51','GENOS_LLM_KEY':'llm-fixture','GENOS_LLM_MODEL':'llm'}
    target,model=from_env('llm',environ=e)
    assert target.root=='https://llm.invalid/api/gateway/rep/serving/51'
    assert target.headers['Authorization']=='Bearer llm-fixture' and model=='llm'


def test_actual_encoder_from_oracle_profile_without_manual_hash(monkeypatch):
    reader,_,_,sql_calls,_=fixture();sends=[]
    def post(url,**kw):
        sends.append((url,kw))
        return NS(status_code=200,json=lambda:{'data':[{'index':0,'embedding':[3.,0.,0.]}]})
    reader.encoder_factory=lambda profile,**kw:PublishedEncoder(profile,env=field_env(),post=post,**kw)
    result=reader.search('승인',{'public'})
    assert result['rows'][0]['SOURCE_ID']=='article:1' and result['embedding_calls']==1
    assert reader.search('승인',{'public'})==result and len(sends)==1 and len(sql_calls)==3
    assert 'SIDDS.LGL_G19_VCTR_ITEM_S_1' in sql_calls[-1][0]
