"""Photo regressions: final citations, compact originals and identical consumers."""
import asyncio
import json
from copy import deepcopy
from html.parser import HTMLParser

import pytest
from markdown_it import MarkdownIt

import test_comparison_display_scope as fixture
import test_comparison_ten_minute as deadline_fixture
from workflow.contracts import digest, WorkflowError
from workflow.risk_team_compare_workflow import concept_report, finalize
from semantic_runtime.chat_adapter import views

tree=fixture.tree


class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]

    def handle_data(self, value):
        self.parts.append(value)


def example():
    state, body, by, ctx = fixture.example()
    names = {'in':'internal > risk_team > 저장폴더 > 모의내규(20260319)',
             'route-1':'external > risk_team > law > 모의외규 > 별표서식 > 별표 10',
             'route-2':'external > risk_team > law > 모의외규 > 별표서식 > 별표 10'}
    for ident, source in by.items():
        source['metadata']['document_name'] = names[ident]
    # Reproduce a stopped field review while the finalizer can use both sides.
    for item in body['comparison_items']['items']:
        for side in ('internal', 'external'):
            item[side].update(text='', citations=[], missing='조사 또는 항목 검토 미완료')
    body['unreviewed_sources'] = [{'evidence_id':i, 'side':e['side']} for i,e in by.items()]
    body.update(status='partial', workflow_id='risk_team_compare_workflow',
                response_schema='workflow-result-v1', request_id='req')
    body = concept_report.apply(ctx, state, body, by)
    paragraphs = [{'text':'내규와 외규는 승인 후 보고하도록 정합니다.',
        'citations':[{'evidence':i, 'quote':by[i]['text']} for i in ('in','route-1','route-2')]}]
    value = {'paragraphs':paragraphs, 'unresolved':['예외 적용 범위는 추가 확인이 필요합니다.']}
    state['finalization']={'status':'COMPLETE','value':value,'value_hash':digest(value)}
    return state, body, by


def test_final_text_and_sources_share_citations_without_inventing_concept_edges():
    state, body, by = example()
    old_rows = deepcopy(body['comparison_table']['rows'])
    audit = deepcopy((state, by, body['comparison_items']))
    result = finalize.apply(state, body, by)
    table = result['comparison_table']
    assert table['rows'] == old_rows  # Stopped field review stays in the audit.
    assert table['final_answer_basis'] == 'FINAL_PARAGRAPH_CITATIONS'
    assert len(table['final_answer'][0]['external']) == 1
    assert table['final_answer'][0]['external'][0]['selection_ids'] == ['route-1','route-2']
    assert (state, by, body['comparison_items']) == audit
    assert result['status']=='partial' and result['answer']['answer_status']=='PARTIAL'
    text = result['answer']['text']
    assert '함께 확인한 원문' not in text  # Aliased routes are already shown above.
    for hidden in ('미완료','외규 원문 미선택','항목별 해석','risk_team','저장폴더','route-1','route-2'):
        assert hidden not in text
    for shown in ('〔내규 1〕','〔외규 1〕','모의외규 · 별표서식 · 별표 10','예외 적용 범위',
                  '직접 연결이나 부합이 확정되는 것은 아닙니다'):
        assert shown in text
    assert digest({k:v for k,v in table.items() if k!='content_hash'})==table['content_hash']
    assert views()._sources(result)==''  # No second list with conflicting numbers.
    assert views().render(result)==text


def test_single_side_final_paragraph_does_not_borrow_other_side_from_stale_table():
    state, body, by = example()
    value=state['finalization']['value']
    value['paragraphs'][0]['citations']=[{'evidence':'route-1','quote':by['route-1']['text']}]
    state['finalization']['value_hash']=digest(value)
    result=finalize.apply(state,body,by)
    row=result['comparison_table']['final_answer'][0]
    assert not row['internal'] and row['external']
    assert '이 설명은 외규 원문을 근거로 작성했습니다.' in result['answer']['text']
    assert '함께 확인한 원문' in result['answer']['text']
    assert '모의내규' in result['answer']['text']


