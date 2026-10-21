"""Selected local adapter with a fake HTTP client; no network or credentials."""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from semantic_runtime.legal_agent import local_gemma as local,output_contract as oc
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from test_navigation_length_recovery import adapter,call,work,PROFILE,PHASE,SCHEMA


def local_transport(monkeypatch,finishes,*,provider='Parasail',model=None,thinking=False):
    sent=[];model=model or PROFILE['model_binding']['model']
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            sent.append(deepcopy(kwargs['json']));finish=finishes[len(sent)-1]
            value={'provider':provider,'model':model,'choices':[{'finish_reason':finish,
                'message':{'content':'{"ok":' if finish=='length' else '{"ok":true}'}}],
                'usage':{'completion_tokens':kwargs['json']['max_tokens']}}
            if thinking:value['choices'][0]['message']['reasoning']='not permitted'
            raw=json.dumps(value).encode()
            return SimpleNamespace(status_code=200,is_success=True,headers={},content=raw,json=lambda:value)
    monkeypatch.setattr(local.httpx,'Client',Client)
    t=local.LocalGemmaTransport.__new__(local.LocalGemmaTransport)
    t.binding=PROFILE['model_binding'];t._key='synthetic-test-key'
    t.policy={'endpoint':'https://synthetic.invalid','provider_routing':{'only':['parasail/fp8'],'allow_fallbacks':False},'reasoning':{'effort':'none'}}
    return t,sent


@pytest.mark.parametrize('finish,repairable',[('length',True),('content_filter',False),('refusal',False)])
def test_local_preserves_typed_incomplete_cause(monkeypatch,finish,repairable):
    t,sent=local_transport(monkeypatch,[finish])
    with pytest.raises(oc.OutputContractError) as caught:
        t.send_once(body={'model':t.binding['model'],'stream':False,'max_tokens':6400},ticket={'remaining_seconds':60})
    assert caught.value.repairable is repairable
    assert caught.value.issues[0]['code']=='OUTPUT_'+finish.upper()
    assert caught.value.response['body_json']['choices'][0]['finish_reason']==finish and len(sent)==1


@pytest.mark.parametrize('bad',[{'provider':'wrong'},{'model':'wrong'},{'thinking':True}])
def test_incomplete_output_cannot_bypass_local_hard_checks(monkeypatch,bad):
    t,sent=local_transport(monkeypatch,['length'],**bad)
    with pytest.raises(ContractError):
        t.send_once(body={'model':t.binding['model'],'stream':False,'max_tokens':6400},ticket={'remaining_seconds':60})
    assert len(sent)==1


def test_local_adapter_and_bounded_owner_use_one_length_correction(work,monkeypatch):
    s,_=adapter(work,[],ceiling=12800);t,sent=local_transport(monkeypatch,['length','stop'])
    s.gateway.transport=t
    data={'question':'synthetic','sources':[]}
    def invoke(payload,attempt):return s.structured('same system',payload,SCHEMA,PHASE+('-repair' if attempt else ''),60,6400)
    def run():return oc.bounded_decision(work,'law-navigation',data,SCHEMA,invoke,lambda v:oc.validate_shape(v,SCHEMA))
    assert run()==run()=={'ok':True}
    assert [r['max_tokens'] for r in sent]==[6400,12800]
    assert work.budget()['model_reserved']==2
    response=work.db.execute('SELECT response_json FROM model_attempt ORDER BY created_seq').fetchone()[0]
    assert json.loads(response)['body_json']['choices'][0]['finish_reason']=='length'
