"""Cross-screen reference preservation with the real next-screen codec."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import navigation_tasks as tasks
from semantic_runtime.legal_agent import read_judgment as judgment
from semantic_runtime.legal_agent import action_choice_contract as choice
from semantic_runtime.legal_agent import task_review_context
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.completion_contracts import obj


def fixture(monkeypatch):
    from semantic_runtime.legal_agent import law_candidates
    monkeypatch.setattr(law_candidates, 'token', lambda s, p, v: p + digest(v)[:12])
    events = []
    inv = SimpleNamespace(question='동일 질문', policy={
        'task_local_navigation': True, 'read_judgment': True, 'execution_review': True},
        p={'binding': {'generation': 'synthetic-v1'}, 'untouched': {'value': True}})
    inv.s = SimpleNamespace(scope={'dA', 'dB', 'dC', 'dD'},
        repo=SimpleNamespace(event=lambda k, v: events.append((k, deepcopy(v)))))
    inv.save = lambda: None
    def page(name, source, doc, text):
        return {'id': name, 'source_id': source, 'document_id': doc, 'text': text,
            'spans': [{'block_id': name, 'start_cp': 0, 'end_cp': len(text), 'text': text}]}
    data = {'issues': [{'id': 'Q1'}], 'state_version': 3, 'presentation_id': 'P1',
        'chain_frame_id': 'F1', 'input_mode': 'REVIEW', 'references': {}, 'actions': [],
        'sources': [page('a', 'sA', 'dA', '법 본문'), page('a-parent', 'sA', 'dA', '필수 상위 조건'),
            page('b', 'sB', 'dB', '시행령 본문'), page('c', 'sC', 'dC', '관계없는 원문')]}
    visible = judgment.originals(inv, data)
    ids = {row['source_id']: jid for jid, row in visible.items()}
    heads = {jid: {'id': jid, 'source_id': row['source_id'], 'document_id': row['document_id'],
        'seen_material': row['material'], 'finding': '기존 의견', 'use': 'CORE'}
        for jid, row in visible.items()}
    state = {'version': judgment.VERSION, 'heads': heads,
        'needs': {'NC': {'id': 'NC', 'judgment_id': ids['sC'], 'status': 'OPEN'}},
        'conflicts': {}, 'final_reviews': [], 'receipts': {}}
    state['state_hash'] = judgment.seal(state)
    inv.p['read_judgments'] = {judgment.request_key(inv, data): state}
    inv.p['navigation_review_tasks'] = {'pending_judgments': {
        ids['sC']: {'judgment_id': ids['sC'], 'source_id': 'sC', 'document_id': 'dC', 'status': 'PENDING'}}}
    tasks.state(inv)['current'] = 'CONNECTION'
    actions = {name: {'id': name, 'action': kind, 'identity': {'source_id': 'sA'}, 'label': name}
        for name, kind in [('read', 'READ_ARTICLES'), ('follow', 'FOLLOW_CONNECTION'), ('search', 'RESEARCH')]}
    return inv, data, actions, ids, events


def depart(inv, data, actions, refs, *, source='a', relation='DIRECT'):
    data, offered = tasks.project(inv, data, actions)
    target = next(k for k, a in offered.items() if a['identity'].get('task') == 'REVIEW')
    proposal = {'choice': 'OPEN_TASK', 'target': target, 'issue_id': 'Q1',
        'missing_need': '확보 원문 판단 화면으로 이동', 'relation': relation,
        'source_ref': source, 'judgment_refs': refs}
    inv.p['executed_compact_choices'] = [deepcopy(proposal)]
    decision = {'next_action': 'OPEN_TASK', 'targets': [target], 'reason': proposal['missing_need']}
    tasks.execute(inv, decision, data, offered)
    future = {**deepcopy(data), 'sources': [], 'state_version': 4, 'presentation_id': 'P2'}
    future, offered = tasks.project(inv, future, actions)
    return future, offered, proposal


def prepare_next(inv, data):
    current = {p['id']: p for p in data['sources']}
    ctx = judgment.context(inv, data, 'next-screen')
    schema = {'type': 'object', 'anyOf': [obj({'choice': {'const': 'OPEN_TASK'},
        'target': {'enum': ['T-next']}, 'issue_id': {'enum': ['Q1']},
        'missing_need': {'type': 'string', 'minLength': 1},
        'relation': {'enum': ['DIRECT', 'DEPENDENCY']},
        'source_ref': {'enum': [None, *current]}})]}
    schema = judgment.attach(schema, ctx, current, ['Q1'], partial=True)
    wire, decode, _ = choice.prepare(schema, data)
    value = decode({'choice': 'OPEN_TASK', 'target': 'T-next'})
    assert task_review_context.reference_errors(value, ctx) == []
    return value, ctx


@pytest.mark.parametrize('relation', ['DIRECT', 'DEPENDENCY'])
def test_two_current_original_judgments_survive_next_screen_codec(monkeypatch, relation):
    inv, data, actions, ids, _ = fixture(monkeypatch)
    original_state = deepcopy(inv.p['read_judgments'])
    pending = deepcopy(inv.p['navigation_review_tasks']['pending_judgments'])
    sources = deepcopy(data['sources'])
    future, _, proposal = depart(inv, data, actions, [ids['sA'], ids['sB']], relation=relation)
    # Pre-fix code reaches the observed ContractError here, before a next call.
    value, _ = prepare_next(inv, future)
    assert value['judgment_refs'] == proposal['judgment_refs']
    assert value['source_ref'] == 'a' and value['relation'] == relation
    assert future['sources'] == sources[:3]
    assert inv.p['read_judgments'] == original_state
    assert inv.p['navigation_review_tasks']['pending_judgments'] == pending
    assert inv.p['untouched'] == {'value': True}


def test_source_free_direct_anchor_carries_only_explicit_judgment_original(monkeypatch):
    inv, data, actions, ids, _ = fixture(monkeypatch)
    future, _, proposal = depart(inv, data, actions, [ids['sB']], source=None)
    value, _ = prepare_next(inv, future)
    assert value['source_ref'] is None and value['judgment_refs'] == proposal['judgment_refs']
    assert [p['source_id'] for p in future['sources']] == ['sB']


def test_single_original_keeps_all_parent_pages_and_omits_other_groups(monkeypatch):
    inv, data, actions, ids, _ = fixture(monkeypatch)
    future, _, _ = depart(inv, data, actions, [ids['sA']], relation='DEPENDENCY')
    value, _ = prepare_next(inv, future)
    assert value['judgment_refs'] == [ids['sA']]
    assert [p['id'] for p in future['sources']] == ['a', 'a-parent']


def test_direct_open_conflict_reference_keeps_its_current_seed_without_transitive_walk(monkeypatch):
    inv, data, actions, ids, _ = fixture(monkeypatch)
    state = judgment.state_for(inv, data)
    state['heads']['JD'] = {'id': 'JD', 'source_id': 'sD', 'document_id': 'dD', 'seen_material': []}
    state['conflicts'] = {
        'BD': {'id': 'BD', 'status': 'OPEN', 'opinions': [state['heads'][ids['sB']], state['heads']['JD']]},
        'DC': {'id': 'DC', 'status': 'OPEN', 'opinions': [state['heads']['JD'], state['heads'][ids['sC']]]}}
    state['state_hash'] = judgment.seal(state)
    # D's open conflicts are both incident to current originals. Both current
    # seeds are needed to retain the exact allowed opinion without inventing D.
    before = deepcopy(state)
    future, _, _ = depart(inv, data, actions, ['JD'])
    value, ctx = prepare_next(inv, future)
    assert value['judgment_refs'] == ['JD']
    assert {p['source_id'] for p in future['sources']} == {'sA', 'sB', 'sC'}
    assert all(p['source_id'] != 'sD' for p in future['sources'])
    assert state == before and set(ctx['task_scope']['related_judgment_ids']) == {*ids.values(), 'JD'}


def test_unrelated_closed_conflict_does_not_expand_departure(monkeypatch):
    inv, data, actions, ids, _ = fixture(monkeypatch)
    state = judgment.state_for(inv, data)
    state['conflicts'] = {'BC': {'id': 'BC', 'status': 'RESOLVED',
        'opinions': [state['heads'][ids['sB']], state['heads'][ids['sC']]]}}
    state['state_hash'] = judgment.seal(state)
    future, _, _ = depart(inv, data, actions, [ids['sB']])
    prepare_next(inv, future)
    assert {p['source_id'] for p in future['sources']} == {'sA', 'sB'}


def test_return_and_subsequent_native_action_release_only_departure_context(monkeypatch):
    inv, data, actions, ids, _ = fixture(monkeypatch)
    before = deepcopy(inv.p['read_judgments'])
    future, offered, _ = depart(inv, data, actions, [ids['sA'], ids['sB']])
    back = next(k for k, a in offered.items() if a['identity'].get('task') == 'CONNECTION')
    tasks.execute(inv, {'next_action': 'OPEN_TASK', 'targets': [back], 'reason': '명시적 복귀'}, future, offered)
    assert 'origin' not in tasks.state(inv) and 'origin_sources' not in tasks.state(inv)
    assert inv.p['read_judgments'] == before
    tasks.after_action(inv, {'next_action': 'READ_ARTICLES'})
    assert tasks.state(inv)['current'] == 'REVIEW' and inv.p['read_judgments'] == before


def test_invalid_reference_is_not_added_to_schema_and_checkpoint_is_unchanged(monkeypatch):
    inv, data, actions, ids, _ = fixture(monkeypatch)
    data, offered = tasks.project(inv, data, actions)
    target = next(k for k, a in offered.items() if a['identity'].get('task') == 'REVIEW')
    inv.p['executed_compact_choices'] = [{'choice': 'OPEN_TASK', 'target': target,
        'issue_id': 'Q1', 'missing_need': '목적', 'relation': 'DIRECT', 'source_ref': 'a',
        'judgment_refs': ['unknown']}]
    before = deepcopy(inv.p)
    with pytest.raises(ContractError, match='cannot preserve'):
        tasks.execute(inv, {'next_action': 'OPEN_TASK', 'targets': [target], 'reason': '목적'}, data, offered)
    assert inv.p == before


def test_departure_never_accepts_unauthorized_current_original(monkeypatch):
    inv, data, actions, ids, _ = fixture(monkeypatch)
    inv.s.scope.remove('dB')
    with pytest.raises(ContractError, match='outside authorized scope'):
        depart(inv, data, actions, [ids['sB']])


def test_recorded_cm023_proposal_and_original_state_survive_same_codec():
    root = Path(__file__).resolve().parents[3]
    path = root / '04_EXPERIMENTS/ADR/ADR-1077-ontology-task-departure-reference-closure/artifacts/recorded-transition-slice.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '82a622c872259b2f4358d46de50cfab40f0f69a625c0a82ee37c0f707aca35ef'
    saved = json.loads(path.read_text())
    for item in saved['provenance']:
        assert hashlib.sha256((root/item['path']).read_bytes()).hexdigest() == item['sha256']
    inv = SimpleNamespace(question=saved['question'], p=deepcopy(saved['p']), policy={
        'task_local_navigation': True, 'execution_review': True, 'read_judgment': True})
    inv.s = SimpleNamespace(scope=set(saved['allowed_documents']),
        repo=SimpleNamespace(event=lambda *_: None))
    data = deepcopy(saved['data'])
    before = deepcopy(inv.p['read_judgments'])
    proposal = inv.p['executed_compact_choices'][-1]
    tasks.execute(inv, {'next_action': 'OPEN_TASK', 'targets': [proposal['target']],
        'reason': proposal['missing_need']}, data, saved['actions'])
    frame = tasks.state(inv)
    # Exact pure transition boundary, not a replay of retrieval or model calls.
    future = {**deepcopy(data), 'sources': deepcopy(frame['origin_sources']),
        'task_navigation': {'task': 'REVIEW', 'departure': deepcopy(frame['origin'])}}
    value, _ = prepare_next(inv, future)
    assert value['judgment_refs'] == saved['expected_judgment_refs']
    assert sorted({p['source_id'] for p in future['sources']}) == saved['expected_original_groups']
    assert future['sources'] == data['sources']  # Both groups, all 25 exact pages.
    assert inv.p['read_judgments'] == before
    assert len({p['source_id'] for p in saved['stored_incomplete_origin_sources']}) == 1
