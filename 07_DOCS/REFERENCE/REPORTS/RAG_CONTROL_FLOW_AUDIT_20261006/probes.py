"""Read-only control-flow diagnostics: synthetic sources and scripted decisions.

Assertions describe the observed defect, not the desired future behavior.
Run from workspace root with .venv/bin/python -m pytest <this file> -q.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / '05_TESTS/CONTRACTS'))
spec = importlib.util.spec_from_file_location('rag_audit_bootstrap', ROOT / '05_TESTS/conftest.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
sys.modules['conftest'] = bootstrap
sys.path.insert(0, str(ROOT / '05_TESTS/CONTRACTS'))
from test_unit_fulltext_adaptive_read import tree, session, hit, record, ur, us
from test_batch_reference_navigation import connected, initial, decision, rel

term_glossary = bootstrap.term_glossary
OBSERVATIONS = []


@pytest.fixture(scope='session', autouse=True)
def observations():
    yield
    Path(__file__).with_name('probe-results.json').write_text(
        json.dumps(OBSERVATIONS, ensure_ascii=False, indent=2) + '\n')


def no_navigation(selected, pending=False):
    return {'contract': 'scripted-navigation', 'batches': [], 'actions': [],
        'seen_target_ids': [], 'limits': [], 'unresolved': [],
        'pending': pending, 'scanned_anchors': list({r['source_id'] for r in selected.values()})}


def choice(data, scope):
    return {'issues': [], 'choices': [{'id': data['units'][0]['id'],
        'scope': scope, 'reason': '모의 원문 확인'}], 'needs_search': False}


def test_grouping_undoes_source_interleaving(session, monkeypatch):
    s, _ = session
    monkeypatch.setitem(ur.POLICY, 'group_units', 1)
    # A second identity tests ordering only, not the source validation contract.
    monkeypatch.setattr(ur, 'offer_plan', lambda s, h: ([{'extent': 'exact', 'chars': 1}], []))
    a1, a2 = hit(s, '3'), hit(s, '4')
    b1 = {**hit(s, '5'), 'source_id': 'B', 'key': 'B#unit:5'}
    result = ur.group_hits(s.sources, [a1, b1, a2])
    assert [h['key'] for h in result] == [a1['key'], a2['key'], b1['key']]
    OBSERVATIONS.append({'id': 'P1', 'input': [a1['key'], b1['key'], a2['key']],
        'output': [h['key'] for h in result], 'method': 'real grouping, stub scope sizes'})


def test_partial_expansion_rereads_leaf(session):
    s, _ = session
    h = hit(s)
    state = {'count': 0, 'chars': 0}
    offers = {o['id']: o for o in ur.offers(s.sources, h)}
    leaf = ur.read(s.sources, h, offers['exact:3'], action_state=state)
    expanded = ur.read(s.sources, h, offers['subtree:1'], action_state=state)
    new_ids = {e['evidence_id'] for e in expanded['evidence']} - {e['evidence_id'] for e in leaf['evidence']}
    repeated = [p for e in expanded['evidence'] if e['evidence_id'] in new_ids
        for p in e['spans'] if p['block_id'] == '3']
    assert repeated and len(expanded['actions']) == 4
    OBSERVATIONS.append({'id': 'P2', 'leaf_pages': len(leaf['actions']),
        'expansion_pages': len(expanded['actions']), 'repeated_block': '3',
        'new_evidence_ids': sorted(new_ids), 'method': 'real source reader'})


def test_reset_action_counter_collides_in_same_session(session):
    s, _ = session
    h = hit(s, '3')
    ur.read(s.sources, h, ur.offers(s.sources, h)[0], action_state={'count': 0, 'chars': 0})
    other = hit(s, '5')
    with pytest.raises(Exception) as exc:
        ur.read(s.sources, other, ur.offers(s.sources, other)[0], action_state={'count': 0, 'chars': 0})
    assert 'action ID reused' in str(exc.value) or 'unit READ failed' in str(exc.value)
    OBSERVATIONS.append({'id': 'P3', 'error': str(exc.value),
        'method': 'real reader, same journal, reset state as prepare does'})


def test_pending_sticks_after_successful_second_navigation(session, monkeypatch):
    s, _ = session
    rec = record(s)
    navigations = []
    def nav(q, sess, selected, invoke, **kwargs):
        pending = not navigations
        navigations.append(pending)
        return no_navigation(selected, pending)
    monkeypatch.setattr(rel, 'navigate', nav)
    def invoke(system, data, schema, phase, timeout):
        value = choice(data, 'exact:3' if phase.endswith('triage') else 'subtree:1')
        if phase.endswith('review'):
            value.update(evidence_sufficient=True, sufficiency_reason='펼친 범위가 필요 충분')
        return value
    out = us.select('승인', rec, invoke, session=s.sources, remaining_seconds=120, max_fulltext_chars=80000)
    assert navigations == [True, False] and out['reference_navigation']['pending']
    assert out['needs_fulltext'] and out['status'] == 'pending'
    OBSERVATIONS.append({'id': 'P4', 'navigation_pending_sequence': navigations,
        'final_pending': out['reference_navigation']['pending'], 'needs_fulltext': out['needs_fulltext'],
        'method': 'real selector/expansion, scripted navigation status'})


def test_review_expansion_not_shown_to_another_sufficiency_check(session, monkeypatch):
    s, _ = session
    rec = record(s)
    monkeypatch.setattr(rel, 'navigate', lambda q, sess, selected, invoke, **kw: no_navigation(selected))
    reviews = []
    def invoke(system, data, schema, phase, timeout):
        if phase.endswith('triage'):
            return choice(data, 'exact:3')
        reviews.append([v['text'] for v in data['sources']])
        value = choice(data, 'subtree:1')
        value.update(evidence_sufficient=False, sufficiency_reason='일반 승인 제한도 펼쳐 확인해야 한다')
        return value
    out = us.select('승인 비교', rec, invoke, session=s.sources, remaining_seconds=120, max_fulltext_chars=80000)
    assert len(reviews) == 1 and all('일반 승인' not in t for t in reviews[0])
    assert any('일반 승인' in v['text'] for v in out['selected_originals'])
    assert out['needs_fulltext']
    OBSERVATIONS.append({'id': 'P5', 'review_count': len(reviews),
        'new_original_in_review': False, 'new_original_in_final': True,
        'needs_fulltext': out['needs_fulltext'], 'method': 'real selector/reader, scripted sufficiency'})


@pytest.mark.parametrize('connected', ['① 「모의승인규정」 제1조제1항을 준용하며 예외는 다음 각 호와 같다.'], indirect=True)
def test_previously_scanned_source_can_gain_an_unexamined_required_link(connected):
    s, _ = connected
    rec, sid = initial(s)
    state = {'count': len(rec['actions']), 'chars': rec['source_chars']}
    detail = next(v for v in s.tools.sources.values() if v['document_id'] == 'detail')
    h = rel.hit_for(s, detail['id'], '2')
    r = ur.read(s, h, ur.offers(s, h)[0], action_state=state)
    selected = {'U1': rec['unit_reads'][0], 'U2': r}
    phases = []
    def invoke(system, data, schema, phase, timeout):
        phases.append(phase)
        value = decision(data)
        chosen = next(g for g in data['groups'] if g['target']['document_id'] == 'detail')
        next(d for d in value['decisions'] if d['id'] == chosen['id']).update(
            action='FOLLOW', scopes=['subtree:1'], applicability='APPLIES')
        return value
    out = rel.navigate('승인 예외', s, selected, invoke, read_state=state,
        seconds_left=lambda: 120, max_context_chars=80000)
    groups, statuses, limits, unresolved = rel.catalog(s, [detail['id']], selected, set())
    unread_required = [c for g in groups for c in g['connections']
        if c['reading_policy']['obligation'] == 'REQUIRED' and not c['already_read']]
    assert len(phases) == 1 and not out['pending'] and unread_required
    OBSERVATIONS.append({'id': 'P6', 'model_phases': phases, 'reported_pending': out['pending'],
        'unexamined_required_connections_after_expansion': len(unread_required),
        'scanned_sources': out['scanned_anchors'], 'method': 'real reference index/catalog/navigation/reader'})


def test_next_navigation_reasks_the_same_skipped_link(connected):
    s, _ = connected
    rec, sid = initial(s)
    selected = {'U1': rec['unit_reads'][0]}
    state = {'count': len(rec['actions']), 'chars': rec['source_chars']}
    menus = []
    def invoke(system, data, schema, phase, timeout):
        menus.append([(g['anchor']['source_id'], g['target']['source_id'], g['direction'])
            for g in data['groups']])
        return decision(data)
    for prefix in ('source-reference-batch-', 'source-reference-batch-2-'):
        rel.navigate('승인', s, selected, invoke, read_state=state,
            seconds_left=lambda: 120, max_context_chars=80000, phase_prefix=prefix)
    assert len(menus) == 2 and menus[0] and menus[0] == menus[1]
    OBSERVATIONS.append({'id': 'P7', 'identical_menu_model_calls': len(menus),
        'method': 'real catalog/navigation; consecutive calls as candidate selector performs'})


def test_old_previews_displace_a_newly_acquired_candidate(session, monkeypatch):
    s, _ = session
    rec = record(s)
    monkeypatch.setattr(rel, 'navigate', lambda q, sess, selected, invoke, **kw: no_navigation(selected))
    views = []
    def invoke(system, data, schema, phase, timeout):
        if phase.startswith('source-unit-triage'):
            views.append(data)
        return {'issues': [], 'choices': [], 'needs_search': False,
            **({'evidence_sufficient': False, 'sufficiency_reason': '보고 규칙이 필요함'}
               if phase.startswith('source-unit-review') else {})}
    previous = us._select_batch('보고', rec, invoke, session=s.sources,
        remaining_seconds=120, max_fulltext_chars=80000)
    first = views[0]
    budget = 6000 + len(json.dumps({'laws': first['laws'], 'units': first['units']}, ensure_ascii=False)) + 1
    fresh = ur.acquire_batch(s.sources, [hit(s, '5')], previous['_read_state'])
    working = {**rec, 'unit_reads': rec['unit_reads'] + fresh, 'read_state': previous['_read_state']}
    out = us._select_batch('보고', working, invoke, session=s.sources,
        remaining_seconds=120, max_fulltext_chars=budget, previous=previous, batch_number=2)
    assert len(views) == 2 and views[0]['units'] == views[1]['units']
    assert views[1]['unpresented_units'] == 1 and fresh[0]['key'] in out['unpresented_unit_ids']
    OBSERVATIONS.append({'id': 'P8', 'max_context_chars': budget,
        'fresh_candidate_read': True, 'fresh_candidate_presented': False,
        'retained_old_preview_count': len(views[1]['units']),
        'method': 'real selector/acquisition at a controlled context boundary'})
