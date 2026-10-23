from conftest import term_glossary
"""Grounding/preservation and actual native gateway streaming contracts."""
from copy import deepcopy
import json
import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import narrative_answer as n, completion_contracts as cc
from semantic_runtime.legal_agent.answer_stream import capture
from semantic_runtime.legal_agent.errors import ContractError, ProposalError, TransportError
from test_source_span_norm import accepted, proposal, SpanTransport
from test_main50_request_repair import tree
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_unified_legal_agent import ok

def assessment():
    return accepted(proposal(),[{'id':'S1','source_id':'s','text':'신고할 수 있다.'}])

def draft(ids=('C1',)):
    return {'paragraphs':[
        {'claim_ids':list(ids),'text':'신고할 수 있습니다.'},
        {'claim_ids':list(ids),'text':'**규정의 의미**\n\n신고를 허용하는 내용이므로 반드시 신고해야 한다는 의무와 구분됩니다.'}]}

def test_preserves_accepted_claims_originals_and_limitations():
    a=assessment();a['limitations']=['일부 원문은 확인하지 못했습니다.']
    before=deepcopy(a);p=n.plan(a,draft());out=cc.compose(a,p)
    cc.verify_composition(a,out)
    assert a==before and out['claims']==a['claims']
    assert out['limitations']==a['limitations'] and a['limitations'][0] in out['text']
    assert out['text'].startswith('신고할 수 있습니다.')
    bad=deepcopy(out);bad['text']+=' 부가 의무'
    with pytest.raises(ContractError):cc.verify_composition(a,bad)
    bad=deepcopy(out);bad['claims'][0]['quote']='원문 변경'
    with pytest.raises(ContractError):cc.verify_composition(a,bad)

def test_coverage_and_unknown_references_cannot_publish():
    with pytest.raises(ProposalError,match='every accepted'):n.checked(draft(),['C1','C2'])
    with pytest.raises(ValidationError):n.checked(draft(['private']),['C1'])
    with pytest.raises((ProposalError,ValidationError)):n.checked(draft(['C1','C1']),['C1'])
    bad=draft();bad['paragraphs'].append(deepcopy(bad['paragraphs'][0]))
    with pytest.raises(ProposalError):n.checked(bad,['C1'])

def test_only_selected_exact_originals_can_enter_writing_call():
    a=assessment();sources=[{'source_id':'s','text':'신고할 수 있다.','document_name':'모의법','heading':'제1조'}]
    out=n.input_data('모의 질문',a,sources,'paragraphs')
    assert out['sources'][0]['text']=='신고할 수 있다.'
    assert out['accepted_claims'][0]['claim_id']=='C1'
    with pytest.raises(ContractError):n.input_data('q',a,[{**sources[0],'text':'다른 원문'}],'paragraphs')
    with pytest.raises(ContractError):n.input_data('q',a,[],'paragraphs')

@pytest.mark.parametrize('ascii_output',[True,False])
@pytest.mark.parametrize('width',[1,7,43])
def test_paragraph_stream_keeps_unicode_markdown_and_hides_ids(ascii_output,width):
    value=draft();value['paragraphs'][1]['text']+='\n\n| 구분 | 의미 |\n|---|---|\n| 허용 | 선택 가능 😀 |'
    raw=json.dumps(value,ensure_ascii=ascii_output);sent=[];projection=n.ParagraphStream(sent.append,['C1'])
    for start in range(0,len(raw),width):projection.feed(raw[start:start+width])
    assert ''.join(sent)=='\n\n'.join(p['text'] for p in value['paragraphs'])
    assert len(sent)==2 and 'claim_ids' not in ''.join(sent)

def test_stream_waits_for_references_but_emits_before_later_paragraph():
    sent=[];p=n.ParagraphStream(sent.append,['C1'])
    p.feed('{"paragraphs":[{"text":"검증한 첫 문단","claim_ids":')
    assert not sent
    p.feed('["C1"]},')
    assert sent==['검증한 첫 문단'] and p.emitted
    with pytest.raises(ValidationError):p.feed('{"claim_ids":["foreign"],"text":"반출 금지"}')
    assert sent==['검증한 첫 문단']

def test_invalid_reference_never_emits_its_text():
    sent=[];p=n.ParagraphStream(sent.append,['C1'])
    with pytest.raises(ValidationError):p.feed('{"paragraphs":[{"text":"미검증 본문","claim_ids":["foreign"]}')
    assert sent==[]

class RichTransport(SpanTransport):
    def __init__(self,tokens,fail=False):
        super().__init__();self.tokens=tokens;self.fail=fail;self.compose_calls=0;self.streamed=False
    def send_once(self,*,body,ticket):
        v=json.loads(body['messages'][1]['content'])['view']
        if v.get('source_stage')==n.PHASE:
            self.compose_calls+=1;self.phases.append(n.PHASE)
            return wire(draft(v['answer_claim_ids']))
        return super().send_once(body=body,ticket=ticket)
    def send_stream_once(self,*,body,ticket,on_content):
        v=json.loads(body['messages'][1]['content'])['view']
        assert v['source_stage']==n.PHASE and body['stream'] is True
        assert body['response_format']['json_schema']['name']==n.SCHEMA
        self.compose_calls+=1;self.phases.append(n.PHASE);self.streamed=True
        value=draft(v['answer_claim_ids']);value['paragraphs'][0]['text']='승인을 받은 후 보고해야 합니다.'
        value['paragraphs'][1]['text']='**절차의 의미**\n\n승인과 보고의 순서를 구분하여 설명합니다.'
        first=json.dumps(value['paragraphs'][0],ensure_ascii=False)
        on_content('{"paragraphs":['+first)
        assert self.tokens and self.tokens[0]['text']==value['paragraphs'][0]['text']
        if self.fail:raise TransportError('synthetic interrupted composition',unknown=True,retryable=True)
        on_content(','+json.dumps(value['paragraphs'][1],ensure_ascii=False)+']}')
        return wire(value)

@pytest.mark.parametrize('fail',[False,True])
def test_native_api_uses_streaming_compose_and_preserves_publication(tmp_path,tree,fail):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    gen,idx=tree;tokens=[];transport=RichTransport(tokens,fail)
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,'final_review_enabled':False,
        'answer_presentation':n.VERSION,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,
        'completion_contract':True,'completion_policy_version':cc.V8,'compact_input':True}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=transport,
        memory_identity=lambda _:{'user_id':'u','team_id':'test_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'rich','request_id':'r1'}
        with capture('r1',tokens.append):response=api.post('/v1/rag/ask',json=body)
        assert transport.streamed and transport.compose_calls==1 and tokens, (response.status_code,response.text,transport.phases)
        if fail:
            assert response.status_code!=200
            return
        out=ok(response)
        assert out['answer']['text']==''.join(t['text'] for t in tokens)
        assert out['answer']['claims'][0]['text']!=out['answer']['text']
        assert out['assembly']['term_agent']['text_integrity']=='SOURCE_BOUND_NARRATIVE'
        assert len(out['assembly']['term_agent']['case']['judgment_refs'])==7
        again=ok(api.post('/v1/rag/ask',json=body))
        assert again['answer']==out['answer'] and transport.compose_calls==1
