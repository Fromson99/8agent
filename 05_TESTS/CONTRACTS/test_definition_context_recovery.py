"""Small in-memory state probes: no source generation or model calls."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace as S
import time

import pytest

from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import definition_context as dc, tool_availability as availability
from semantic_runtime.legal_agent import law_candidates as lc, query_scope as qs, unit_reading as ur
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.law_navigation import Investigation


def material(sid, block, text):
    span = {'block_id': block, 'start_cp': 0, 'end_cp': len(text), 'text': text}
    evidence = {'evidence_id': 'e' + sid + block, 'source_id': sid, 'spans': [span]}
    return {'source_id': sid, 'document_id': sid, 'article_unit_id': '0', 'unit_id': block,
        'complete': True, 'text': text, 'evidence': [evidence], 'evidence_ids': [evidence['evidence_id']],
        'offer': {'id': 'subtree:' + block, 'unit_id': block, 'extent': 'subtree',
                  'block_ids': [block], 'chars': len(text)}}


@pytest.fixture
def context_probe(monkeypatch):
    primary = material('a', '0', '선택 원문')
    body = material('b', '2', '이미 확보한 연결 본문')
    parent = material('b', '1', '상위 조건')
    hit = {'source_id': 'b', 'document_id': 'b', 'unit_id': '2', 'article_unit_id': '0', 'heading': '연결 조항'}
    offer = body['offer']
    group = {'id': 'B', 'source_id': 'b', 'law_id': 'L', 'hit': hit, 'offer': offer,
             'status': 'CANDIDATE', 'reason': '', 'page_plan': [], 'delivery': 0}
    events = []; snapshots = []; read_calls = []
    raw = {('a', '0'): primary['text'], ('b', '2'): body['text'], ('b', '1'): parent['text'], ('b', '3'): '이전 범위'}
    def verify(evidence):
        for span in evidence['spans']:
            assert span['text'] == raw[(evidence['source_id'], span['block_id'])][span['start_cp']:span['end_cp']]
    s = S(scope=['a', 'b'], profile={'max_read_chars': 1000},
        source=S(verify=verify), store=S(source=lambda did, bid: {'text': raw[(did, str(bid))]}),
        context=S(binding_hash='binding', deadline=time.monotonic() + 60),
        repo=S(event=lambda *args: events.append(args), evidence=lambda: [],
               budget=lambda: {'tool_used': 1, 'tool_limit': 20, 'model_reserved': 1, 'model_limit': 10}),
        resolve=lambda handle, kind: {'source_id': 'b', 'document_id': 'b', 'block_ids': ['1']})
    p = {'binding': {'test': 'context'}, 'requested_originals': ['A'], 'selected': {'A': primary},
         'groups': {'A': {'status': 'READ'}, 'B': group}, 'contexts': {}, 'material_history': {},
         'basis_history': {}, 'read_state': {}, 'laws': {'L': {'name': '연결 규정'}}}
    inv = S(s=s, p=p, control=True, completion=True, policy={'definition_context': True})
    for name in ('register_read', 'read_records', 'plan_pages', 'render_page'):
        setattr(inv, name, getattr(Investigation, name).__get__(inv))
    inv.save = lambda: snapshots.append(deepcopy(p))
    inv.add_reads = lambda reads: None
    link = {'reference_id': 'r', 'already_read': False, 'defines_anchor_wording': {'quote': '위임 문구'}, 'endpoint_scopes': ['scope']}
    relation = {'direction': 'INCOMING', 'connections': [link], 'offers': {'scope': (hit, offer)}}
    monkeypatch.setattr(dc.cs, 'bound', lambda *args: nullcontext())
    monkeypatch.setattr(dc.rel, 'catalog', lambda *args: ([relation], [], [], []))
    monkeypatch.setattr(lc, 'token', lambda *args: 'B')
    monkeypatch.setattr(lc, 'parent_offer', lambda *args: offer)
    monkeypatch.setattr(availability, 'article_plan', lambda *args: ((hit, offer), None))
    monkeypatch.setattr(availability, 'context_plans', lambda *args: [(hit, parent['offer'])])
    # This fake reports the actual two offered extents, not a fixed target-only cost.
    monkeypatch.setattr(availability, 'sequence_cost', lambda s, plans, evidence: (sum(o['chars'] for h, o in plans), len(plans)))
    def read(*args, **kwargs):
        read_calls.append(1)
        return deepcopy(body)
    monkeypatch.setattr(ur, 'read', read)
    monkeypatch.setattr(ur, 'ensure_context', lambda *args: None)
    return S(inv=inv, body=body, parent=parent, group=group, calls=read_calls, snapshots=snapshots, events=events)


def test_body_and_completed_context_remain_deliverable_after_later_context_failure(context_probe, monkeypatch):
    f = context_probe; inv = f.inv
    old = material('b', '3', '이전 범위'); inv.p['selected']['B'] = old
    def context(s, records, state):
        assert set(records) == {'B'}  # old scopes stay delivered, not re-expanded
        records['CONTEXT:parent'] = f.parent
        raise TimeoutError('next ancestor unavailable')
    monkeypatch.setattr(ur, 'ensure_context', context)
    with pytest.raises(TimeoutError):
        inv.register_read(f.group, f.body, reason='연결 확인')
    assert inv.p['material_history'][digest(['B', old['offer']])] == old
    assert f.group['delivery_requested'] and f.group['delivery'] < len(f.group['page_plan'])
    page = inv.render_page(f.group, 0)
    assert all(text in page['text'] for text in (f.body['text'], f.parent['text'], old['text']))
    assert f.snapshots[0]['groups']['B']['page_plan']  # durable before context I/O
    assert not inv.p['basis_history']  # acquisition never impersonates model delivery


@pytest.mark.parametrize('error', [ContractError('hash mismatch'), PermissionError('ACL denied')])
def test_context_integrity_failure_is_not_downgraded(context_probe, monkeypatch, error):
    f = context_probe
    monkeypatch.setattr(ur, 'ensure_context', lambda *args: (_ for _ in ()).throw(error))
    with pytest.raises(type(error), match=str(error)):
        dc.acquire(f.inv, ['A'])
    assert f.group['page_plan'] and not f.inv.p.get('tool_failures')


def test_auto_context_failure_records_only_failed_ancestor_and_preserves_body(context_probe, monkeypatch):
    f = context_probe; error = TimeoutError('ancestor unavailable')
    error.read_progress = {'remaining_target': {'target': 'P-parent'}, 'completed_receipt_refs': []}
    monkeypatch.setattr(ur, 'ensure_context', lambda *args: (_ for _ in ()).throw(error))
    assert dc.acquire(f.inv, ['A']) == ['B']
    row, = f.inv.p['tool_failures']
    assert row['status'] == 'PARTIAL' and row['failure_stage'] == 'CONTEXT'
    assert row['failed_scope'] == {'source_id': 'b', 'document_id': 'b', 'block_ids': ['1']}
    assert row['completed_group_id'] == 'B' and row['recovery_policy']['owner'] == 'investigation'
    assert f.body['text'] in f.inv.render_page(f.group, 0)['text']
    before = deepcopy(f.inv.p['definition_context'])
    assert dc.acquire(f.inv, ['A']) == ['B'] and f.calls == [1]
    assert f.inv.p['definition_context'] == before and len(f.inv.p['tool_failures']) == 1
    assert not any(name == 'INVESTIGATION_CHAIN_STEP' for name, *_ in f.events)


def test_auto_body_failure_keeps_exact_failed_scope_and_does_not_retry(context_probe, monkeypatch):
    f = context_probe; calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise TimeoutError('body unavailable')
    monkeypatch.setattr(ur, 'read', fail)
    assert dc.acquire(f.inv, ['A']) == []
    row, = f.inv.p['tool_failures']
    assert row['failure_stage'] == 'READ' and row['failed_scope']['block_ids'] == ['2']
    assert row['completed_group_id'] is None and 'B' not in f.inv.p['selected']
    assert dc.acquire(f.inv, ['A']) == [] and calls == [1]


def test_context_character_bound_includes_ancestor_cost_before_read(context_probe, monkeypatch):
    f = context_probe
    monkeypatch.setattr(dc, 'MAX_CHARS', len(f.body['text']))
    assert dc.acquire(f.inv, ['A']) == [] and f.calls == []
    state = f.inv.p['definition_context']
    assert state['reserved_chars'] == 0
    assert next(iter(state['anchors'].values()))['omitted'][0]['reason'] == 'CONTEXT_BOUND'


def test_scope_ancestor_cost_prediction_does_not_create_a_read_grant(monkeypatch):
    hit = {'source_id': 's', 'document_id': 'd', 'article_unit_id': '0', 'unit_id': '1'}
    s = S(matcher=S(units={('d', '1'): {'parent': '0'}, ('d', '0'): {'parent': None}}),
          tools=S(sources={'s': {'blocks': [{'block_id': '0'}, {'block_id': '1'}]}}))
    monkeypatch.setattr(availability.rel, 'hit_for', lambda *args: {**hit, 'unit_id': str(args[-1])})
    monkeypatch.setattr(ur, 'offers', lambda *args: [])  # ancestor grant awaits successful child read
    monkeypatch.setattr(ur, 'exact_offer', lambda *args: {'extent': 'exact', 'block_ids': ['0'], 'chars': 13000})
    monkeypatch.setattr(qs, 'active', lambda *args: {'targets': []})
    monkeypatch.setattr(qs, 'permitted_blocks', lambda *args: {'1'})
    monkeypatch.setattr(qs, 'grant', lambda *args, **kwargs: pytest.fail('cost prediction must not grant access'))
    plans = availability.context_plans(s, hit, {'unit_id': '1', 'block_ids': ['1']})
    assert len(plans) == 1 and plans[0][1]['block_ids'] == ['0'] and plans[0][1]['chars'] == 13000
    assert availability.context_plans(s, hit, {'unit_id': '1', 'block_ids': ['ungranted']}) == []
