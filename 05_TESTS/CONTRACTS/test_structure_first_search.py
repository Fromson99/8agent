"""Synthetic structure/READ/fallback contracts; no model or latency benchmark."""
import json
import sqlite3
from types import SimpleNamespace

import pytest

from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.navigation_match import SurfaceIndex, norm
from semantic_runtime.legal_agent.structure_query import navigation_context, resolve
from semantic_runtime.legal_agent.source_selection import select_sources
from test_legal_agent_double_harness import wire
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation
from test_bounded_source_main import Transport, settings
from test_legal_agent_v5 import app_for, PROFILE, plan, decision, choices
from test_bounded_source_selection import record


@pytest.fixture
def structured_generation(tmp_path, term_glossary):
    raw = source(tmp_path/'raw.sqlite', [('d', '모의승인규정', [
        '원칙상 이사회 승인을 받아야 한다. 다만 제2조의 예외를 확인한다.',
        '적법하게 위임된 경우에는 별도 이사회 승인을 받지 않는다.']),
        ('other', '다른문서', ['이 자료는 이번 요청 범위 밖이다.'])])
    with sqlite3.connect(raw) as db:
        for did, uid, text in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
            unit = json.loads(text)
            coordinate = find_coordinates(unit['surface'])[0].coordinate
            unit.update(legal_coordinate=coordinate.as_dict(), coordinate_scope='body',
                        coordinate_key='body:'+coordinate.canonical_surface())
            db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',
                       (json.dumps(unit, ensure_ascii=False), did, uid))
    build_generation(raw, term_glossary, tmp_path/'built', serving=True)
    return tmp_path/'built/generation'


def matcher():
    names = SurfaceIndex()
    documents = {'law': '자본시장과 금융투자업에 관한 법률', 'decree': '자본시장과 금융투자업에 관한 법률 시행령'}
    aliases = {'law': '자본시장법', 'decree': '자본시장법 시행령'}
    for did, title in documents.items():
        names.add(title, did)
        names.add(aliases[did], did)
    coords, units, sources = {}, {}, {}
    for did, locator in [('law', '제6조'), ('law', '제6조제1항'), ('law', '제6조의2'),
                         ('decree', '제6조'), ('decree', '제7조')]:
        key = did, locator
        coords[key] = find_coordinates(locator)[0].coordinate
        units[key] = {'coordinate_scope': 'body'}
        sources[did+locator] = {'document_id': did, 'unit_id': locator}
    headings = SurfaceIndex()
    headings.add('금융투자업', {'document_id': 'law', 'unit_id': '제6조', 'kind': 'TITLE'})
    return SimpleNamespace(document_names=names, structures=headings, documents=documents,
        title_keys={norm(x) for x in list(documents.values())+list(aliases.values())},
        stored_coordinates=coords, units=units, sources=sources,
        _unit_sources=lambda did, uid: [did+uid])


@pytest.mark.parametrize('query,expected', [
    ('자본시장법 제 6 조에 따른 금융투자업 종류는?', ['law제6조']),
    ('자본시장과 금융투자업에 관한 법률 제6조제1항은?', ['law제6조제1항']),
    ('자본시장법 제6조의2는?', ['law제6조의2']),
    ('자본시장법 시행령 제6조는?', ['decree제6조']),
    ('자본시장법 제6조와 자본시장법 시행령 제7조 비교', ['law제6조', 'decree제7조']),
    ('자본시장법 제6조 및 제6조의2 설명', ['law제6조', 'law제6조의2']),
])
def test_named_coordinates_are_paired_without_cross_product(query, expected):
    route = resolve(query, matcher(), ['law', 'decree'])
    assert route['status'] == 'MATCH'
    assert route['source_ids'] == expected


@pytest.mark.parametrize('query', [
    '제6조 금융투자업 종류는?', '자본시장법 제99조는?',
    '자본시장법 제6조제99항은?', '자본시장법 제6조와 제99조는?',
    '자본시장법과 자본시장법 시행령 제6조 비교',
    '자본시장법 부칙 제6조는?', '자본시장법 제6조부터 제8조까지는?',
    '자본시장법 제6조와 시행령 제6조는?', '자본시장법 및 없는법 제6조는?',
])
def test_missing_ambiguous_or_partial_coordinates_do_not_narrow_search(query):
    route = resolve(query, matcher(), ['law', 'decree'])
    assert route['status'] == 'MISS'
    assert route['source_ids'] == []


