"""Regression for photographed comparison output, including actual SSE consumers."""
import asyncio
from copy import deepcopy
import json

import pytest
from markdown_it import MarkdownIt
from semantic_runtime.chat_adapter import views
from semantic_runtime.legal_agent.answer_stream import capture, current_sink, suppress
from semantic_runtime.workflow_bridge import Services


def answer():
    ident='E'+'c'*32
    side={'status':'CONFIRMED','text':'승인 후 보고한다. | 예외 <명시>',
          'citations':[{'evidence':ident,'quote':'승인 후 보고한다.'}], 'dependencies':[],
          'scope_sufficient':False,'missing':'예외 조문 미확인','alternatives':[]}
    return {'response_schema':'workflow-result-v1','workflow_id':'risk_team_compare_workflow',
        'status':'partial','run_id':'a'*32,'request_id':'req',
        'answer':{'text':'LLM이 검토한 1개 비교 항목의 결과입니다.\n기준일: 미지정 — 현재 유효성 미확인\n'+ident},
        'report':{'scope':{'issues':[{'id':'i1','label':'승인 기준'}]},
            'basis':{'pairs':[{'pair_id':'items-opaque','issue_id':'i1','basis_relation':'CONTENT_ONLY'}]},
            'rows':[{'pair_id':'items-opaque','verdict':'DEFERRED','difference':'추가 확인 필요','reason':'조건을 모두 확인하지 못했습니다.'}]},
        'comparison_items':{'items':[{'issue_id':'i1','field':'obligation','internal':deepcopy(side),
                                      'external':deepcopy(side),'difference':'같은 의무 문구'}]},
        'assembly':{'term_agent':{'source_bundle':{'schema_version':'workflow-source-v1','sources':[
            {'selection_id':ident,'document_name':'모의규정','coordinate_label':'제1조','content_read':True}]}}},
        'unresolved':['i1 / 의무 — 항목 확인 미완료']}


def test_readable_table_has_real_html_cells_and_no_internal_ids():
    body=answer();before=deepcopy(body);w=views()
    text=w.render(body);shown=w._for_markdown(text)
    html=MarkdownIt('commonmark',{'html':True}).enable('table').render(shown)
    assert html.count('<table>')==1 and html.count('<th>')==4
    assert '<th>확인 내용</th>' in html and '<th>해석</th>' in html
    for value in ('모의규정','제1조','승인 후 보고한다.','판정 보류','예외 조문 미확인','현재 유효성 미확인'):assert value in shown
    assert 'items-opaque' not in shown and 'E'+'c'*32 not in shown and 'i1 /' not in shown
    assert '<명시>' not in shown and '&lt;명시&gt;' in shown
    assert body==before


def test_verified_answer_chunks_match_final_public_view_and_children_cannot_write():
    body=answer();events=[];service=object.__new__(Services)
    with capture('req',events.append):
        with suppress():assert current_sink() is None
        assert service.deliver(body) is body
    assert len(events)>5
    assert ''.join(e['text'] for e in events)==views()._public_answer_text(body)
    assert [e['seq'] for e in events]==list(range(1,len(events)+1))
    async def consume():
        display=views()._ChatProgress({'socketIOClientId':'fixture'});sent=[]
        async def send(kind,value):sent.append((kind,value))
        display._send=send
        for event in events:await display.answer_delta(event)
        await display.finish(views()._for_markdown(views().render(body)))
        return ''.join(value for kind,value in sent if kind=='token')
    assert asyncio.run(consume())==views()._for_markdown(views().render(body))


def test_failed_or_already_started_delivery_does_not_append_a_new_answer():
    from semantic_runtime.legal_agent.errors import ContractError
    service=object.__new__(Services);events=[]
    with capture('req',events.append):
        service.deliver({**answer(),'status':'failed'});assert events==[]
        current_sink()('partial')
        with pytest.raises(ContractError):service.deliver(answer())
    assert [e['text'] for e in events]==['partial']


