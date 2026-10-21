from copy import deepcopy
import json
from types import SimpleNamespace as NS
import pytest
from jsonschema import validate
from semantic_runtime.legal_agent.minimal_output import Projection, prepare_request
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from semantic_runtime.legal_agent.model_contract import genos_wire_schema


def obj(properties, required=None):
    return {'type':'object', 'properties':properties, 'required':list(properties) if required is None else required,
            'additionalProperties':False}


@pytest.mark.parametrize('text', ['', '한국어 원문', '😀\n인용 그대로'])
@pytest.mark.parametrize('count', [0,1,8])
def test_exact_recursive_constant_restoration(text,count):
    s=obj({'revision':{'const':7},'empty':{'type':'array','maxItems':0},
        'rows':{'type':'array','items':obj({'type':{'enum':['quote']},'text':{'type':'string'},
            'source':{'enum':['S1','S2']}})}})
    p=Projection(s);v={'revision':7,'empty':[],'rows':[{'type':'quote','text':text,'source':'S1'} for _ in range(count)]}
    raw=p.project(v);assert p.expand(raw)==v
    assert 'revision' not in raw and 'empty' not in raw
    assert all('type' not in r for r in raw['rows'])
    validate(raw,p.wire)
    assert p.expand(v)==v  # previously recorded exact full outputs remain readable


@pytest.mark.parametrize('bad',[{'revision':8,'value':'a'},{'value':'a','invented':True},{}, {'value':3}])
def test_missing_semantic_or_conflicting_host_value_rejected(bad):
    p=Projection(obj({'revision':{'const':7},'value':{'type':'string'}}))
    with pytest.raises(ProposalError):p.expand(bad)


def test_optional_constant_presence_and_schema_literals_preserved():
    literal={'properties':{'x':{'readOnly':True}},'enum':[1]}
    s=obj({'optional':{'const':7},'choice':{'enum':[literal,{'different':2}]}},['choice'])
    p=Projection(s)
    for value in ({'choice':literal},{'choice':literal,'optional':7}):
        assert p.expand(p.project(value))==value


@pytest.mark.parametrize('kind',['READ','FINISH','PENDING'])
def test_action_owns_fields_and_one_reason(kind):
    common={'action':{'type':'string','enum':['READ','FINISH','PENDING']},'reason':{'type':'string'},
        'targets':{'type':'array','items':{'type':'string','enum':['T1','T2']}},
        'citations':{'type':'array','items':{'type':'string','enum':['S1','S2']}},'revision':{'const':3}}
    s=obj(common);s['anyOf']=[]
    for action in common['action']['enum']:
        b=obj(deepcopy(common));b['properties']['action']={'type':'string','const':action}
        b['properties']['citations' if action=='READ' else 'targets']['maxItems']=0
        if action=='PENDING':b['properties']['citations']['maxItems']=0
        s['anyOf'].append(b)
    value={'action':kind,'reason':'필요 근거','targets':['T1'] if kind=='READ' else [],
        'citations':['S1'] if kind=='FINISH' else [],'revision':3}
    p=Projection(s);raw=p.project(value);validate(raw,p.wire)
    assert p.expand(raw)==value
    assert 'anyOf' not in p.wire and 'revision' not in p.wire['properties']
    if kind=='READ':
        assert 'citations' not in raw
        with pytest.raises(ProposalError):p.expand({**raw,'citations':['S2']})


def test_ambiguous_restore_rejected_and_unknown_branch_not_guessed():
    s=obj({'action':{'type':'string'},'revision':{'type':'integer'}})
    s['anyOf']=[obj({'action':{'const':a,'type':'string'},'revision':{'const':r}})
                for a,r in [('A',1),('A',2),('B',3)]]
    p=Projection(s)
    with pytest.raises(ProposalError,match='ambiguous'):p.expand({'action':'A'})
    with pytest.raises(ProposalError):p.expand({'action':'X'})
    assert p.expand({'action':'B'})=={'action':'B','revision':3}