def test_scope_and_duplicate_document_alias_are_not_bypassed():
    m = matcher()
    assert resolve('자본시장법 제6조', m, ['decree'])['status'] == 'MISS'
    m.document_names.add('자본시장법', 'decree')
    assert resolve('자본시장법 제6조', m, ['law', 'decree'])['status'] == 'MISS'


def test_duplicate_body_coordinate_is_unresolved():
    m = matcher()
    m.stored_coordinates[('law', 'duplicate')] = m.stored_coordinates[('law', '제6조')]
    m.units[('law', 'duplicate')] = {'coordinate_scope': 'body'}
    assert resolve('자본시장법 제6조', m, ['law'])['status'] == 'MISS'


def test_literal_heading_is_scoped_to_named_document():
    m = matcher()
    assert resolve('자본시장법 금융투자업 종류는?', m, ['law'])['source_ids'] == ['law제6조']
    assert resolve('자본시장법 시행령 금융투자업 종류는?', m, ['decree'])['status'] == 'MISS'
    m.structures.add('금융투자업', {'document_id': 'law', 'unit_id': '제6조의2', 'kind': 'TITLE'})
    assert resolve('자본시장법 금융투자업 종류는?', m, ['law'])['status'] == 'MISS'


def test_named_quoted_definition_routes_only_bound_original():
    m = matcher()
    m.tools = SimpleNamespace(definitions={'def1': {
        'id': 'def1', 'document_id': 'law', 'unit_id': '제6조',
        'source_id': 'law제6조', 'key': '자기자본'}})
    question = "자본시장법에서 '자기자본'의 정의는 무엇인가요?"
    route = resolve(question, m, ['law', 'decree'])
    assert route['reason'] == 'EXACT_DOCUMENT_DEFINITION'
    assert route['source_ids'] == ['law제6조']
    assert resolve(question, m, ['decree'])['status'] == 'MISS'
    assert resolve('자본시장법에서 자기자본의 정의는?', m, ['law'])['status'] == 'MISS'


def test_navigation_context_contains_locations_but_no_source_text():
    m = matcher()
    m.tools = SimpleNamespace(terms={'term1': {'label': '자기자본'}},
        definitions={'def1': {'id': 'def1', 'document_id': 'law',
                              'unit_id': '제6조', 'source_id': 'law제6조',
                              'key': '자기자본', 'scope_status': 'EXPLICIT_SCOPE_HINT'}})
    matches = {'documents': [{'id': 'law', 'name': m.documents['law']}],
               'structures': [], 'terms': [{'id': 'term1',
                   'question_spans': [{'text': '자기자본'}]}]}
    hints = navigation_context("자본시장법에서 '자기자본'의 정의는?", m,
                               ['law', 'decree'], matches=matches)
    assert hints['definitions'][0]['unit_id'] == '제6조'
    assert hints['terms'][0]['label'] == '자기자본'
    assert hints['navigation_hint_only'] and not hints['citation_eligible']
    assert 'source_text' not in str(hints)


def test_unnamed_ambiguous_definitions_do_not_expose_arbitrary_first_page():
    m = matcher()
    m.tools = SimpleNamespace(terms={'term1': {'label': '자기자본'}},
        definitions={str(i): {'id': str(i), 'document_id': str(i),
                              'unit_id': '1', 'source_id': str(i), 'key': '자기자본'}
                     for i in range(9)})
    matches = {'documents': [], 'structures': [],
               'terms': [{'id': 'term1', 'question_spans': [{'text': '자기자본'}]}]}
    hints = navigation_context('자기자본 정의', m, [str(i) for i in range(9)],
                               matches=matches)
    assert hints['definition_candidates_ambiguous']
    assert {d['definition_id'] for d in hints['definitions']} == {str(i) for i in range(9)}
    assert hints['terms'][0]['label'] == '자기자본'


def test_child_coordinate_and_addendum_are_not_used_as_main_body():
    m = matcher()
    m.units[('law', '제6조')]['coordinate_scope'] = 'addendum'
    assert resolve('자본시장법 제6조', m, ['law'])['status'] == 'MISS'


