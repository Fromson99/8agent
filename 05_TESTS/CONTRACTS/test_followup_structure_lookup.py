"""Stored-structure tool/READ contracts. Synthetic data; no external model calls."""
import copy
from types import SimpleNamespace

import pytest

from semantic_runtime.legal_agent import structure_query as sq, law_candidates as lc
from semantic_runtime.legal_agent import law_navigation as ln
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.errors import ProposalError
from test_structure_first_search import matcher
from test_structure_first_search import structured_generation
from test_unit_fulltext_adaptive_read import tree, session
from test_law_grouped_navigation import decide, reader, cards


def test_explicit_body_name_excludes_separately_registered_annex():
    m = matcher()
    m.document_context = {'annex': {'document_role': 'annex'}, 'law': {'document_role': 'body'}}
    m.document_names.add('자본시장법', 'annex')
    route = sq.resolve('자본시장법 제6조', m, ['law', 'annex'])
    assert route['status'] == 'MATCH' and route['source_ids'] == ['law제6조']


def test_selected_law_supplies_only_the_document_name():
    m = matcher()
    assert sq.resolve('제6조', m, ['law', 'decree'], document_id='law')['source_ids'] == ['law제6조']
    assert sq.resolve('자본시장법 시행령 제6조', m, ['law', 'decree'], document_id='law')['status'] == 'MISS'
    assert sq.resolve('제6조', m, ['decree'], document_id='law')['status'] == 'MISS'


@pytest.mark.parametrize('query', ['자본시장법 제6조', '자본시장법 금융투자업', '금융투자업'])
def test_lookup_uses_stored_coordinates_and_titles(query):
    out = sq.catalogue(matcher(), ['law'], queries=[query])
    assert len(out['items']) == 1 and out['items'][0]['unit_id'] == '제6조'
    assert not out['citation_eligible'] and not out['items'][0]['content_read']


def test_unnamed_coordinate_retains_multiple_laws_and_duplicate_body_is_unreadable():
    m = matcher()
    out = sq.catalogue(m, ['law', 'decree'], queries=['제6조'])
    assert {r['document_id'] for r in out['items']} == {'law', 'decree'}
    assert all(r['status'] == 'MISS' for r in out['resolutions'])
    m = matcher()
    m.stored_coordinates[('law', 'duplicate')] = m.stored_coordinates[('law', '제6조')]
    m.units[('law', 'duplicate')] = {'coordinate_scope': 'body'}
    m.sources['lawduplicate'] = {'document_id': 'law'}
    out = sq.catalogue(m, ['law'], queries=['제6조'])
    assert len(out['items']) == 2 and all(r['ambiguous'] for r in out['items'])


def test_body_directory_pages_ignore_fulltext_and_addenda():
    m = matcher()
    m.units[('law', '제6조의2')]['coordinate_scope'] = 'addendum'
    out = sq.catalogue(m, ['law'], document_id='law', limit=1)
    assert out['total'] == 1 and out['items'][0]['coordinate'] == '제6조'
    assert sq.catalogue(m, ['law'], queries=['자본시장법 부칙 제6조'])['items'] == []
    with pytest.raises(ValueError, match='scope'):
        sq.catalogue(m, ['law'], document_id='decree')
    assert sq.catalogue(m, ['law'], queries=['자본시장법 시행령 제6조'])['items'] == []


def test_structure_directory_continuation_has_no_loss_or_duplicate():
    m = matcher()
    first = sq.catalogue(m, ['law'], document_id='law', limit=1)
    second = sq.catalogue(m, ['law'], document_id='law', offset=first['next_offset'], limit=1)
    assert first['total'] == second['total'] == 2
    assert first['items'][0]['unit_id'] != second['items'][0]['unit_id']
    assert second['next_offset'] is None


def test_definition_on_a_non_article_node_is_not_fabricated_as_an_article():
    from lawrag.core.legal_coordinate import find_coordinates
    m = matcher()
    m.units[('law', 'chapter')] = {'coordinate_scope': 'body'}
    m.stored_coordinates[('law', 'chapter')] = find_coordinates('제1장')[0].coordinate
    m.sources['lawchapter'] = {'document_id': 'law'}
    m.tools = SimpleNamespace(definitions={'def1': {'id': 'def1', 'document_id': 'law',
        'unit_id': 'chapter', 'source_id': 'lawchapter', 'key': '모의용어'}})
    page = sq.catalogue(m, ['law'], queries=["자본시장법 '모의용어'의 정의"])
    assert page['items'] == []
    assert page['resolutions'][0]['reason'] == 'EXACT_DOCUMENT_DEFINITION'