def test_reference_scopes_are_left_intact():
    s=obj({'x':{'$ref':'#/$defs/X'}});s['$defs']={'X':{'const':'fixed'}}
    p=Projection(s);assert p.wire==s and not p.changed
    assert p.expand({'x':'fixed'})=={'x':'fixed'}
    with pytest.raises(ProposalError):p.expand({})


def navigation(n):
    from semantic_runtime.legal_agent.law_navigation import decision_schema
    from semantic_runtime.legal_agent.decision_projection import prepare
    from semantic_runtime.legal_agent import completion_contracts as cc
    view={'presentation_id':'current','laws':[],'basis':[],'branches':[],
        'issues':[{'id':'Q1','request_quote':'기준은?'}], 'completion_contract':cc.V8,
        'investigation_scope':{'request':'기준은?'},'sources':[],'state_version':3}
    kinds=['RESEARCH','SEARCH_BODY','READ_ARTICLES','READ_PARENT','READ_SCOPE','OPEN_LAW',
        'NEXT_LAWS','NEXT_ARTICLES','FOLLOW_CONNECTION','NEXT_DEFINITIONS','RETURN_TO','VIEW_SAVED_SOURCE'][:n]
    actions={f'T{i+1}':{'id':f'T{i+1}','action':k,'identity':{},'label':'모의 원문 조사'} for i,k in enumerate(kinds)}
    canonical=decision_schema(view,actions,set())
    old,expand,_=prepare(canonical,view)
    return old,expand,canonical


@pytest.mark.parametrize('n',[1,4,12])
def test_real_navigation_shape_reconstructs(n):
    old,expand,canonical=navigation(n)
    p=Projection(old)
    raw={'next_action':'RESEARCH','targets':['T1'],'queries':['기준'],
        'reason':'규정 찾기','evidence_sufficient':False,'sufficiency_reason':'아직 미확인',
        'exploration':[{'target':'T1','issue_id':'Q1','missing_need':'규정','relation':'DIRECT'}]}
    # Test compatibility and minimal output against the same original decision.
    expected=expand(raw);actual=expand(p.expand(p.project(raw)))
    assert actual==expected
    validate(actual,canonical)
    assert actual['presentation_id']=='current'


def test_exact_duplicate_schema_removed_but_source_text_preserved():
    s=obj({'revision':{'const':7},'reason':{'type':'string'}})
    view={'sources':[{'text':'그대로 보존 😀','output_schema':s}]}
    req={'messages':[{'role':'system','content':'지침'},{'role':'user','content':json.dumps({'view':view,'output_schema':s})}],
         'response_format':{'type':'json_schema','json_schema':{'schema':s}}}
    old=deepcopy(req);out,p=prepare_request(req)
    assert req==old and json.loads(out['messages'][1]['content'])=={'view':view}
    assert p.expand({'reason':'판단'})=={'revision':7,'reason':'판단'}


def test_workflow_recovery_restores_without_another_model_call():
    from semantic_runtime.workflow_bridge import Services
    s=obj({'revision':{'const':8},'opinion':{'type':'string'}})
    raw={'body_json':{'model':'synthetic','choices':[{'finish_reason':'stop','message':{'content':'{"opinion":"추가 확인"}'}}]}}
    before=deepcopy(raw)
    services=object.__new__(Services);services.profile={'model_binding':{'model':'synthetic'}}
    assert services.recover_response(raw,s)=={'revision':8,'opinion':'추가 확인'}
    assert raw==before
    raw['body_json']['model']='wrong'
    with pytest.raises(ContractError):services.recover_response(raw,s)


