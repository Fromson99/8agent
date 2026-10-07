"""Code-authored display, exact source coordinates, currentness and token contract."""
import asyncio
import copy
from html.parser import HTMLParser
import json

import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.judgment_view import build, STAGES
from semantic_runtime.legal_agent.readable_log import decision_rows, render_rows, render_detail
from semantic_runtime.legal_agent.errors import ContractError
from test_genos_chat_flow import workflow
from test_unified_legal_agent import unified, ok
from test_structure_first_search import structured_generation
from test_memory_runtime_v2 import command


@pytest.fixture(autouse=True)
def current_unit_transport(monkeypatch):
    import test_unified_legal_agent as cases
    base=cases.ScriptedTransport
    class UnitTransport(base):
        def send_once(self, *, body, ticket):
            view=json.loads(body['messages'][1]['content'])['view']
            phase=view.get('source_stage',view['phase'])
            if phase in ('source-unit-triage','source-unit-review'):
                self.phases.append(phase)
                choices=[]
                if phase=='source-unit-triage' and view['units']:
                    unit=view['units'][0]
                    choices=[{'id':unit['id'],'scope':unit['read_options'][0][0],'reason':'모의 원문 확인'}]
                return cases.wire({'issues':['승인'],'choices':choices,'needs_search':False})
            if phase.startswith('source-reference-batch'):
                self.phases.append(phase)
                from test_batch_reference_navigation import decision
                return cases.wire(decision(view))
            return super().send_once(body=body,ticket=ticket)
    monkeypatch.setattr(cases,'ScriptedTransport',UnitTransport)


def sample():
    source={'source_id':'s1','document_id':'d','document_name':'모의규정',
            'heading':'제3조 제2항 제1호','text':'승인 대상은 담당자다.'}
    payloads=[{'purpose':'승인 대상 확인','concepts':['승인']},
              {'queries':['승인 대상'],'law_names':['모의규정']},
              {'selected_for_read':['s1']}, {'originals':[source]},
              {'final_ids':['s1'],'label_to_source':{'C1':'s1'},
               'decisions':[{'decision':{'issues':['승인 대상'],
                 'choices':[{'id':'C1','reason':'적용 대상 확인'}]}}]},
              {'claims':[{'text':'담당자가 승인 대상이다.','quote':'승인 대상은 담당자다.','source_id':'s1'}],'limitations':['신분 확인 필요']},
              {'claims':[],'limitations':[]}]
    parts={s:{'payload':p} for s,p in zip(STAGES,payloads)}
    case={'question_id':'g1','revision':2,'route_id':4,'judgment_refs':{
        s:{'run_id':'r1','kind':'case_stage','entity_id':'case:'+s,'version':1,
           'payload_hash':digest(parts[s]['payload']),'choice_id':i+1} for i,s in enumerate(STAGES)}}
    state={'facts':[{'name':'대상','value':'담당자'}]}
    return parts,case,state


def body():
    parts,case,state=sample()
    view=build(parts,case,state=state,run_id='r1',allowed_documents=['d'],executed=STAGES)
    return {'answer':{'text':'최종 답변.'},'assembly':{'term_agent':{'case':case,'judgment_view':view}}}


class Toggles(HTMLParser):
    def __init__(self): super().__init__();self.depth=0;self.maximum=0;self.opened=[]
    def handle_starttag(self, tag, attrs):
        if tag=='details':
            self.depth+=1;self.maximum=max(self.maximum,self.depth)
            self.opened.append('open' in dict(attrs))
    def handle_endtag(self, tag):
        if tag=='details':self.depth-=1;assert self.depth>=0


def test_nested_collapsed_toggles_exact_coordinate_actions_quote_and_diagram():
    w=workflow();b=body();text=w._for_markdown(w.render(b))
    parser=Toggles();parser.feed(text)
    assert parser.depth==0 and parser.maximum==4 and not any(parser.opened)
    assert '제3조 제2항 제1호' in text and '원문 열람' in text and '답변 근거 채택' in text
    assert '적용 대상 확인' in text and '승인 대상은 담당자다.' in text
    assert '신분 확인 필요' in text and '사용자가 제공한 현재 조건' in text
    diagram=w._judgment_mermaid(b['assembly']['term_agent']['judgment_view'])
    assert '```mermaid\n'+diagram+'\n```' in text
    assert text.index('7. 답변 작성') < text.index('```mermaid')
    assert w._for_markdown(text)==text


def test_injection_safe_html_and_fixed_mermaid_grammar():
    parts,case,state=sample()
    parts['READ']['payload']['originals'][0]['document_name']='<img src=x onerror=alert(1)>'
    parts['ASSESS']['payload']['claims'][0]['text']='</details><script>bad()</script>'
    for s in STAGES:case['judgment_refs'][s]['payload_hash']=digest(parts[s]['payload'])
    view=build(parts,case,state=state,run_id='r1',allowed_documents=['d'],executed=STAGES)
    b={'answer':{'text':'답변'},'assembly':{'term_agent':{'case':case,'judgment_view':view}}}
    w=workflow();text=w._judgment_html(b)
    assert '<img' not in text and '<script' not in text and '&lt;script&gt;' in text
    assert 'alert' not in w._judgment_mermaid(view)


def test_scope_hash_and_route_binding_fail_closed():
    parts,case,state=sample()
    view=build(parts,case,state=state,run_id='r1',allowed_documents=['other'])
    assert all(not row['data'] for row in view['stages'])
    parts['INTENT']['payload']['purpose']='tampered'
    with pytest.raises(ContractError):build(parts,case,state=state,run_id='r1',allowed_documents=['d'])
    b=body();b['assembly']['term_agent']['judgment_view']['stages'][0]['decisions']=['tampered']
    assert not workflow()._judgment_html(b)
    b=body();b['assembly']['term_agent']['case']['revision']=99
    assert not workflow()._judgment_html(b)


