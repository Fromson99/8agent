"""Prospective token boundary, native API and GENOS R4 consumer contracts."""
import asyncio, importlib.util, json, os
from pathlib import Path
import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import narrative_answer as n, completion_contracts as cc
from semantic_runtime.legal_agent.answer_stream import capture
from semantic_runtime.legal_agent.errors import ProposalError, TransportError
from test_narrative_answer import RichTransport, draft
from test_main50_request_repair import tree
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_unified_legal_agent import ok

TEXTS=['신고할 수 있습니다. 다음 문장을 계속 작성합니다.','**핵심 답변**\n\n조건과 의무를 구분합니다.','**확인 항목**\n\n- 첫째 항목\n- 둘째 항목','| 구분 | 내용 |\n|---|---|\n| 허용 | 선택 가능 😀 |','```txt\n한글 ~ \\" 이스케이프\n```']
@pytest.mark.parametrize('text',TEXTS)
@pytest.mark.parametrize('ascii_output',[False,True])
@pytest.mark.parametrize('width',[1,2,7,43])
def test_every_fragment_reconstructs_identical_text_without_waiting_for_paragraph(text,ascii_output,width):
    sent=[];p=n.TokenStream(sent.append,['C1'])
    p.feed('{"paragraphs":[{"claim_ids":["C1"],"text":"')
    escaped=json.dumps(text,ensure_ascii=ascii_output)[1:-1]
    for at in range(0,len(escaped),width):p.feed(escaped[at:at+width])
    assert ''.join(sent)==text and p.emitted
    assert not p.validation.rows  # paragraph/string have not ended
    p.feed('"}]}')
    assert ''.join(sent)==text and len(p.validation.rows)==1

def test_partial_sentence_leaves_on_each_feed_not_next_feed():
    out=[];p=n.TokenStream(out.append,['C1'])
    p.feed('{"paragraphs":[{"claim_ids":["C1"],"text":"')
    for delta in ('승인을',' 받은 후',' 보고해야',' 합니다.'):
        before=len(out);p.feed(delta)
        assert out[before:]==[delta]
    p.feed('"},{"claim_ids":["C1"],"text":"다음')
    assert out[-1]=='\n\n다음'
    p.feed(' 문단"}]}')
    assert ''.join(out)=='승인을 받은 후 보고해야 합니다.\n\n다음 문단'

@pytest.mark.parametrize('prefix',['{"claim_ids":["foreign"],"text":"','{"claim_ids":[],"text":"','{"claim_ids":["C1","C1"],"text":"','{"text":"'])
def test_unbound_metadata_never_emits_text(prefix):
    out=[];p=n.TokenStream(out.append,['C1'])
    with pytest.raises((ProposalError,ValidationError)):
        p.feed('{"paragraphs":['+prefix+'미검증')
    assert not out

def test_duplicate_text_field_fails_after_partial_emission():
    out=[];p=n.TokenStream(out.append,['C1'])
    p.feed('{"paragraphs":[{"claim_ids":["C1"],"text":"첫 답변')
    with pytest.raises(ProposalError):p.feed('","text":"대체 답변')
    assert ''.join(out)=='첫 답변'

class TokenTransport(RichTransport):
    def send_stream_once(self,*,body,ticket,on_content):
        v=json.loads(body['messages'][1]['content'])['view']
        assert v['source_stage']==n.PHASE and body['stream'] is True
        self.compose_calls+=1;self.phases.append(n.PHASE);self.streamed=True
        value=draft(v['answer_claim_ids'])
        value['paragraphs'][0]['text']='승인을 받은 후 보고해야 합니다.'
        value['paragraphs'][1]['text']='**절차의 의미**\n\n승인과 보고를 구분합니다.'
        on_content('{"paragraphs":[{"claim_ids":'+json.dumps(v['answer_claim_ids'])+',"text":"')
        for delta in ('승인을',' 받은 후',' 보고해야',' 합니다.'):
            before=len(self.tokens);on_content(delta)
            assert [t['text'] for t in self.tokens[before:]]==[delta]
            if self.fail=='disconnect':raise TransportError('synthetic mid-token disconnect',unknown=True,retryable=True)
        if self.fail=='invalid':
            on_content('","text":"다른 답')
            raise AssertionError('duplicate text must fail')
        on_content('"},'+json.dumps(value['paragraphs'][1],ensure_ascii=False)+']}')
        return wire(value)

@pytest.mark.parametrize('fail',[False,'disconnect','invalid'])
def test_native_gateway_emits_before_sentence_and_never_retries_partial_answer(tmp_path,tree,fail):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    gen,idx=tree;tokens=[];transport=TokenTransport(tokens,fail)
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,'final_review_enabled':False,'answer_presentation':n.VERSION,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,'completion_policy_version':cc.V8,'compact_input':True}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=transport,memory_identity=lambda _:{'user_id':'u','team_id':'t','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'token','request_id':'token-r1'}
        with capture('token-r1',tokens.append):response=api.post('/v1/rag/ask',json=body)
        assert transport.streamed and transport.compose_calls==1 and tokens
        if fail:assert response.status_code!=200;return
        out=ok(response)
        assert out['answer']['text']==''.join(t['text'] for t in tokens)
        assert out['assembly']['term_agent']['narrative_presentation']['streaming']=='text-deltas-during-generation'
        again=ok(api.post('/v1/rag/ask',json=body));assert again['answer']==out['answer'] and transport.compose_calls==1

@pytest.mark.parametrize('editor',['current','r4'])
def test_actual_workflow_forwards_partial_sentence_immediately_and_finishes_once(editor):
    # Root resolution is explicit for the immutable existing editor fixture.
    workspace=Path(os.environ['LAWRAG_TOKEN_TEST_REPOSITORY']) if os.getenv('LAWRAG_TOKEN_TEST_REPOSITORY') else next(p for p in Path(__file__).resolve().parents if (p/'06_TOOLS/EXPERIMENTS/adr_0770').is_dir())
    path=ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py' if editor=='current' else workspace/'08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r4/genos_rag_chat.py'
    spec=importlib.util.spec_from_file_location('token_workflow_'+editor,path);w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    async def check():
        d=w._ChatProgress({'socketIOClientId':'synthetic'});d.enabled=True;d.sid='synthetic';sent=[]
        async def emit(name,value,room):sent.append((name,value))
        d.emit=emit
        parts=['승인을',' 받은 후',' 보고해야',' 합니다.']
        for i,delta in enumerate(parts):
            before=len(sent)
            await d.answer_delta({'schema_version':'rag-answer-delta-v1','seq':i+1,'text':delta})
            assert sent[before:]==[('token',delta)]
        await d.finish(''.join(parts))
        assert ''.join(x for k,x in sent if k=='token')==''.join(parts)
        assert sent[-1]==('end','end')
    asyncio.run(check())