def investigation(native):
    s = native.sources
    # The fixture predates stored scope fields. Bind a fresh synthetic map rather
    # than changing its shared generation maps in place.
    s.matcher.units = {k: dict(v) for k, v in s.matcher.units.items()}
    s.matcher.stored_coordinates = dict(s.matcher.stored_coordinates)
    for key, unit in s.matcher.units.items():
        if key[0] == 'd':
            unit.update(coordinate_scope='body', coordinate_binding={'mode': 'stored'})
    s.profile['candidate_navigation'] = {**lc.DEFAULT_POLICY, 'mode': 'law-first-v1',
        'investigation_control': True, 'completion_contract': True}
    rec = SourceRecall(s).prepare()
    return ln.Investigation(s, '긴급 승인 예외', rec, reader, 120, None, None)


def apply(inv, data, actions, kind, target, queries=None, structure_filter=None):
    value = decide(data, kind, target)
    value.update(law_decisions=[], branch_decisions=[], expected_state_version=data['state_version'],
                 queries=queries or [])
    if structure_filter is not None:
        value['structure_filter'] = structure_filter
    inv.validate(value, data, actions)
    inv.execute(value, data, actions)
    return inv.view()


def hierarchy_matcher():
    from lawrag.core.legal_coordinate import find_coordinates
    from semantic_runtime.navigation_match import SurfaceIndex
    m = matcher()
    nodes = [
        ('part', None, 'kr_편', '제1편', '총칙', 'body', [0, 30]),
        ('chapter', 'part', 'kr_장', '제1장', '금융투자업', 'body', [1, 25]),
        ('article5', 'chapter', 'kr_article', '제5조', '파생상품', 'body', [2, 5]),
        ('article6', 'chapter', 'kr_article', '제6조', '금융투자업', 'body', [5, 20]),
        ('paragraph', 'article6', 'circled', '제6조제1항', '', 'body', [6, 10]),
        ('item', 'paragraph', 'dot_number:1', '제6조제1항제1호', '', 'body', [7, 9]),
        ('subitem', 'item', 'hangul_dot', '제6조제1항제1호가목', '', 'body', [8, 9]),
        ('addendum', None, 'addendum', '', '부칙', 'addendum', [30, 40]),
        ('addendum6', 'addendum', 'kr_article', '제6조', '시행일', 'addendum', [31, 32]),
    ]
    m.units = {}; m.stored_coordinates = {}; m.sources = {}; m.structures = SurfaceIndex()
    for uid, parent, family, surface, title, branch, span in nodes:
        m.units[('law', uid)] = {'parent': parent, 'family': family, 'surface': surface,
            'title': title, 'coordinate_scope': branch, 'coordinate_binding': {'mode': 'stored'}, 'span': span}
        coords = find_coordinates(surface)
        m.stored_coordinates[('law', uid)] = coords[0].coordinate if coords else None
        m.structures.add(title, {'document_id': 'law', 'unit_id': uid, 'kind': 'TITLE'})
        m.sources['law'+uid] = {'document_id': 'law', 'unit_id': uid}
    m._unit_sources = lambda did, uid: ['law'+uid] if uid not in ('part', 'chapter', 'addendum') else []
    return m


def test_document_shape_path_numbering_and_children_are_stored_metadata():
    m = hierarchy_matcher()
    page = sq.document_structure(m, ['law'], 'law', unit_id='article6')
    assert [(p['level'], p['unit_id']) for p in page['path']] == [
        ('편', 'part'), ('장', 'chapter'), ('조', 'article6')]
    assert page['children'][0]['coordinate'] == '제6조제1항'
    assert page['children'][0]['readable'] and page['parent_unit_id'] == 'chapter'
    levels = {r['level']: r for r in page['shape']['levels']}
    assert set(levels) >= {'편', '장', '조', '항', '호', '목'}
    assert levels['조']['count'] == 3
    assert {'parent': '항', 'child': '호'} in page['shape']['parent_child_levels']
    assert page['shape']['branches'] == [
        {'coordinate_scope': 'addendum', 'node_count': 2}, {'coordinate_scope': 'body', 'node_count': 7}]
    assert not page['citation_eligible'] and 'text' not in page
    with pytest.raises(ValueError, match='scope'):
        sq.document_structure(m, ['decree'], 'law')