def test_structural_selection_reads_complete_text_and_can_request_more():
    r = {**record(), 'discovery_mode': 'structure'}
    calls = []
    def invoke(system, data, schema, phase, timeout):
        calls.append(data)
        assert 'needs_fulltext' in schema['required']
        assert all(c['excerpts'][0]['start'] == 0 and
                   c['excerpts'][0]['end'] == c['total_chars'] for c in data['originals'])
        return {'issues': ['별도 예외 부족'], 'needs_fulltext': True,
                'choices': [{'id': 'C001', 'reason': '승인 원칙 확인'}]}
    selected = select_sources('승인 대상과 별도 예외는?', r, invoke, remaining_seconds=60)
    assert selected['needs_fulltext']
    assert selected['final_ids'] == ['0']
    assert len(calls) == 1


def test_oversized_structural_text_falls_back_without_silent_truncation():
    selected = select_sources('승인', {**record(), 'discovery_mode': 'structure'},
        lambda *args: pytest.fail('oversized original must not be sent'),
        remaining_seconds=60, max_fulltext_chars=1)
    assert selected['needs_fulltext']
    assert selected['fallback_reason'] == 'STRUCTURE_CONTEXT_LIMIT'


def test_empty_structural_selection_requests_fulltext_even_if_model_says_sufficient():
    selected = select_sources('승인', {**record(), 'discovery_mode': 'structure'},
        lambda *args: {'issues': [], 'choices': [], 'needs_fulltext': False}, remaining_seconds=60)
    assert selected['needs_fulltext']


class StructuralTransport(Transport):
    def __init__(self, needs_fulltext=False):
        super().__init__()
        self.needs_fulltext = needs_fulltext
        self.structural_views = []

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        if view.get('source_stage') == 'source-query-plan':
            self.calls.append(body)
            return wire({'mode':'SEARCH','law_names':['모의승인규정'],'queries':[view['question']],
                'answer':'','reason':'모의 모델이 요청의 조문을 선택','document_category':'all',
                'browse_view':'documents','title_query':'','inspect_documents':False})
        if view.get('source_stage') == 'source-triage' and 'originals' in view:
            self.calls.append(body)
            self.structural_views.append(view)
            return wire({'issues': [], 'needs_fulltext': self.needs_fulltext,
                'choices': [{'id': view['originals'][0]['id'], 'reason': '지정 조문 원문 확인'}]})
        return super().send_once(body=body, ticket=ticket)


def test_model_selected_exact_structure_skips_fulltext(tmp_path, structured_generation, monkeypatch):
    transport = StructuralTransport()
    app = app_for(tmp_path, structured_generation, transport, settings())
    p = app.state.pipeline
    try:
        request = {'question': '모의승인규정 제1조에 따른 승인 대상은?', 'document_ids': ['d'], 'use_llm': True}
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['d']), runtime=tmp_path/'runtime') as s:
            monkeypatch.setattr(s.sources.matcher.fulltext, 'rank', lambda *args: pytest.fail('exact structure must skip fulltext'))
            monkeypatch.setattr(s.sources.tools.sources, 'items',
                                lambda: pytest.fail('scope lookup must not enumerate original JSON'))
            s.investigate()
            assert not s.limitations, s.limitations
            assert s.source_recall_record['discovery_mode'] == 'structure'
            assert s.source_recall_record['queries'] == []
            assert s.structure_first_record['fulltext_fallback'] is False
            assert transport.structural_views
            assert '원칙상 이사회 승인을 받아야 한다.' in transport.structural_views[0]['originals'][0]['excerpts'][0]['text']
            phases = [json.loads(b['messages'][1]['content'])['view'].get('source_stage') for b in transport.calls]
            assert phases == ['source-query-plan', 'source-triage', 'bounded-question-plan']
            assert s.source_selection_record['final_ids'] == s.source_recall_record['read_complete']
            assert all(h['payload']['selection_basis'] == 'STRUCTURE_FULL_ORIGINAL_COVERAGE_CHECK'
                       for h in s.work.heads('source_selection', current=True))
    finally:
        p.store.close()