def test_ad_consumes_minimal_reply_and_keeps_raw(monkeypatch):
    from semantic_runtime import ad_model
    seen=[]
    target=NS(headers={'Authorization':'synthetic'},root='https://invalid.example',read_timeout=30)
    monkeypatch.setattr(ad_model,'from_env',lambda _: (target,'synthetic'))
    class T:
        def __init__(self,*_):pass
        def send_once(self,*,body,ticket):
            seen.append(body)
            assert 'revision' not in body['response_format']['json_schema']['schema']['properties']
            return {'body_json':{'model':'synthetic','choices':[{'finish_reason':'stop','message':{'content':'{"choice":"A"}'}}]}}
    monkeypatch.setattr(ad_model,'GenosTransport',T)
    s=obj({'revision':{'const':8},'choice':{'type':'string','enum':['A','B']}})
    v=ad_model.interpret({'request_id':'synthetic'},s,'지침')
    assert v['plan']=={'revision':8,'choice':'A'} and len(seen)==1
    assert json.loads(v['raw']['choices'][0]['message']['content'])=={'choice':'A'}


def test_build_provider_reconstructs_and_preserves_receipt(tmp_path):
    from semantic_runtime.genos_backend import Genos
    p=object.__new__(Genos);p.models={'llm':'synthetic'};p.max_tokens=500
    s=obj({'revision':{'const':3},'definition':{'type':'string'}})
    folder=tmp_path/'call';folder.mkdir();(folder/'receipt.json').write_text('{}')
    def request(kind,path,payload,role):
        assert '"revision"' not in payload['messages'][0]['content']
        return {'choices':[{'finish_reason':'stop','message':{'content':'{"definition":"원문 해석"}'}}]}, {'path':str(folder/'receipt.json')}
    p.request=request
    value,_=p.call('synthetic','판단',{'text':'원문'},s)
    assert value=={'revision':3,'definition':'원문 해석'} and (folder/'projection.json').is_file()


@pytest.mark.parametrize('count',[0,2,8])
def test_prospective_branch_counts(count):
    s=obj({'action':{'type':'string'},'reason':{'type':'string'},'revision':{'const':7}})
    if count:
        s['anyOf']=[obj({'action':{'type':'string','const':str(i)},
            'reason':{'type':'string'},'revision':{'const':7}}) for i in range(count)]
    p=Projection(s)
    for i in range(max(1,count)):
        v={'action':str(i),'reason':'판단 근거','revision':7}
        assert p.expand(p.project(v))==v


@pytest.mark.parametrize('mode',['json_schema','prompt','json_object'])
def test_vlm_stream_preserves_image_raw_and_canonical(mode):
    from lawrag.core.llm import LLM
    p=object.__new__(LLM);p.backend='genos';p.model='synthetic';p._genos_url='https://invalid.example'
    p._temperature=0;p._json_mode=mode;p.log=[];calls=[]
    raw='{"text":"정확한 원문 😀"}'
    frames=[{'model':'synthetic','choices':[{'delta':{'content':raw},'finish_reason':'stop'}]}]
    class Response:
        status_code=200
        headers={}
        def raise_for_status(self):pass
        def iter_lines(self):
            yield ('data: '+json.dumps(frames[0],ensure_ascii=False)).encode()
            yield b'data: [DONE]'
    def post(url,**kwargs):calls.append(kwargs['json']);return Response()
    p._session=NS(post=post)
    s=obj({'revision':{'const':9},'text':{'type':'string'}})
    result=p.structured('synthetic','픽셀 판독','원문',s,images=['data:image/png;base64,c3ludGhldGlj'])
    assert result=={'revision':9,'text':'정확한 원문 😀'}
    assert p.log[0].raw_response==raw and p.log[0].provider_response==frames
    assert p.log[0].physical_calls==1 and len(calls)==1
    assert calls[0]['messages'][1]['content'][0]['image_url']['url']=='data:image/png;base64,c3ludGhldGlj'
    if mode=='json_schema':assert 'revision' not in calls[0]['response_format']['json_schema']['schema']['properties']