def test_typed_article_jump_and_branch_qualifier_never_select_addendum_implicitly():
    m = hierarchy_matcher()
    filters = {'coordinate': '제 6 조', 'title': '금융투자업', 'coordinate_scope': 'body'}
    page = sq.catalogue(m, ['law'], document_id='law', structure_filter=filters)
    assert [r['unit_id'] for r in page['items']] == ['article6']
    assert [p['unit_id'] for p in page['items'][0]['path']] == ['part', 'chapter', 'article6']
    assert page['items'][0]['readable']
    filters = {'coordinate': '제6조', 'title': '', 'coordinate_scope': 'addendum'}
    page = sq.catalogue(m, ['law'], document_id='law', structure_filter=filters)
    assert page['items'][0]['unit_id'] == 'addendum6' and not page['items'][0]['readable']
    page = sq.catalogue(m, ['law'], document_id='law', structure_filter={**filters, 'coordinate_scope': ''})
    assert page['items'][0]['unit_id'] == 'article6'


def test_typed_container_search_opens_children_without_reading_container_as_article():
    m = hierarchy_matcher()
    page = sq.catalogue(m, ['law'], document_id='law', structure_filter={
        'coordinate': '제1장', 'title': '', 'coordinate_scope': 'body'})
    assert page['items'][0]['unit_id'] == 'chapter' and not page['items'][0]['readable']
    child = sq.document_structure(m, ['law'], 'law', unit_id='chapter', limit=1)
    assert [r['unit_id'] for r in child['children']] == ['article5']
    child2 = sq.document_structure(m, ['law'], 'law', unit_id='chapter', offset=child['next_offset'], limit=1)
    assert [r['unit_id'] for r in child2['children']] == ['article6']
    assert child2['next_offset'] is None


@pytest.mark.parametrize('coordinate,title', [('제6조', '시행일'), ('제99조', ''), ('제6조부터 제7조', '')])
def test_typed_filter_misses_preserve_structure_without_relaxing_constraints(coordinate, title):
    m = hierarchy_matcher()
    page = sq.catalogue(m, ['law'], document_id='law', structure_filter={
        'coordinate': coordinate, 'title': title, 'coordinate_scope': 'body'})
    assert page['items'] == []
    assert sq.document_structure(m, ['law'], 'law')['shape']['root_count'] == 2


def test_tree_navigation_cannot_hide_missing_or_cyclic_parent():
    from semantic_runtime.legal_agent.errors import ContractError
    m = hierarchy_matcher()
    m.units[('law', 'part')]['parent'] = 'article6'
    with pytest.raises(ContractError, match='cyclic'):
        sq.document_structure(m, ['law'], 'law', unit_id='article6')


def forbid_fulltext(monkeypatch, idx):
    def denied(*args, **kwargs):
        pytest.fail('structure navigation must not call fulltext')
    for name in ('law_groups_page', 'article_groups_page', 'hit_page', 'rank_units'):
        monkeypatch.setattr(idx, name, denied)