def test_insufficient_structural_originals_expand_to_existing_fulltext(tmp_path, structured_generation, monkeypatch):
    transport = StructuralTransport(needs_fulltext=True)
    app = app_for(tmp_path, structured_generation, transport, settings())
    p = app.state.pipeline
    try:
        request = {'question': '모의승인규정 제1조의 승인 원칙과 별도 예외는?', 'document_ids': ['d'], 'use_llm': True}
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['d']), runtime=tmp_path/'runtime') as s:
            rank = s.sources.matcher.fulltext.rank
            calls = []
            def traced(*args, **kwargs):
                calls.append('fulltext')
                assert transport.structural_views, 'read and inspect the structural original before fulltext'
                return rank(*args, **kwargs)
            monkeypatch.setattr(s.sources.matcher.fulltext, 'rank', traced)
            s.investigate()
            assert not s.limitations, s.limitations
            assert calls
            assert s.structure_first_record['fulltext_fallback']
            assert s.source_recall_record['discovery_mode'] == 'fulltext'
            initial = set(s.structure_first_record['source_ids'])
            assert initial <= set(s.source_recall_record['selected_for_read'])
            assert len(s.source_selection_record['final_ids']) == 2
    finally:
        p.store.close()


def test_exact_structure_ask_publishes_original_source(tmp_path, structured_generation):
    app = app_for(tmp_path, structured_generation, StructuralTransport(),
                  {**settings(), 'final_review_enabled': False})
    try:
        ask = app.state.pipeline.run
        result = ask('모의승인규정 제1조의 승인 대상은?', ['d'])
        assert result['answer']['claims']
        meta = result['assembly']['term_agent']
        assert not meta['structure_first_search']['fulltext_fallback']
        assert len(meta['source_bundle']['sources']) == 1
        assert meta['source_bundle']['sources'][0]['document_name'] == '모의승인규정'
        assert result['answer']['provider_receipt']['final_review_status'] == 'SKIPPED'
    finally:
        app.state.pipeline.store.close()


def test_an_unread_requested_article_cannot_be_hidden_by_another_complete_read(tmp_path, structured_generation, monkeypatch):
    transport = StructuralTransport()
    app = app_for(tmp_path, structured_generation, transport, settings())
    p = app.state.pipeline
    try:
        request = {'question': '모의승인규정 제1조와 제2조의 승인 대상은?', 'document_ids': ['d'], 'use_llm': True}
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['d']), runtime=tmp_path/'runtime') as s:
            execute = s.sources.execute
            def first_read_failure(action, ident, **kwargs):
                if (action['tool'] == 'read' and not getattr(s.sources, 'force_fulltext_recall', False)
                        and s.sources.resolve(action['args']['target'], 'P')['unit_id'] == '1'):
                    return {'status': 'ERROR', 'server_reason': 'synthetic unread article'}
                return execute(action, ident, **kwargs)
            monkeypatch.setattr(s.sources, 'execute', first_read_failure)
            s.investigate()
            assert not s.limitations, s.limitations
            assert s.structure_first_record['fulltext_fallback']
            assert not transport.structural_views, 'do not judge a partially acquired set as sufficient'
            assert len(s.source_recall_record['read_complete']) == 2
    finally:
        p.store.close()


class ToolsTransport(Transport):
    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        if view['phase'] == 'investigate':
            self.calls.append(body)
            assert view['structure_first_search']['read_complete']
            assert view['exact_evidence'], 'the first investigation must receive actual originals'
            return wire(decision(plan(refs=view['reference_numbers']['questions']), source_selection=choices(view), intent='DRAFT',
                                 reason='지정 조문 원문으로 답변 작성'))
        if view['phase'] == 'select_sources':
            self.calls.append(body)
            return wire(choices(view))
        return super().send_once(body=body, ticket=ticket)


def test_model_tool_loop_receives_question_before_any_automatic_originals(tmp_path, structured_generation, monkeypatch):
    app = app_for(tmp_path, structured_generation, ToolsTransport(), {**PROFILE, 'final_review_enabled': False})
    p = app.state.pipeline
    try:
        request = {'question': '모의승인규정 제1조의 승인 대상은?', 'document_ids': ['d'], 'use_llm': True}
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['d']), runtime=tmp_path/'runtime') as s:
            def inspect_first(phase, *args, **kwargs):
                assert phase == 'investigate'
                assert not s.work.evidence() and not s.work.observations(1)
                assert s.context.request['question'] == request['question']
                raise RuntimeError('first model decision reached')
            monkeypatch.setattr(s, 'generate_checked', inspect_first)
            with pytest.raises(RuntimeError, match='first model decision reached'):
                s.investigate()
    finally:
        p.store.close()
