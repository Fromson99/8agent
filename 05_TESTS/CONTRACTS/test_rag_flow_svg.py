"""Server SVG and concise progress reach both chat transports and workflow JSON."""
import asyncio
import base64
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import pytest
from semantic_runtime import chat_adapter as adapter
from semantic_runtime.contracts import digest

ROOT = Path(__file__).resolve().parents[2]
STAGES = ['INTENT', 'PLAN', 'RECALL', 'READ', 'SELECT', 'ASSESS', 'COMPOSE']
LABELS = ['질문 이해', '검색 계획', '자료 검색', '원문 확인', '근거 선택', '적용 판단', '답변 작성']


def workflow():
    spec = importlib.util.spec_from_file_location('flow_svg_test', ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def body():
    refs = {stage: {'payload_hash': digest({'stage': stage}), 'version': 1} for stage in STAGES}
    view = {'schema_version': 'judgment-view-v1', 'question_id': 'q', 'question_revision': 1, 'route_id': 1,
            'stages': [{'id': str(i+1), 'stage': stage, 'label': LABELS[i], 'status': '이번 요청 수행',
                        'judgment_ref': refs[stage], 'data': [], 'actions': [], 'decisions': []}
                       for i, stage in enumerate(STAGES)]}
    view['stages'][0]['decisions'] = ['CASE START']
    view['stages'][3]['data'] = [{'source_id': 's1', 'document_name': '모의법', 'coordinate': '제1조', 'action': '원문 열람',
                                 'quote': 'READ는 원문에서 사용한 영문 표기다.'}]
    view['content_sha256'] = digest(view)
    return {'answer': {'text': '확인한 답변.'}, 'assembly': {'term_agent': {'judgment_view': view, 'case': {
        'question_id': 'q', 'revision': 1, 'route_id': 1, 'judgment_refs': refs}}}}


def events():
    return [{'schema_version': 'rag-progress-v1', 'kind': kind, 'label': label,
             'details': details, 'basis': {'detail_mode': 'activity'}} for kind, label, details in [
        ('candidate', '자료 검색 · 관련 법령을 찾았습니다', ['모의법 1', '모의법 2']),
        ('candidate', '자료 검색 · 본문 검색 결과', ['본문 검색어: 승인 기한']),
        ('reading', '원문 확인 · 법령 본문을 읽기 시작합니다', ['모의법 1 · 제1조']),
        ('revised', '자료 검색 단계로 돌아갑니다', ['예외 적용 근거가 부족합니다']),
        ('candidate', '자료 검색 · 본문 검색 결과', ['본문 검색어: 승인 예외']),
        ('heartbeat', '대기 중 60초', []), ('model_wait', '내부 모델 대기', [])]]


def image_xml(text):
    encoded = re.search(r'<img src="data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)"', text).group(1)
    return ET.fromstring(base64.b64decode(encoded))


def test_svg_keeps_search_and_evidence_without_duplicate_execution_trace():
    w = workflow(); raw = body(); flow = w._judgment_flow(raw, events())
    text = w._for_markdown(w.render(raw, flow=flow)); svg = image_xml(text)
    labels = ''.join(svg.itertext())
    assert '```mermaid' not in text and '<svg' not in text
    assert '승인 기한' in labels and '승인 예외' in labels and '제1조' in labels
    assert not any('data-flow-step' in node.attrib for node in svg.iter())
    assert '실제 진행 순서' not in labels and '돌아갑니다' not in labels
    assert '→' not in flow['html']
    assert '60초' not in labels and '내부 모델' not in labels
    assert flow['metadata']['node_count'] == 5 and flow['metadata']['return_count'] == 1
    assert flow['metadata']['basis'] == 'request-progress'
    assert w._for_markdown(text) == text
    assert raw == body()


def test_fallback_uses_verified_execution_labels_and_keeps_source_quote_unchanged():
    w = workflow(); raw = body(); view = raw['assembly']['term_agent']['judgment_view']
    for row in view['stages']: row['status'] = '확정 경험 연결'
    view['content_sha256'] = digest({k: v for k, v in view.items() if k != 'content_sha256'})
    flow = w._judgment_flow(raw)
    labels = ''.join(ET.fromstring(flow['svg']).itertext())
    assert 'CASE' not in labels and 'START' not in labels
    assert w._judgment_html(raw).count('확정 경험 연결') == 7
    assert flow['metadata']['basis'] == 'verified-judgment'
    assert 'READ는 원문에서 사용한 영문 표기다.' in w.render(raw, flow=flow)


def test_svg_is_escape_safe_and_has_no_script_external_reference_or_foreign_object():
    w = workflow(); raw = body(); view = raw['assembly']['term_agent']['judgment_view']
    view['stages'][3]['data'][0]['document_name'] = '</text><script>alert(1)</script>'
    view['content_sha256'] = digest({k: v for k, v in view.items() if k != 'content_sha256'})
    flow = w._judgment_flow(raw, events())
    xml = ET.fromstring(flow['svg'])
    assert set(node.tag.rsplit('}', 1)[-1] for node in xml.iter()) <= {
        'svg','title','desc','rect','text','g','path','circle',
        'defs','linearGradient','radialGradient','stop','pattern'}
    assert '</text><script>alert(1)</script>' in ''.join(xml.itertext())
    assert '<script>' not in flow['svg'] and 'foreignObject' not in flow['svg']
    assert not any(key.endswith('href') for node in xml.iter() for key in node.attrib)
    # The design uses local SVG paint servers, never network resources.
    definitions = {node.attrib['id'] for node in xml.iter() if 'id' in node.attrib}
    references = re.findall(r'url\(([^)]+)\)', flow['svg'])
    assert references and all(ref.startswith('#') and ref[1:] in definitions for ref in references)


def test_relationships_follow_exact_source_and_composed_claim_refs():
    w = workflow(); raw = body(); view = raw['assembly']['term_agent']['judgment_view']
    view['stages'][5]['data'] = [{'source_id': 's1', 'judgment': '현재 조건에서는 승인이 필요합니다.'},
                               {'source_id': 'outside', 'judgment': '연결하면 안 되는 판단'}]
    view['stages'][6]['data'] = [{'source_id': 's1', 'judgment': '현재 조건에서는 승인이 필요합니다.'}]
    view['content_sha256'] = digest({k: v for k, v in view.items() if k != 'content_sha256'})
    nodes, edges = w._flow_graph(raw, view, events())
    lookup = {node['id']: node for node in nodes}
    assert not any('연결하면 안' in node['title'] for node in nodes)
    evidence = [edge for edge in edges if edge['label'] == '판단 근거']
    assert len(evidence) == 1
    assert lookup[evidence[0]['from']]['kind'] == 'source'
    assert lookup[evidence[0]['to']]['kind'] == 'claim'
    assert len([edge for edge in edges if edge['label'] == '답변에 반영']) == 1
    # A current assessment absent from COMPOSE remains a judgment, with no
    # fabricated connection to the final answer.
    view['stages'][6]['data'] = []
    _, edges = w._flow_graph(raw, view, events())
    assert not any(edge['label'] == '답변에 반영' for edge in edges)
    view['stages'][6]['data'] = [{'source_id': 'different', 'judgment': '현재 조건에서는 승인이 필요합니다.'}]
    _, edges = w._flow_graph(raw, view, events())
    assert not any(edge['label'] == '답변에 반영' for edge in edges)


def test_each_found_law_has_its_own_graph_entity():
    w = workflow(); raw = body(); view = raw['assembly']['term_agent']['judgment_view']
    found = [dict(events()[0], details=[f'모의법 {i}' for i in range(1, 20)],
                  basis={'kind': 'LAW_FULLTEXT_DIRECTORY'})]
    nodes, edges = w._flow_graph(raw, view, found)
    laws = [node['title'] for node in nodes if node['kind'] == 'law']
    assert all(f'모의법 {i}' in laws for i in range(1, 20))
    assert len([edge for edge in edges if edge['label'] == '확인한 법령']) == len(laws)


def test_search_concept_table_distinguishes_actual_search_from_question_review():
    w = workflow(); raw = body(); view = raw['assembly']['term_agent']['judgment_view']
    view['stages'][0]['concepts'] = ['승인', 'system:question']
    recorded = [dict(events()[0], details=['본문 검색에 사용한 단어: 상인 / 정의 / 4'])]
    nodes, edges = w._flow_graph(raw, view, recorded)
    table = [node for node in nodes if node['kind']=='term']
    assert len(table)==1 and table[0]['rows']==[
        {'concept':'상인','usage':'본문 검색'}, {'concept':'정의','usage':'본문 검색'},
        {'concept':'승인','usage':'질문 검토'}]
    search = next(node for node in nodes if node['kind'] == 'search')
    assert '4' in search['details'][0]
    assert len([edge for edge in edges if edge['label'] == '검색에 사용']) == 1
    assert '승인' not in search['details'][0]
    assert len([edge for edge in edges if edge['label'] == '검토한 개념']) == 1
    _, review_edges = w._flow_graph(raw, view, [])
    assert not any(edge['label']=='검색에 사용' for edge in review_edges)
    assert not any('정의한다' in edge['label'] or '상위 개념' in edge['label'] for edge in edges)


def test_entity_network_has_circles_and_real_relations_without_process_boxes():
    w = workflow(); recorded = events()+[dict(events()[0], details=['본문 검색에 사용한 단어: 상인 / 정의'])]
    raw = body(); view = raw['assembly']['term_agent']['judgment_view']
    view['stages'][5]['data'] = [{'source_id': 's1', 'judgment': '승인이 필요합니다.'}]
    view['stages'][6]['data'] = [{'source_id': 's1', 'judgment': '승인이 필요합니다.'}]
    view['content_sha256'] = digest({k: v for k, v in view.items() if k != 'content_sha256'})
    xml = ET.fromstring(w._judgment_flow(raw, recorded)['svg'])
    entities = {}
    for group in xml.iter():
        if 'data-entity' not in group.attrib: continue
        assert not any(node.tag.endswith('rect') for node in group)
        circles = [node for node in group if node.tag.endswith('circle')]
        assert len(circles)==1 and float(circles[0].attrib['r'])<=20
        entities[group.attrib['data-entity-id']] = group.attrib['data-entity']
    assert set(entities.values())=={'law','source','claim'}
    relationships = []
    for relation in xml.iter():
        if 'data-relation' not in relation.attrib: continue
        relationships.append((entities[relation.attrib['data-from']],entities[relation.attrib['data-to']],relation.attrib['data-relation']))
    assert relationships==[('law','source','포함하는 원문'),('source','claim','판단 근거')]
    assert all(node.attrib.get('data-canvas')=='true' for node in xml.iter() if node.tag.endswith('rect'))
    assert float(xml.attrib['height'])<500 and float(xml.attrib['width'])<1000
    assert not any('data-flow-step' in group.attrib for group in xml.iter())


def test_single_evidence_branch_opens_into_a_triangle_with_curved_links():
    w=workflow();raw=body();view=raw['assembly']['term_agent']['judgment_view']
    view['stages'][5]['data']=[{'source_id':'s1','judgment':'현재 조건에서는 승인이 필요합니다.'}]
    view['content_sha256']=digest({k:v for k,v in view.items() if k!='content_sha256'})
    xml=ET.fromstring(w._judgment_flow(raw)['svg'])
    points={}
    for group in xml.iter():
        if 'data-entity' not in group.attrib:continue
        circle=next(child for child in group if child.tag.endswith('circle'))
        points[group.attrib['data-entity']]=(float(circle.attrib['cx']),float(circle.attrib['cy']))
    a,b,c=(points[kind] for kind in ('law','source','claim'))
    # The claim must be visibly away from the law/source line, not simply
    # another point in the old diagonal chain. Check the rendered geometry.
    distance=abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/((b[0]-a[0])**2+(b[1]-a[1])**2)**0.5
    assert distance>=40
    relations=[group for group in xml.iter() if 'data-relation' in group.attrib]
    assert len(relations)==2
    assert all(' C' in next(child for child in group if child.tag.endswith('path')).attrib['d'] for group in relations)


def test_two_evidence_branches_share_one_law_without_stretching_into_a_chain():
    w=workflow();raw=body();view=raw['assembly']['term_agent']['judgment_view']
    view['stages'][3]['data'].append({'source_id':'s2','document_name':'모의법','coordinate':'제2조',
                                     'action':'원문 열람','quote':'긴급 요청의 모의 조문.'})
    view['stages'][5]['data']=[{'source_id':'s1','judgment':'일반 요청은 담당자가 승인합니다.'},
                             {'source_id':'s2','judgment':'긴급 요청은 팀장이 승인합니다.'}]
    view['content_sha256']=digest({k:v for k,v in view.items() if k!='content_sha256'})
    flow=w._judgment_flow(raw);xml=ET.fromstring(flow['svg'])
    grouped={kind:[] for kind in ('law','source','claim')}
    for group in xml.iter():
        if 'data-entity' not in group.attrib:continue
        circle=next(child for child in group if child.tag.endswith('circle'))
        grouped[group.attrib['data-entity']].append((float(circle.attrib['cx']),float(circle.attrib['cy'])))
    assert [len(grouped[kind]) for kind in grouped]==[1,2,2]
    law=grouped['law'][0];sources=grouped['source']
    assert (sources[0][0]-law[0])*(sources[1][0]-law[0])<0
    assert float(xml.attrib['width'])<800 and float(xml.attrib['height'])<400
    assert flow['metadata']['entity_count']==5 and flow['metadata']['relation_count']==4


def test_curved_branches_fit_canvas_even_when_judgment_labels_are_short():
    w=workflow();raw=body();view=raw['assembly']['term_agent']['judgment_view']
    view['stages'][3]['data'].append({'source_id':'s2','document_name':'모의법','coordinate':'제2조'})
    view['stages'][5]['data']=[{'source_id':'s1','judgment':'승인'}, {'source_id':'s2','judgment':'예외'}]
    view['content_sha256']=digest({k:v for k,v in view.items() if k!='content_sha256'})
    xml=ET.fromstring(w._judgment_flow(raw)['svg']);width=float(xml.attrib['width']);height=float(xml.attrib['height'])
    for relation in xml.iter():
        if 'data-relation' not in relation.attrib:continue
        curve=next(child for child in relation if child.tag.endswith('path')).attrib['d']
        values=[float(value) for value in re.findall(r'-?\d+(?:\.\d+)?',curve)]
        # A Bézier curve stays inside the hull of its endpoints/control points.
        assert all(0<=x<=width for x in values[::2])
        assert all(0<=y<=height for y in values[1::2])


def test_concepts_are_normalized_once_without_repeating_query_cards_and_search_list():
    w = workflow(); raw = body(); view = raw['assembly']['term_agent']['judgment_view']
    view['stages'][0]['concepts'] = [' 상인 ', '정의', 'FULLTEXT', 'fulltext']
    view['stages'][1]['decisions'] = ['검색어: 상인 정의', '검색어:  상인   정의 ']
    recorded = [dict(events()[0], details=['본문 검색에 사용한 단어: 상인 / 정의 / 상인 / fulltext / 4'])]
    nodes, _ = w._flow_graph(raw, view, recorded)
    table = [row for row in nodes if row['kind']=='term']
    assert len(table)==1 and [row['concept'] for row in table[0]['rows']]==['상인','정의','fulltext']
    assert not any(row['kind']=='concept' for row in nodes)
    search = next(row for row in nodes if row['kind']=='search')
    assert search['details'] == ['검색 표현 1개','숫자 조건: 4']
    view['content_sha256'] = digest({k:v for k,v in view.items() if k!='content_sha256'})
    assert '상인 정의' in w._judgment_html(raw)
    flow = w._judgment_flow(raw, recorded)
    xml = ET.fromstring(flow['svg'])
    rows = [row for row in xml.iter() if row.attrib.get('data-concept-row')=='true']
    assert len(rows)==1 and flow['metadata']['layout']=='law-centered-evidence-clusters'
    table_text = ''.join(rows[0].itertext())
    assert all(table_text.count(value)==1 for value in ('상인','정의','fulltext','본문 검색'))
    assert not any(row.attrib.get('data-entity')=='term' for row in xml.iter())


def test_unboxed_concept_properties_keep_both_usages_long_words_and_answer():
    w = workflow(); raw = body(); view = raw['assembly']['term_agent']['judgment_view']
    long_word = '아주긴검색개념'*25
    view['stages'][0]['concepts'] = ['승인',long_word]
    view['content_sha256'] = digest({k:v for k,v in view.items() if k!='content_sha256'})
    recorded = [dict(events()[0],details=['본문 검색에 사용한 단어: 상인 / 정의'])]
    flow = w._judgment_flow(raw,recorded); xml = ET.fromstring(flow['svg'])
    rows = [row for row in xml.iter() if row.attrib.get('data-concept-row')=='true']
    assert {row.attrib['data-usage'] for row in rows}=={'본문 검색','질문 검토'}
    review = next(row for row in rows if row.attrib['data-usage']=='질문 검토')
    cells = [node.text for node in review if node.tag.endswith('text')]
    assert long_word in ''.join(cells).replace(' ','')
    assert not any(group.attrib.get('data-entity')=='answer' for group in xml.iter())
    assert w.render(raw,flow=flow).startswith('확인한 답변.\n\n')
    assert flow['metadata']['answer_body_repeated'] is False


def test_no_graph_is_invented_when_there_are_no_legal_entities():
    w=workflow();raw=body();view=raw['assembly']['term_agent']['judgment_view']
    view['stages'][3]['data']=[]
    view['content_sha256']=digest({k:v for k,v in view.items() if k!='content_sha256'})
    assert w._judgment_flow(raw,events()) is None
    assert '<img' not in w.render(raw) and w.render(raw).startswith('확인한 답변.')


def test_unread_laws_are_collapsed_below_evidence_without_fabricated_links():
    w=workflow();raw=body();view=raw['assembly']['term_agent']['judgment_view']
    found=[dict(events()[0],details=[f'모의법 {i}' for i in range(1,20)],basis={'kind':'LAW_FULLTEXT_DIRECTORY'})]
    flow=w._judgment_flow(raw,found);xml=ET.fromstring(flow['svg'])
    entities=[node for node in xml.iter() if 'data-entity' in node.attrib]
    assert len([node for node in entities if node.attrib['data-entity']=='law'])==1
    assert flow['metadata']['entity_count']==2 and flow['metadata']['relation_count']==1
    assert flow['metadata']['search_candidate_count']==19
    assert all(f'모의법 {i}</li>' in flow['html'] for i in range(1,20))
    assert '<details data-search-candidates="true">' in flow['html']
    assert float(xml.attrib['height']) < 350
    assert len([node for node in xml.iter() if 'data-relation' in node.attrib])==1


def test_graph_is_the_first_collapsed_toggle_after_answer_before_sources(monkeypatch):
    from html.parser import HTMLParser
    w = workflow(); raw = body()
    monkeypatch.setattr(w, '_sources', lambda body: '출처: 모의법 제1조')
    text = w._for_markdown(w.render(raw))
    assert text.startswith('확인한 답변.\n\n<!-- GENOS_JUDGMENT_GRAPH_START -->')
    assert text.index('<img src=') < text.index('출처: 모의법 제1조') < text.index('처리 상세 · 판단 근거와 LLM 호출')
    assert text.count('<img src=') == 1 and '<img' not in w._judgment_html(raw)
    class Placement(HTMLParser):
        def __init__(self): super().__init__(); self.depth=0; self.image_depth=None; self.opened=[]
        def handle_starttag(self, tag, attrs):
            if tag=='details': self.depth+=1; self.opened.append('open' in dict(attrs))
            if tag=='img': self.image_depth=self.depth
        def handle_endtag(self, tag):
            if tag=='details': self.depth-=1
    parser = Placement(); parser.feed(text)
    assert parser.image_depth == 1 and parser.depth == 0 and not any(parser.opened)
    assert w._for_markdown(text) == text


@pytest.mark.parametrize('tamper', ['hash', 'route', 'stage_ref'])
def test_unbound_or_tampered_judgment_never_generates_image(tamper):
    w = workflow(); raw = body(); agent = raw['assembly']['term_agent']
    if tamper == 'hash': agent['judgment_view']['stages'][0]['decisions'] = ['modified']
    if tamper == 'route': agent['case']['route_id'] = 2
    if tamper == 'stage_ref': agent['case']['judgment_refs']['READ'] = {'different': True}
    assert w._judgment_flow(raw, events()) is None
    assert '<img' not in w.render(raw)


@pytest.mark.parametrize('streaming', [False, True])
def test_native_chat_json_and_sse_return_same_svg_and_concise_progress(monkeypatch, tmp_path, streaming):
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(ROOT)); import main
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path)); monkeypatch.setenv('GENOS_MEMORY_ENABLED', '0')
    monkeypatch.setenv('GENOS_CHAT_TRANSPORT', 'auto'); monkeypatch.delenv('TEAM_ID', raising=False)
    calls = []
    async def local(request):
        calls.append(request)
        return {'status': 200, 'body': body()}
    @contextmanager
    def capture(request_id, runtime, sink):
        for event in events(): sink(event)
        yield
    monkeypatch.setattr(adapter, 'call_service', local)
    monkeypatch.setattr(adapter.progress, 'capture', capture)
    response = TestClient(main.app).post('/chat', json={'question': '모의 질문', 'stream': streaming})
    if streaming:
        frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        result = next(frame['data'] for frame in frames if frame['event'] == 'result')
        tokens = ''.join(frame['data'] for frame in frames if frame['event'] == 'token')
        assert 'data:image/svg+xml;base64,' in tokens and '대기 중' not in tokens
    else: result = response.json()['data']
    labels = ''.join(image_xml(result['text']).itertext())
    assert '승인 기한' in labels and '승인 예외' in labels and '돌아갑니다' not in labels
    assert result['judgment_flow']['node_count'] == 5
    assert result['progress_display_revision'] == 'rag-compact-progress-20261009-r1'
    cards = json.dumps(result['agentFlowExecutedData'], ensure_ascii=False)
    assert '대기 중' not in cards and '돌아갑니다' not in cards and len(calls) == 1


def test_split_workflow_final_json_keeps_flow_without_socket(monkeypatch):
    w = workflow()
    monkeypatch.delenv('GENOS_RAG_PROGRESS_UI', raising=False)
    monkeypatch.setattr(w, '_post_code_serving', lambda request: {'status': 200, 'body': {'ad_active': False}})
    async def serving(question, data, display):
        assert not display.enabled and not display.show_inline_progress
        for event in events(): await display.progress(event)
        return body()
    monkeypatch.setattr(w, '_stream_code_serving', serving)
    result = asyncio.run(w.run({'question': '모의 질문'}))
    assert result['judgment_flow']['basis'] == 'request-progress'
    assert result['judgment_flow']['return_count'] == 1 and result['agentFlowExecutedData']
    assert '승인 예외' in ''.join(image_xml(result['text']).itertext())