def test_current_document_tree_down_up_and_direct_fields_lookup(session, monkeypatch):
    native, idx = session
    inv = investigation(native)
    data, actions = inv.view()
    forbid_fulltext(monkeypatch, idx)
    law = data['laws'][0]; tree = law['document_structure']
    assert tree['search_fields'] == ['coordinate', 'title', 'coordinate_scope']
    data, actions = apply(inv, data, actions, 'BROWSE_STRUCTURE', tree['children'][0]['browse_action'])
    tree = data['laws'][0]['document_structure']
    assert tree['focus']['unit_id'] == '0'
    assert [r['level'] for r in tree['children']] == ['항', '항']
    data, actions = apply(inv, data, actions, 'BROWSE_STRUCTURE', tree['children'][0]['browse_action'])
    tree = data['laws'][0]['document_structure']
    assert [p['level'] for p in tree['path']] == ['조', '항']
    data, actions = apply(inv, data, actions, 'BROWSE_STRUCTURE', tree['parent_action'])
    tree = data['laws'][0]['document_structure']
    data, actions = apply(inv, data, actions, 'BROWSE_STRUCTURE', tree['root_action'])
    law = data['laws'][0]
    data, actions = apply(inv, data, actions, 'SEARCH_STRUCTURE', law['structure_search_action'],
        structure_filter={'coordinate': '제1조제2항', 'title': '', 'coordinate_scope': 'body'})
    row = data['structure_catalogue']['items'][0]
    assert row['unit_id'] == '5' and row['read_action']
    data, actions = apply(inv, data, actions, 'READ_ARTICLES', row['read_action'])
    assert data['sources']
    assert data['laws'][0]['document_structure']['focus']['unit_id'] == '5'
    assert any(a['action'] == 'SEARCH_STRUCTURE' for a in actions.values())
    target = next(k for k, a in actions.items() if a['action'] == 'READ_SCOPE' and a['identity']['scope'] == 'subtree:0')
    data, actions = apply(inv, data, actions, 'READ_SCOPE', target)
    assert data['laws'][0]['document_structure']['focus']['unit_id'] == '0'
    data, actions = apply(inv, data, actions, 'SEARCH_STRUCTURE', data['laws'][0]['structure_search_action'],
        structure_filter={'coordinate': '제99조', 'title': '', 'coordinate_scope': 'body'})
    assert not data['structure_catalogue']['items']
    assert data['laws'][0]['document_structure']['focus']['unit_id'] == '0'


def test_failed_lookup_keeps_current_tree_and_search_available_after_resume(session, monkeypatch):
    native, idx = session
    inv = investigation(native)
    data, actions = inv.view()
    forbid_fulltext(monkeypatch, idx)
    tree = data['laws'][0]['document_structure']
    data, actions = apply(inv, data, actions, 'BROWSE_STRUCTURE', tree['children'][0]['browse_action'])
    frame = data['chain_frame_id']
    law = data['laws'][0]
    data, actions = apply(inv, data, actions, 'SEARCH_STRUCTURE', law['structure_search_action'],
        structure_filter={'coordinate': '제99조', 'title': '', 'coordinate_scope': 'body'})
    assert not data['structure_catalogue']['items']
    assert data['laws'][0]['document_structure']['focus']['unit_id'] == '0'
    resumed = ln.Investigation(inv.s, inv.question, inv.record, reader, 120, copy.deepcopy(inv.p), None)
    data, actions = resumed.view()
    law = data['laws'][0]
    assert law['document_structure']['root_action'] and law['structure_search_action']
    data, actions = apply(resumed, data, actions, 'SEARCH_STRUCTURE', law['structure_search_action'],
        structure_filter={'coordinate': '제1조', 'title': '', 'coordinate_scope': 'body'})
    assert data['structure_catalogue']['items'][0]['unit_id'] == '0'
    point = next(p for p in data['return_points'] if p['id'] == frame)
    data, _ = apply(resumed, data, actions, 'RETURN_TO', point['return_action'])
    assert data['laws'][0]['document_structure']['focus']['unit_id'] == '0'


def test_typed_lookup_requires_bound_document_and_cannot_mix_search_inputs(session):
    native, _ = session
    inv = investigation(native)
    data, actions = inv.view()
    target = next(k for k, a in actions.items() if a['action'] == 'SEARCH_STRUCTURE' and a['identity']['document_id'] is None)
    filters = {'coordinate': '제1조', 'title': '', 'coordinate_scope': 'body'}
    with pytest.raises(ProposalError, match='document target'):
        apply(inv, data, actions, 'SEARCH_STRUCTURE', target, structure_filter=filters)
    target = data['laws'][0]['structure_search_action']
    with pytest.raises(ProposalError, match='empty queries'):
        apply(inv, data, actions, 'SEARCH_STRUCTURE', target, ['제1조'], structure_filter=filters)


