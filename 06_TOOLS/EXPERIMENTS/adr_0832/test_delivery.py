from copy import deepcopy
import json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.bounded_source_session import compact_assessment_evidence
from semantic_runtime.legal_agent.source_tools import canonical_evidence
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.completion_contracts import evidence_options


def fixture(text='앞 문장.\n\n승인 후 보고한다.\n' + '가'*1250, rebound=False):
    span={'block_id':'b','start_cp':7,'end_cp':7+len(text),'text':text,
          'block_hash':text_hash('prefix '+text),'span_hash':text_hash(text)}
    e=canonical_evidence(dict(source_id='s',document_id='d',unit_id='1',generation_id='g',
        source_artifact_hash='a'*64,role='reference',temporal_status='unknown',metadata={}),[span])
    source={**e,'text':text,'adopted_spans':[{**span,'evidence_id':e['evidence_id']}]}
    options=evidence_options([source])
    data={'sources':[{'source_id':'s','document_id':'d','evidence_refs':[o['id'] for o in options]}],
          'evidence_options':options}
    if rebound:e['evidence_id']='Enew-request-id'
    return data,[e]


@pytest.mark.parametrize('text',['승인 후 보고한다.','앞\n\n뒤','가'*2501,'😀가\n조건 및 예외'])
@pytest.mark.parametrize('rebound',[False,True])
def test_only_delivered_exact_subspans(text,rebound):
    data,acquired=fixture(text,rebound);before=deepcopy(data)
    out=compact_assessment_evidence(data,acquired)
    assert data==before
    assert {s['text'] for e in out for s in e['spans']}=={o['text'] for o in data['evidence_options']}
    assert all(len(e['spans'])==1 for e in out)
    assert out==compact_assessment_evidence(data,acquired)
    # Identical duplicate options do not multiply evidence or introduce text.
    data['evidence_options']*=2
    assert compact_assessment_evidence(data,acquired)==out


@pytest.mark.parametrize('mutation',['id','text','text_hash','source_id','document_id','block_id','start_cp','end_cp','evidence_id',
    'unknown_ref','unread','foreign_document','wrong_source','changed_block','changed_bytes','truncated_read','no_card','bool_offset'])
def test_wrong_or_unread_option_cannot_become_delivery(mutation):
    data,acquired=fixture('승인 후 보고한다.')
    o=data['evidence_options'][0]
    if mutation in ('start_cp','end_cp'):o[mutation]+=1
    elif mutation in o:o[mutation]='wrong'
    elif mutation=='unknown_ref':data['sources'][0]['evidence_refs']=[]
    elif mutation=='unread':acquired=[]
    elif mutation=='foreign_document':acquired[0]['document_id']='foreign'
    elif mutation=='wrong_source':acquired[0]['source_id']='other'
    elif mutation=='changed_block':acquired[0]['spans'][0]['block_id']='other'
    elif mutation=='changed_bytes':acquired[0]['spans'][0]['text']='X'*len(o['text'])
    elif mutation=='truncated_read':acquired[0]['spans'][0]['end_cp']-=1
    elif mutation=='no_card':data['sources'][0]['source_id']='other'
    elif mutation=='bool_offset':o['start_cp']=True
    with pytest.raises(ContractError):compact_assessment_evidence(data,acquired)


def test_metadata_and_saved_inventory_never_prove_delivery():
    data,acquired=fixture();data['saved_inventory']=deepcopy(data['evidence_options']);data['evidence_options']=[]
    assert compact_assessment_evidence(data,acquired)==[]
    assert compact_assessment_evidence({'sources':[],'evidence_options':data['saved_inventory']},acquired)==[]


def test_option_subset_does_not_mark_whole_original_presented():
    data,acquired=fixture();data['evidence_options']=data['evidence_options'][:1]
    out=compact_assessment_evidence(data,acquired)
    assert len(out)==1 and out[0]['evidence_id']!=acquired[0]['evidence_id']
    assert out[0]['spans'][0]['text']==data['evidence_options'][0]['text']


# Real ASGI endpoint: direct-source path has no preceding navigation model
# presentation. Existing strict native publication must accept this assessment.
from test_main50_request_repair import tree
from test_source_span_norm import SpanTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT
from test_unified_legal_agent import ok


def test_compact_assessment_without_navigation_publishes_through_api(tmp_path,tree):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    from semantic_runtime.legal_agent import completion_contracts as cc
    class Capture(SpanTransport):
        def send_once(self,*,body,ticket):
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage')=='memory-assess':
                assert all('text' not in s for s in view['sources'])
                assert 'exact_evidence' not in view
                assert view['evidence_options']
            return super().send_once(body=body,ticket=ticket)
    gen,idx=tree;t=Capture(False,False);t.direct_note=True
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
            'completion_policy_version':cc.V8,'compact_input':True}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=t,
        memory_identity=lambda _:{'user_id':'u','team_id':'t','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'delivery','request_id':'r1'}
        out=ok(api.post('/v1/rag/ask',json=body));calls=len(t.phases)
        assert '승인 후 보고한다.' in out['answer']['text']
        again=ok(api.post('/v1/rag/ask',json=body))
        assert again['answer']==out['answer'] and len(t.phases)==calls