@pytest.mark.parametrize('defect',['hash','quote','source','published'])
def test_final_display_never_bypasses_original_binding(defect):
    state, body, by = example()
    value=state['finalization']['value']
    if defect=='quote':value['paragraphs'][0]['citations'][0]['quote']='없는 원문'
    if defect=='source':value['paragraphs'][0]['citations'][0]['evidence']='outside'
    if defect=='published':body['evidence_refs'].remove('route-1')
    if defect=='hash':value['paragraphs'][0]['text']='변조'
    else:state['finalization']['value_hash']=digest(value)
    with pytest.raises((ValueError,WorkflowError)):
        finalize.apply(state,body,by)


def test_group_many_fragments_by_document_keep_all_literal_quotes_and_distinct_versions():
    rows=[]
    for number in range(90):
        e=fixture.fixture.source('E'+format(number,'032x'),'external')
        e['document_id']='one-law'; e['metadata']['document_name']='external > risk_team > law > 모의규정'
        e['metadata']['heading']='별표 10'
        text=f'{number} | 값 <원문> & [1] 1~3 \\_ 미완료\n다음 줄'
        rows.append(concept_report.source_row(e,text))
    newer=deepcopy(rows[0]);newer.update(generation_id='g2',source_artifact_hash='new')
    rows.append(newer)
    table={'question':'출처 표시','as_of':None,'rows':[],'unresolved':[],
           'unreviewed_originals':rows,'display_version':concept_report.DISPLAY_VERSION}
    concept_report.label_sources(table)
    raw=concept_report.render(table)
    assert {r['label'] for r in rows}=={'외규 1','외규 2'}
    assert raw.count(' — 원문</strong></p>')==2
    assert raw.count('<blockquote ')==91 and ' open' not in raw
    assert views()._for_markdown(raw)==raw
    assert views()._without_inline_reference_numbers(raw)==raw
    assert 'risk_team' not in raw and 'E'+'0'*32 not in raw
    parsed=Text();parsed.feed(MarkdownIt('commonmark',{'html':True}).render(raw))
    content=''.join(parsed.parts)
    assert '89 | 값 <원문> & [1] 1~3 \\_ 미완료' in content
    assert '다음 줄' in content  # Only prose statuses change; originals stay literal.


@pytest.mark.parametrize('step',[1,17,160])
def test_literal_html_survives_split_stream_and_matches_saved_final(step):
    state, body, by=example()
    value=state['finalization']['value']
    value['paragraphs'][0]['text'] += ' [C4][C60][C61]'
    state['finalization']['value_hash']=digest(value)
    text=finalize.apply(state,body,by)['answer']['text']
    assert '[C4]' not in text and '[C60]' not in text
    async def consume():
        w=views();display=w._ChatProgress({'socketIOClientId':'fixture'});sent=[]
        async def send(kind,value):
            if kind=='token':sent.append(value)
        display._send=send
        for seq,start in enumerate(range(0,len(text),step),1):
            await display.answer_delta({'schema_version':'rag-answer-delta-v1',
                'seq':seq,'text':text[start:start+step]})
        await display.finish(w._for_markdown(w.render(body)))
        return ''.join(sent)
    assert asyncio.run(consume())==text


def test_model_markup_is_text_and_cannot_open_source_details_or_run_html():
    state,body,by=example()
    value=state['finalization']['value']
    value['paragraphs'][0]['text']='<script>alert(1)</script><details open>변조</details>'
    state['finalization']['value_hash']=digest(value)
    text=finalize.apply(state,body,by)['answer']['text']
    assert '<script>' not in text and '<details open>' not in text
    assert '&lt;script&gt;' in text