def test_failed_global_lookup_retains_document_from_fulltext_view(session, monkeypatch):
    native, idx = session
    inv = investigation(native)
    data, actions = inv.view()
    data, actions = apply(inv, data, actions, 'OPEN_LAW', data['laws'][0]['open_action'])
    forbid_fulltext(monkeypatch, idx)
    target = next(k for k, a in actions.items() if a['action'] == 'SEARCH_STRUCTURE' and a['identity']['document_id'] is None)
    data, actions = apply(inv, data, actions, 'SEARCH_STRUCTURE', target, ['존재하지않는표제'])
    assert data['structure_catalogue']['total'] == 0
    assert data['laws'][0]['document_structure']['document_id'] == 'd'
    assert data['laws'][0]['structure_search_action'] in actions


def test_followup_lookup_reads_every_article_block_with_no_fulltext(session, monkeypatch):
    native, idx = session
    inv = investigation(native)
    # The first search is already complete. Every subsequent location/READ is
    # structural; even a fulltext lookup is forbidden by this contract.
    monkeypatch.setattr(idx, 'article_groups_page', lambda *a, **k: pytest.fail('fulltext article page'))
    monkeypatch.setattr(idx, 'hit_page', lambda *a, **k: pytest.fail('fulltext hit page'))
    inv.p['window'] = 'structure'
    data, actions = inv.view()
    target = next(k for k, a in actions.items() if a['action'] == 'SEARCH_STRUCTURE' and a['identity']['document_id'] is None)
    data, actions = apply(inv, data, actions, 'SEARCH_STRUCTURE', target, ['제1조'])
    assert not inv.p['no_progress']
    row = data['structure_catalogue']['items'][0]
    assert row['coordinate'] == '제1조'
    data, actions = apply(inv, data, actions, 'READ_ARTICLES', row['read_action'])
    group = next(g for g in inv.p['groups'].values() if g['id'] in inv.p['window_groups'])
    spans = [p for page in data['sources'] for p in page['spans']]
    while group['delivery'] + 1 < len(group['page_plan']):
        card = next(c for c in cards(data) if c['id'] == group['id'])
        data, actions = apply(inv, data, actions, 'READ_PARENT', card['read_parent_action'])
        spans.extend(p for page in data['sources'] for p in page['spans'])
    assert {p['block_id'] for p in spans} == {'0', '1', '2', '3', '4', '5'}
    assert group['status'] != 'ACTIVE'
    assert inv.p['selected'][group['id']]['offer']['article_complete']
    assert inv.p['query_history'] and len(inv.p['structure_search_history']) == 1


def test_structure_page_return_resume_and_changed_queries(session):
    native, _ = session
    inv = investigation(native)
    data, actions = inv.view()
    target = next(k for k, a in actions.items() if a['action'] == 'SEARCH_STRUCTURE' and a['identity']['document_id'] is None)
    data, actions = apply(inv, data, actions, 'SEARCH_STRUCTURE', target, ['第1条不存在'])
    assert data['structure_catalogue']['total'] == 0
    target = next(k for k, a in actions.items() if a['action'] == 'SEARCH_STRUCTURE' and a['identity']['document_id'] is None)
    data, actions = apply(inv, data, actions, 'SEARCH_STRUCTURE', target, ['제1조제2항'])
    assert data['structure_catalogue']['items'][0]['unit_id'] == '5'
    saved = copy.deepcopy(inv.p)
    resumed = ln.Investigation(inv.s, inv.question, inv.record, reader, 120, saved, None)
    restored, offers = resumed.view()
    assert restored['structure_catalogue'] == data['structure_catalogue']
    target = next(k for k, a in offers.items() if a['action'] == 'SEARCH_STRUCTURE' and a['identity']['document_id'] is None)
    with pytest.raises(ProposalError, match='unchanged structure'):
        apply(resumed, restored, offers, 'SEARCH_STRUCTURE', target, ['제1조제2항'])
    point = next(p for p in restored['return_points'] if p['id'] != restored['chain_frame_id'])
    restored, _ = apply(resumed, restored, offers, 'RETURN_TO', point['return_action'])
    assert len(resumed.p['structure_search_history']) == 2


def test_open_structure_directory_is_independent_of_fulltext_matches(session, monkeypatch):
    native, idx = session
    inv = investigation(native)
    data, actions = inv.view()
    target = data['laws'][0]['structure_open_action']
    monkeypatch.setattr(idx, 'article_groups_page', lambda *a, **k: pytest.fail('fulltext'))
    data, actions = apply(inv, data, actions, 'OPEN_STRUCTURE', target)
    assert data['structure_catalogue']['total'] == 1
    assert data['structure_catalogue']['items'][0]['read_action']