@pytest.mark.parametrize('reason',[None,'','없음','이유 없음','별도 이유 없음','모델이 별도 이유를 제공하지 않음'])
def test_absent_rationale_never_says_no_reason_or_invents_fixed_processing(reason):
    rows=decision_rows({'mode':'CASE','answer':'기존 사건 처리','reason':reason},{})
    text=render_rows(rows)
    assert '이유' not in text and '고정 처리' not in text
    log=render_detail('TOOL RESULT',{'tool':'read','status':'OK','reason':reason})
    assert '이유' not in log and '도구' not in log


def test_final_token_append_contains_one_complete_judgment_and_end(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI','socketio')
    w=workflow();display=w._ChatProgress({'socketIOClientId':'synthetic'})
    sent=[]
    async def emit(name,value,room):sent.append((name,value))
    display.emit=emit
    async def run():
        await display.answer_delta({'schema_version':'rag-answer-delta-v1','seq':1,'text':'최종 답변.'})
        await display.finish(w._for_markdown(w.render(body())))
    asyncio.run(run())
    text=''.join(value for name,value in sent if name=='token')
    assert text==w._for_markdown(w.render(body()))
    assert text.count('GENOS_JUDGMENT_VIEW_START')==1 and sent[-1]==('end','end')


def test_real_v6_correction_preserves_sources_but_displays_current_assessment(unified):
    _,send,transport,_,_=unified
    first=ok(send());start=first['assembly']['term_agent']['judgment_view']
    assert len(start['stages'])==7
    one=ok(send(command('FACT_UPDATE',target=first['question_id'],facts=[{'name':'대상','value':'B'}])))
    view=one['assembly']['term_agent']['judgment_view']
    assert view['question_revision']==2 and view['question_id']==first['question_id']
    assert [s['stage'] for s in view['stages'] if s['status']=='이번 요청 수행']==['ASSESS','COMPOSE']
    assert 'B' in view['stages'][5]['data'][0]['judgment']
    assert 'B' in json.dumps(view['stages'][0]['facts'],ensure_ascii=False)
    assert 'memory-assess-check' not in transport.phases
    assert workflow()._judgment_html(one)


def test_direct_chat_receives_the_same_server_generated_view(monkeypatch):
    from semantic_runtime import chat_adapter
    async def service(request):return {'status':200,'body':body()}
    monkeypatch.setenv('GENOS_RUNTIME_DIR','/tmp/synthetic')
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','0')
    monkeypatch.setattr(chat_adapter,'call_service',service)
    out=asyncio.run(chat_adapter.chat({'question':'모의 질문'}))['data']
    assert out['judgment_display_revision']=='judgment-view-20261006-r1'
    assert '```mermaid' in out['text'] and '<details' in out['text']


def test_confirmation_and_reuse_keep_actual_execution_labels(unified):
    _,send,_,_,_=unified
    first=ok(send())
    saved=ok(send(command('EXPERIENCE_CONFIRM',target=first['question_id'])))
    assert all(s['status']=='현재 판단 유지' for s in saved['assembly']['term_agent']['judgment_view']['stages'])
    reused=ok(send(command('EXPERIENCE_REUSE',document_scope_mode='AUTHORIZED',knowledge_id=saved['experience_id'],
                          task='모의승인규정 제1조의 승인 대상은?',queries=['승인'],facts=[]),session_id='other'))
    stages=reused['assembly']['term_agent']['judgment_view']['stages']
    assert [s['stage'] for s in stages if s['status']=='이번 요청 수행']==list(dict.fromkeys(reused['executed']))
    if reused['status']=='REUSED':
        assert all(s['status']=='확정 경험 연결' for s in stages[:-1])
    else:
        # The current shortcut policy can demand fresh investigation. Display
        # that actual outcome rather than calling it experience rebinding.
        assert not any(s['status']=='확정 경험 연결' for s in stages)


def test_publisher_rejects_rehashed_display_that_disagrees_with_route(unified):
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    from semantic_runtime.legal_agent.unified_publication import validate_saved
    _,send,_,_,runtime=unified
    response=ok(send())
    journal=next((runtime/'legal-agent/runs').glob('*/'+response['run_id']+'/journal.sqlite'))
    repo=UnifiedRepository(journal)
    try:
        validate_saved(repo,response)
        altered=copy.deepcopy(response)
        view=altered['assembly']['term_agent']['judgment_view']
        view['stages'][0]['decisions']=['코드 원장과 다른 설명']
        view['content_sha256']=digest({k:v for k,v in view.items() if k!='content_sha256'})
        with pytest.raises(ContractError,match='display differs'):
            validate_saved(repo,altered)
    finally:repo.close()


def test_workflow_final_result_includes_toggles_without_socket_or_model(monkeypatch):
    w=workflow()
    async def serving(question,data,display):return body()
    monkeypatch.setattr(w,'_stream_code_serving',serving)
    monkeypatch.setattr(w,'_post_code_serving',lambda request:{'status':200,'body':{'ad_active':False}})
    out=asyncio.run(w._run_once({'question':'모의 질문','request_id':'synthetic'}))
    assert out['judgment_display_revision']=='judgment-view-20261006-r1'
    assert '<details' in out['text'] and '```mermaid' in out['text']