def test_packet_citation_markers_do_not_leak_from_final_prose_or_change_audit():
    state,body,by=example()
    value=state['finalization']['value']
    markers='[C4][C60][C61][C62][C63][C64][C65][C66][C67] [C129,C130] [ C131 ; C132 ]'
    value['paragraphs'][0]['text']='승인 후 보고합니다. '+markers+' 조건은 추가 확인해야 합니다.'
    value['unresolved']=['예외는 추가 확인해야 합니다. [C148]']
    state['finalization']['value_hash']=digest(value)
    before=deepcopy((state,by))
    result=finalize.apply(state,body,by)
    text=result['answer']['text']
    assert '[C' not in text and '[ C' not in text
    assert '승인 후 보고합니다.' in text and '조건은 추가 확인해야 합니다.' in text
    assert '예외는 추가 확인해야 합니다.' in text
    assert '〔내규 1〕' in text and '〔외규 1〕' in text
    assert result['comparison_table']['final_answer'][0]['text']==value['paragraphs'][0]['text']
    assert (state,by)==before
    assert views().render(result)==text
    assert concept_report.render(result['comparison_table'])==text


def test_packet_citation_cleaning_preserves_literal_quotes_questions_and_other_codes():
    state,body,by=example()
    table=finalize.apply(state,body,by)['comparison_table']
    table['question']='[C4]와 [C60]은 무엇인가요?'
    table['final_answer'][0]['internal'][0]['quote']='원문 분류 [C4][C60] 및 각주 [1]'
    table['final_answer'][0]['text']='분류 C4, C60, [C4A], [제4조], [1] 보존. [C4][C60]'
    table['answer_unresolved']=['검토 [C148] 필요']
    before=deepcopy(table)
    text=concept_report.render(table)
    assert '질문: [C4]와 [C60]은 무엇인가요?' in text
    assert '원문 분류 [C4][C60] 및 각주 [1]</blockquote>' in text
    assert '분류 C4, C60, [C4A], [제4조], [1] 보존.' in text
    assert '보존. [C4]' not in text and '[C148]' not in text
    assert table==before


@pytest.mark.parametrize('brackets', ['[]', '()', '（）'])
def test_packet_citations_through_service_stream_saved_result_and_duplicate(tmp_path,tree,monkeypatch,brackets):
    app,transport,_=deadline_fixture.application(tmp_path,tree,monkeypatch,'review_deadline')
    original=transport.send_once
    def send_once(*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view']
        if view.get('source_stage',view['phase'])=='workflow-finalize':
            transport.final_calls+=1
            refs=[{'citation_id':s['citation_options'][0]['citation_id']} for s in view['sources']]
            markers=''.join(brackets[0]+r['citation_id']+brackets[1] for r in refs)
            return deadline_fixture.wire({'paragraphs':[{'text':'승인 후 보고합니다. '+markers,'citations':refs}],
                'unresolved':['적용 예외는 추가 확인해야 합니다. '+markers]})
        return original(body=body,ticket=ticket)
    transport.send_once=send_once
    service=deadline_fixture.load('readable_citation_service','service.py')
    service._APP=app;service._BINDING={'mode':'isolated-contract-test'}
    request={'API_TYPE':'RAG_ASK',**deadline_fixture.BODY}
    from semantic_runtime.legal_agent.answer_stream import capture
    events=[]
    with capture(request['request_id'],events.append):
        response=asyncio.run(service.service({},request))
    assert response['status']==200,response
    result=response['body'];text=result['answer']['text']
    assert result['finalization']['status']=='COMPLETE'
    assert brackets[0]+'C' in result['comparison_table']['final_answer'][0]['text']
    assert brackets[0]+'C' not in text
    assert '〔내규 1〕' in text and '〔외규 1〕' in text
    assert '적용 예외는 추가 확인해야 합니다.' in text
    assert ''.join(e['text'] for e in events)==text
    rendered=views().render(result)
    # The chat consumer may append its separate judgment view after the answer.
    assert rendered.startswith(text) and brackets[0]+'C' not in rendered
    saved=asyncio.run(service.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':result['run_id'],'session_id':'s'}))
    repeated=asyncio.run(service.service({},request))
    assert saved['status']==repeated['status']==200
    assert saved['body']['answer']==repeated['body']['answer']==result['answer']
    assert transport.final_calls==1
