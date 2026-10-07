"""Selected introductions must deliver their actual children, even at the bound."""
from test_exact_anchor_delegation_read import *


def follow_intro(s, record, observations):
    def invoke(system, data, schema, phase, timeout):
        observations.append((phase, data))
        if phase == 'source-unit-triage':
            return {'issues': ['승인 예외'], 'choices': [{'id': data['units'][0]['id'],
                'scope': 'exact:2', 'reason': '긴급 승인 원칙을 확인한다'}], 'needs_search': False}
        if phase.startswith('source-reference-batch'):
            value = decision(data)
            if data['round'] == 1:
                target = next(g for g in data['groups'] if g['target']['document_id'] == 'detail')
                next(d for d in value['decisions'] if d['id'] == target['id']).update(
                    action='FOLLOW', scopes=['exact:1'])
            return value
        return {'issues': [], 'choices': [], 'needs_search': False}
    return select_sources('긴급 승인 예외', record, invoke, remaining_seconds=120, session=s)


def test_last_round_follow_delivers_children_but_unexamined_links_remain_pending(connected, monkeypatch):
    s, _ = connected
    record, _ = initial(s)
    monkeypatch.setitem(rel.LIMITS, 'rounds', 1)
    seen = []
    out = follow_intro(s, record, seen)
    review = next(data for phase, data in seen if phase == 'source-unit-review')
    detail = next(row for row in review['sources'] if row['document_id'] == 'detail')
    assert '책임자 확인 후 승인한다.' in detail['text']
    assert '정해진 보고를 한다.' in detail['text']
    assert '제2조 예외' not in detail['text']
    assert out['status'] == 'pending' and out['needs_fulltext']
    assert len(seen) == 3  # triage, one navigation decision, review
    assert any(r['kind'] == 'LOCAL_ENUMERATION' and r['status'] == 'READ'
               for r in out['reference_navigation']['required_reads'])


def test_chosen_intro_completes_without_model_call_per_child(connected):
    s, _ = connected
    record, _ = initial(s)
    seen = []
    out = follow_intro(s, record, seen)
    assert out['status'] == 'complete'
    assert len(seen) == 4
    detail = next(row for row in out['selected_originals'] if row['document_id'] == 'detail')
    assert {'exact:1', 'subtree:1'} <= {o['id'] for o in detail['read_scopes']}
    assert {e['source_id'] for e in out['selected_evidence']} == set(out['final_ids'])


def test_chosen_intro_children_respect_required_read_limit(connected, monkeypatch):
    s, _ = connected
    record, _ = initial(s)
    monkeypatch.setitem(dep.LIMITS, 'chars', 1)
    seen = []
    out = follow_intro(s, record, seen)
    assert out['status'] == 'pending'
    detail = next(row for row in out['selected_originals'] if row['document_id'] == 'detail')
    assert '책임자 확인 후 승인한다.' not in detail['text']
    assert any(r['kind'] == 'LOCAL_ENUMERATION' and r['reason'] == 'required_read_budget'
               for r in out['reference_navigation']['required_reads'] if r['status'] == 'UNRESOLVED')


def test_new_unit_in_same_article_is_examined_again(connected):
    s, _ = connected
    record, sid = initial(s)
    seen = []
    def invoke(system, data, schema, phase, timeout):
        seen.append(phase)
        if phase == 'source-unit-triage':
            return {'issues': [], 'choices': [{'id': data['units'][0]['id'],
                'scope': 'exact:2', 'reason': '긴급 승인 원칙'}], 'needs_search': False}
        if phase.startswith('source-reference-batch'):
            value = decision(data)
            did = 'detail' if data['round'] == 1 else 'd' if data['round'] == 2 else None
            target = next((g for g in data['groups'] if g['target']['document_id'] == did), None)
            if target:
                next(d for d in value['decisions'] if d['id'] == target['id']).update(
                    action='FOLLOW', scopes=['exact:1' if did == 'detail' else 'subtree:0'])
            return value
        return {'issues': [], 'choices': [], 'needs_search': False}
    out = select_sources('긴급 승인 예외', record, invoke, remaining_seconds=120, session=s)
    assert out['status'] == 'complete'
    assert 'source-reference-batch-3' in seen
    assert set(out['reference_navigation']['scanned_unit_focus'][sid]) == {'0', '2'}
    root = next(row for row in out['selected_originals'] if row['document_id'] == 'd')
    assert '일반 승인은 제한한다.' in root['text']