def test_followup_fulltext_query_preserves_an_explicit_structural_entry(session):
    native, _ = session
    inv = investigation(native)
    s = inv.s
    s.law_search_queries = ['모의승인규정 제1조제2항']
    rec = SourceRecall(s).prepare()
    assert rec['structure_query']['status'] == 'MATCH'
    assert any(h.get('requested_unit_id') == '5' and h['entry_reason'] == 'exact_structure'
               for h in rec['unit_hits'])


def test_structure_read_keeps_empty_container_requested_scope(session):
    native, _ = session
    inv = investigation(native)
    s = inv.s
    sid = next(sid for sid, src in s.tools.sources.items() if src['document_id'] == 'd')
    # A mock empty container is a structural condition, not a rewritten source.
    from semantic_runtime.legal_agent import unit_reading as ur
    original = ur.blocks
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ur, 'blocks', lambda s, did, uid, extent: [] if str(uid) == '0' and extent == 'exact'
                      else original(s, did, uid, extent))
        h = lc.structure_hit(s, sid, '0')
    assert h['unit_id'] != '0' and h['requested_unit_id'] == '0'
    assert lc.parent_offer(s, h)['id'] == 'subtree:0'


@pytest.mark.parametrize('lookup', ['text', 'fields'])
def test_native_api_exposes_followup_structure_and_publishes_read_original(tmp_path, structured_generation, lookup):
    import json
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from semantic_runtime.unit_fulltext import UnitFulltextIndex, build
    from test_law_grouped_navigation import LawTransport
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT, wire
    from test_unified_legal_agent import ok

    class Transport(LawTransport):
        def send_once(self, *, body, ticket):
            view = json.loads(body['messages'][1]['content'])['view']
            phase = view.get('source_stage', view['phase'])
            if phase.startswith('source-law-navigation-'):
                self.phases.append(phase)
                if not getattr(self, 'located', False):
                    self.located = True
                    if lookup == 'fields':
                        law = next(l for l in view['laws'] if l['name'] == '모의승인규정')
                        assert law['document_structure']['shape']['node_count'] == 2
                        value = decide(view, 'SEARCH_STRUCTURE', law['structure_search_action'])
                        value['structure_filter'] = {'coordinate': '제2조', 'title': '', 'coordinate_scope': 'body'}
                    else:
                        action = next(a for a in view['actions'] if a['action'] == 'SEARCH_STRUCTURE')
                        value = decide(view, 'SEARCH_STRUCTURE', action['id'])
                        value['queries'] = ['모의승인규정 제2조']
                elif not getattr(self, 'read_structural', False):
                    self.read_structural = True
                    row = view['structure_catalogue']['items'][0]
                    law = next(l for l in view['laws'] if l['name'] == '모의승인규정')
                    assert law['document_structure']['focus']['coordinate'] == '제2조'
                    value = decide(view, 'READ_ARTICLES', row['read_action'])
                else:
                    value = reader(None, view, None, phase, 120)
                return wire(value)
            return super().send_once(body=body, ticket=ticket)

    gen = structured_generation
    path = tmp_path/'units'
    build(gen, gen/'navigation', path, workers=1)
    idx = UnitFulltextIndex(path, json.loads((gen/'navigation/manifest.json').read_text()))
    transport = Transport()
    app = create_app(tmp_path/'app', gen, contracts_root=ROOT, provider=object(),
        implementation='legal-agent-unified-v6', runtime_root=tmp_path/'runtime',
        legal_agent_profile={**settings(), 'candidate_navigation': {'mode': 'law-first-v1'}},
        legal_agent_transport=transport,
        memory_identity=lambda req: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as client:
        result = ok(client.post('/v1/rag/ask', json={'question': '승인 예외를 확인해줘',
            'session_id': 'structure', 'request_id': 'structure-r1'}))
    steps = result['assembly']['term_agent']['investigation_chain']['steps']
    assert any(s['action'] == 'SEARCH_STRUCTURE' for s in steps)
    assert any(s['action'] == 'READ_ARTICLES' for s in steps)
    assert result['answer']['claims']
