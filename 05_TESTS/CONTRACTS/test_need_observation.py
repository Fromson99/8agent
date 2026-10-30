"""Independent declaration persistence; no live model calls or action recovery."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import gzip
import json

import pytest
from semantic_runtime.legal_agent import answer_progress as progress
from semantic_runtime.legal_agent import investigation_supervisor as su
from semantic_runtime.legal_agent import need_continuity as nc, read_judgment as rj
from semantic_runtime.legal_agent import read_judgment_final as final
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_need_continuity import declaration
from test_read_judgment import setup, options


def fixture():
    inv, data, page, events, saved = setup()
    inv.p['state_version'] = 3
    data.update(state_version=3, presentation_id='P3')
    schema = {'anyOf': [{'properties': {'answer_progress': progress.schema(
        {s['id']: s for s in data['sources']}, data['issues'], False)}}]}
    value = declaration()
    value['answer_progress']['goals'][0]['previous_effect'] = 'INITIAL'
    observer = nc.observe_progress(inv, data, schema, 'selection-3')
    return inv, data, value, observer, events, saved


def test_observation_is_open_and_does_not_accept_action_judgment_goal_or_budget():
    inv, data, value, observe, events, saved = fixture()
    before = deepcopy(su.state_for(inv, data))
    value.update(choice='FOLLOW_CONNECTION', target='unoffered', judgment_refs=['fake'])
    observe(value, 'first')
    st = su.state_for(inv, data)
    assert all(st[k] == v for k, v in before.items() if k != 'state_hash')
    assert len(st['material_needs']) == len(st['need_declaration_receipts']) == 1
    need = next(iter(st['material_needs'].values()))
    assert need['status'] == 'OPEN'
    assert all(not d['action_execution_confirmed'] for d in need['declarations'])
    assert 'read_judgments' not in inv.p
    assert len(saved) == len(events) == 1
    assert events[0][0] == 'NEED_DECLARATION_OBSERVED'
    assert events[0][1]['action_accepted'] is events[0][1]['judgments_adopted'] is False
    ctx = final.context(inv.p, inv.question, data['issues'], options(data), inv.s.scope)
    assert any(n['id'] == need['id'] and n['text'] == need['text'] for n in ctx['needs'])
    assert ctx['need_continuity']['latest_goals'] == []


def test_retry_serialized_restart_and_event_gap_do_not_duplicate_or_call_model():
    inv, data, value, observe, events, saved = fixture()
    observe(value, 'first')
    inv.p = json.loads(json.dumps(inv.p))
    observe(value, 'first')
    observe(value, 'repair')
    st = su.state_for(inv, data)
    assert len(st['material_needs']) == 1 and len(st['need_declaration_receipts']) == 2
    assert len(next(iter(st['material_needs'].values()))['declarations']) == 1
    assert len(events) == len(saved) == 2
    value['answer_progress']['goals'][0]['material_need'] = '수정된 별도 필요'
    with pytest.raises(ContractError, match='changed'):
        observe(value, 'first')
    observe(value, 'new-response')
    assert len(st['material_needs']) == 2


@pytest.mark.parametrize('fault', ['missing', 'fake_issue', 'fake_basis', 'duplicate_issue',
    'blank_need', 'blank_change', 'wrong_status', 'wrong_effect', 'oversized', 'wrong_type'])
def test_invalid_progress_is_not_salvaged(fault):
    inv, data, value, observe, events, saved = fixture()
    goal = value['answer_progress']['goals'][0]
    if fault == 'missing': del value['answer_progress']
    elif fault == 'fake_issue': goal['issue_id'] = 'other'
    elif fault == 'fake_basis': goal['basis_refs'] = ['unoffered']
    elif fault == 'duplicate_issue': value['answer_progress']['goals'].append(deepcopy(goal))
    elif fault == 'blank_need': goal['material_need'] = '  '
    elif fault == 'blank_change': goal['next_answer_change'] = '  '
    elif fault == 'wrong_status': goal['status'] = 'RESOLVED'
    elif fault == 'wrong_effect': goal['previous_effect'] = 'ANSWER_CHANGED'
    elif fault == 'oversized': goal['material_need'] = 'x' * 401
    elif fault == 'wrong_type': goal['material_need'] = None
    before = deepcopy(inv.p)
    observe(value, 'first')
    assert inv.p == before and not events and not saved


@pytest.mark.parametrize('fault', ['request', 'binding', 'version', 'presentation', 'scope',
    'source_bytes', 'source_identity', 'state_hash', 'unconfirmed_delivery'])
def test_stale_or_untrusted_original_cannot_create_need(fault):
    inv, data, value, observe, events, saved = fixture()
    su.state_for(inv, data)
    if fault == 'request': data['current_request'] = '다른 질문'
    elif fault == 'binding': inv.p['binding'] = 'other'
    elif fault == 'version': inv.p['state_version'] += 1
    elif fault == 'presentation': data['presentation_id'] = 'other'
    elif fault == 'scope': inv.s.scope = set()
    elif fault == 'source_bytes': inv.s.store.source = lambda *a: {'text': '바뀐 원문'}
    elif fault == 'source_identity': inv.p['selected']['a']['source_id'] = 'other'
    elif fault == 'state_hash': su.state_for(inv, data)['turns'] += 1
    elif fault == 'unconfirmed_delivery': inv.control = True
    with pytest.raises(ContractError): observe(value, 'first')
    assert not events and not saved


def test_answerable_and_accepted_record_keep_one_declaration_and_no_silent_close():
    inv, data, value, observe, events, saved = fixture()
    observe(value, 'first')
    su.record(inv, data, value, 'selection-3')
    before = deepcopy(su.state_for(inv, data)['material_needs'])
    assert len(next(iter(before.values()))['declarations']) == 1
    value['answer_progress']['goals'][0].update(status='ANSWERABLE', material_need='', next_answer_change='')
    observe(value, 'repair')
    assert su.state_for(inv, data)['material_needs'] == before


def test_checkpoint_failure_rolls_back_uncommitted_need():
    inv, data, value, observe, events, saved = fixture()
    before = deepcopy(su.state_for(inv, data))
    def fail(): raise OSError('synthetic checkpoint failure')
    inv.save = fail
    with pytest.raises(OSError): observe(value, 'first')
    assert su.state_for(inv, data) == before and not events


def test_saved_1205_initial_and_repair_still_reject_action_but_retain_need_in_final():
    root = Path(__file__).resolve().parents[2]
    base = root / '04_EXPERIMENTS/ADR/ADR-1205-need-continuity-live-cm009/artifacts/live/cm-009'
    def read(name):
        p = base / name
        return json.loads(gzip.decompress(p.read_bytes()))
    state = read('states/006.json.gz')
    first = read('canonical/002.json.gz')
    view = first['view']
    raw = {}
    for source in view['sources']:
        for span in source['spans']:
            key = (source['document_id'], span['block_id'])
            chars = raw.setdefault(key, [])
            chars.extend(' ' * max(0, span['end_cp'] - len(chars)))
            chars[span['start_cp']:span['end_cp']] = span['text']
    # This fixture checks binding to the frozen delivered bytes. Corpus byte
    # verification was recorded by ADR1205; no claim of a new DB audit here.
    inv = SimpleNamespace(p=state, question=view['request'], control=True)
    inv.s = SimpleNamespace(scope={s['document_id'] for s in view['sources']},
        store=SimpleNamespace(source=lambda did, block: {'text': ''.join(raw[did, block])}),
        repo=SimpleNamespace(event=lambda *a: None))
    inv.save = lambda: None
    before = deepcopy(su.state_for(inv, view))
    unchanged = {k: deepcopy(v) for k, v in state.items() if k != 'investigation_supervisor'}
    observe = nc.observe_progress(inv, view, first['schema'], 'saved-1205')
    for number in ('002', '003'):
        request = read(f'canonical/{number}.json.gz')
        value = read(f'canonical/{number}-output.json.gz')
        ctx = request['view']['read_judgments']
        with pytest.raises(ProposalError, match='judgment'):
            normalized, _ = rj.normalize_review(value, ctx)
            rj.validate_review(normalized, ctx, {s['id']: s for s in view['sources']},
                [i['id'] for i in view['issues']])
        observe(value, number)
    after = su.state_for(inv, view)
    assert all(after[k] == v for k, v in before.items() if k != 'state_hash')
    assert {k: v for k, v in inv.p.items() if k != 'investigation_supervisor'} == unchanged
    assert len(after['material_needs']) == 1 and len(after['need_declaration_receipts']) == 2
    need = next(iter(after['material_needs'].values()))
    opts = read('canonical/004.json.gz')['view']['evidence_options']
    allowed = {o['document_id'] for o in opts} | inv.s.scope
    ctx = final.context(inv.p, view['current_request'], view['issues'], opts, allowed)
    assert any(n['id'] == need['id'] and n['text'] == need['text'] for n in ctx['needs'])
    assert '대형법인' in need['text'] and '적격 해외증권시장' in need['text']
    assert ctx['need_continuity']['latest_goals'] == []