def test_table_and_code_preserved_without_changing_prose_spacing():
    w=views();table='| 항목 | 내규 | 외규 |\n|---|---|---|\n| 값 | 1 | 2 |'
    assert w._for_markdown(table)==table
    assert w._for_markdown('첫 문장\n다음 문장')=='첫 문장\n\n다음 문장'
    code='```text\n| a |\n| b |\n```'
    assert w._for_markdown(code)==code


def test_field_conflict_and_row_specific_uncertainty_remain_visible():
    body=answer();row=body['report']['rows'][0]
    row['unresolved']=['산식 적용 대상 추가 확인']
    row['dimensions']=[{'name':'period','status':'UNKNOWN','reason':'평균 산정 기간 미확인'}]
    body['comparison_items']['items'][0]['internal']['status']='CONFLICT'
    text=views()._public_answer_text(body)
    for value in ('산식 적용 대상 추가 확인','평균 산정 기간 미확인','확인 상태: 상충'):
        assert value in text


def test_multiple_issues_share_one_table_and_sources_have_readable_paragraphs():
    body=answer();w=views();ident='E'+'c'*32
    body['report']['scope']['issues'].append({'id':'i2','label':'보고 시점'})
    item=deepcopy(body['comparison_items']['items'][0]);item.update(issue_id='i2',field='period')
    item['internal']['text']='승인을 받는다.\n\n담당 부서에 보고한다. 예외는 별도로 확인한다.'
    body['comparison_items']['items'].append(item)
    source=body['assembly']['term_agent']['source_bundle']['sources'][0]
    source.update(side='internal',document_name='internal > risk_team > 관리 폴더 > 모의내규(20260319)')
    outside=deepcopy(source);outside.update(selection_id='E'+'d'*32,side='external',
        document_name='external > risk_team > law > 모의감독규정 > 별표서식 > [별표 25] 산정기준',coordinate_label='제2항')
    body['assembly']['term_agent']['source_bundle']['sources'].append(outside)
    for item in body['comparison_items']['items']:
        item['external']['citations']=[{'evidence':outside['selection_id'],'quote':'승인 후 보고한다.'}]
    before=deepcopy(body);text=w._for_markdown(w.render(body))
    html=MarkdownIt('commonmark',{'html':True}).enable('table').render(text)
    assert html.count('<table>')==1 and html.count('<th>')==4 and html.count('<td>')==8
    assert '승인을 받는다.<br><br>담당 부서에 보고한다.<br><br>예외는 별도로 확인한다.' in text
    for value in ('〔내규 1〕','〔외규 1〕','모의내규(20260319)','모의감독규정 · 별표서식 ·', '산정기준', '위치: 제2항'):
        assert value in text
    assert 'risk_team' not in text and '관리 폴더' not in text
    assert ident not in text and outside['selection_id'] not in text
    assert '의무의 차이' not in text and body==before


def test_source_versions_and_same_names_keep_separate_references_without_guessing_side():
    body=answer();source=body['assembly']['term_agent']['source_bundle']['sources'][0]
    newer=deepcopy(source);newer.update(selection_id='different-version',version='2026-10-01')
    source['version']='2025-01-01'
    body['assembly']['term_agent']['source_bundle']['sources'].append(newer)
    records,ordered=views()._report_sources(body)
    assert len(records)==2 and [r['label'] for r in ordered]==['출처 1','출처 2']
    text=views()._sources(body)
    assert '2025-01-01' in text and '2026-10-01' in text and '**내규**' not in text


@pytest.mark.parametrize('items',[None,[]])
def test_old_or_partial_comparison_still_has_four_columns_without_invented_summaries(items):
    body=answer();body['comparison_items']={'items':items}
    text=views()._public_answer_text(body)
    assert text.count('| 확인 내용 | 내규 | 외규 | 해석 |')==1
    assert '항목별 요약 미확보' in text and '판정 보류' in text


def test_changed_final_report_is_not_appended_as_a_second_answer():
    w=views();text=w._for_markdown(w._public_answer_text(answer()))
    async def consume():
        display=w._ChatProgress({'socketIOClientId':'fixture'});sent=[]
        async def emit(kind,value,**kwargs):sent.append((kind,value))
        display.emit=emit
        for seq,line in enumerate(w._public_answer_text(answer()).splitlines(keepends=True),1):
            await display.answer_delta({'schema_version':'rag-answer-delta-v1','seq':seq,'text':line})
        with pytest.raises(ValueError,match='delivered prefix'):
            await display.finish('다른 표시 형식\n\n'+text)
        await display.finish('조회 번호: fixture',failed=True)
        return ''.join(v for k,v in sent if k=='token')
    shown=asyncio.run(consume())
    assert shown.count('| 확인 내용 | 내규 | 외규 | 해석 |')==1
    assert '다른 표시 형식' not in shown and '답변 전달 미완료' in shown


@pytest.mark.parametrize('explicit',[False,True])
def test_workflow_entry_reports_delivery_mismatch_without_reexecuting_or_duplicating(monkeypatch,explicit):
    w=views();calls=[];sent=[]
    monkeypatch.setattr(w,'_post_code_serving',lambda _: {'status':200,'body':{}})
    async def send(self,kind,value):sent.append((kind,value))
    monkeypatch.setattr(w._ChatProgress,'_send',send)
    async def received(question,data,display,**kwargs):
        calls.append(data['request_id'])
        await display.answer_delta({'schema_version':'rag-answer-delta-v1','seq':1,'text':'다른 리비전의 일부 답변'})
        return answer()
    monkeypatch.setattr(w,'_stream_code_serving',received)
    data={'question':'대사: 모의 질문','request_id':'req','socketIOClientId':'fixture'}
    if explicit:data.update(API_TYPE='WORKFLOW_RUN',session_id='s',team_id='risk_team')
    result=asyncio.run(w.run(data))
    assert result['answer_status']=='failed' and len(calls)==1
    shown=''.join(v for k,v in sent if k=='token')
    assert '답변 전달 미완료' in shown and '| 확인 내용 |' not in shown


def test_status_lookup_uses_the_same_report_renderer(monkeypatch):
    w=views();body=answer()
    monkeypatch.setattr(w,'_post_code_serving',lambda _: {'status':200,'body':body})
    result=asyncio.run(w.run({'API_TYPE':'WORKFLOW_STATUS','request_id':'req',
        'session_id':'s','team_id':'risk_team','run_id':'a'*32}))
    assert result['text']==w._for_markdown(w.render(body))


@pytest.mark.parametrize('mismatch',[False,True])
def test_native_chat_sse_reports_render_mismatch_without_second_table(mismatch):
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'08_DEPLOYMENT/GENOS/stream_app.py'
    spec=importlib.util.spec_from_file_location('native_report_stream_contract',path)
    stream_app=importlib.util.module_from_spec(spec);spec.loader.exec_module(stream_app)
    from semantic_runtime.chat_adapter import stream_display
    w=views();body=answer();calls=[]
    async def execute(data,on_progress,on_answer):
        calls.append(data['request_id'])
        for seq,line in enumerate(w._public_answer_text(body).splitlines(keepends=True),1):
            on_answer({'schema_version':'rag-answer-delta-v1','request_id':data['request_id'],
                       'seq':seq,'text':line})
        return {'code':0,'data':{'text':('다른 리비전\n\n' if mismatch else '')+
            w._for_markdown(w.render(body)),'answer_status':'partial'}}
    async def consume():
        response=await stream_app.stream_response({'request_id':'native-report-check'},execute,display=stream_display())
        frames=[]
        async for raw in response.body_iterator:
            if raw.startswith('data: '):frames.append(json.loads(raw[6:]))
        return frames
    frames=asyncio.run(consume())
    text=''.join(f['data'] for f in frames if f['event']=='token')
    assert text.count('| 확인 내용 | 내규 | 외규 | 해석 |')==1
    assert len(calls)==1 and frames[-1]['event']=='result'
    assert frames[-1]['data']['answer_status']==('failed' if mismatch else 'partial')
    if mismatch:assert '답변 전달 미완료' in text and '다른 리비전' not in text
    else:assert text==w._for_markdown(w.render(body))
