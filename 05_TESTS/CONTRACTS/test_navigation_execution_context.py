"""Executed state survives the final navigation wire; no live model involved."""
from copy import deepcopy
from types import SimpleNamespace as S

from semantic_runtime.legal_agent import decision_projection as dp
from semantic_runtime.legal_agent import investigation_chain as trail
from semantic_runtime.legal_agent.navigation_input import expand_cards
from test_read_choice_input_preservation import unit, wire
from test_navigation_scope_memory import memory
from conftest import term_glossary


def test_return_wire_keeps_every_executed_target_result_and_reused_original(monkeypatch):
    inv, data, actions, payloads, _ = unit.fixture(monkeypatch, unit.choice(queries=['미확보 조건']))
    steps = [{'id':f'S{i}', 'number':i + 1, 'action':'READ_ARTICLES',
              'status':'APPLIED' if i % 2 == 0 else 'FAILED',
              'reason':'원문 조건 확인',
              'targets':[{'id':f'T{i}', 'label':f'모의규정 제{i+1}조',
                          'identity':{'document_id':'D1', 'source_id':f'A{i}', 'unit_id':str(i)}}],
              'outcome':{'original_acquired':i % 2 == 0}, 'queries':[], 'basis_refs':[]}
             for i in range(12)]
    data['investigation_chain'] = {'steps':steps, 'current_frame':'H1',
        'memory_rule':'복귀해도 확보 원문과 실행 결과를 유지한다.'}
    data['investigation_chain'] = trail.compact(data['investigation_chain'], brief=True)
    data['return_context'] = {'frame_id':'H1', 'reason':'이전 후보의 다른 연결을 확인한다.'}
    data['already_presented_reads'] = [{'action_id':'OLD', 'source_id':'A0', 'basis_refs':['E1']}]
    inv.p['executed_compact_choices'] = [{'choice':'READ', 'selections':[{'target':'UNEXECUTED'}]}]
    before = deepcopy(data)
    dp.choose_read(inv, data, actions, 'execution-context')
    shown = expand_cards(wire(payloads[0]))
    assert data == before
    assert len(shown['investigation_chain']['steps']) == len(steps)
    for original, received in zip(steps, shown['investigation_chain']['steps']):
        assert received['status'] == original['status']
        assert received['outcome'] == original['outcome']
        assert received['targets'][0]['label'] == original['targets'][0]['label']
        assert received['targets'][0]['location'] == original['targets'][0]['identity']
    assert shown['return_context'] == data['return_context']
    assert shown['already_presented_reads'] == data['already_presented_reads']
    assert 'previous_choices' not in shown
    assert 'recent_outcomes' not in shown['navigation_feedback']


def test_empty_chain_does_not_claim_selected_proposal_executed(monkeypatch):
    inv, data, actions, payloads, _ = unit.fixture(monkeypatch, unit.choice(queries=['원문']))
    inv.p['executed_compact_choices'] = [{'choice':'READ', 'selections':[{'target':'NOT_RUN'}]}]
    dp.choose_read(inv, data, actions, 'empty-execution-context')
    shown = wire(payloads[0])
    assert not shown['investigation_chain'].get('steps')
    assert shown['return_context'] is None
    assert shown['already_presented_reads'] == []


def test_actual_read_record_consumer_keeps_history_and_current_exclusion(memory):
    from semantic_runtime.legal_agent.law_navigation import Investigation
    session, state, wide, _, _ = memory
    actor = S(p=state, completion=True)
    assert wide in Investigation.read_records(actor).values()
    state['groups']['B']['status'] = 'EXCLUDED'
    assert not Investigation.read_records(actor)
    state['groups']['B']['delivery_requested'] = True
    assert wide in Investigation.read_records(actor).values()


def test_partial_active_original_offers_first_missing_page(memory, monkeypatch):
    session, state, wide, page, _ = memory
    state['selected']['B'] = wide
    state['basis_history'] = {}
    state['groups']['B'].update(status='ACTIVE', page_plan=[[p] for p in page['spans']])
    session.profile = {'max_read_chars':100, 'max_context_chars':1000}
    actor = S(s=session, p=state)
    data = {'sources':[{**page, 'spans':page['spans'][:1], 'text':'abc'}], 'basis':[],
            'saved_inventory':[{'material_id':'B', 'status':'ACTIVE'}]}
    from semantic_runtime.legal_agent import law_candidates
    monkeypatch.setattr(law_candidates, 'token', lambda *args:'VIEW')
    actions = {}
    dp.retain_requested(actor, data, actions)
    row = data['saved_inventory'][0]
    assert row['presented_any'] and not row['presented_complete']
    assert actions[row['view_action']]['identity'] == {'branch_id':'B', 'page':1}


def test_api_navigation_wire_keeps_executed_reads_and_exact_connection_witnesses(tmp_path, term_glossary, monkeypatch):
    import json
    from semantic_runtime.legal_agent.bounded_source_session import _Gateway
    from test_answer_progress_api import test_progress_actual_api_originals_links_handoff_and_duplicate as run
    calls = []; reference_calls = []
    original = _Gateway.request
    def capture(self, *args, **kwargs):
        body = original(self, *args, **kwargs)
        view = expand_cards(json.loads(body['messages'][1]['content'])['view'])
        if '-read-choice' in view.get('source_stage',''):
            for card, canonical in zip(view['references']['dependency_cards'], args[1]['references']['dependency_cards']):
                witness=card['reference_witness']
                if 'text_ref' in witness:
                    ref=witness['text_ref']
                    source=next(s for s in view['sources'] if s['text_id']==ref['id'])
                    assert source['source_id']==witness['source_id']
                    exact=source['text'][ref['start']:ref['end']]
                else:exact=witness['text']
                assert exact==canonical['reference_witness']['text']
            calls.append(view)
        if view.get('source_stage','').startswith('source-reference-law-'):
            scope=view['selected_connection_scope']
            roots={m['source_id'] for m in scope['members']}
            assert roots=={g['anchor']['source_id'] for g in view['groups']}
            for received, canonical in zip(view['groups'], args[1]['groups']):
                for witness, original_witness in zip(received['connections'],canonical['connections']):
                    assert witness['witness']==original_witness['witness']
                    assert witness['witness_document_id']==original_witness['witness_document_id']
                    assert witness['witness_block_id']==original_witness['witness_block_id']
            reference_calls.append(view)
        return body
    monkeypatch.setattr(_Gateway, 'request', capture)
    run(tmp_path, term_glossary, 'chain', False, monkeypatch)
    executed = [step for view in calls for step in view['investigation_chain']['steps']
                if step['action']=='READ_ARTICLES' and step['status']=='APPLIED']
    assert executed and all(step['targets'][0]['location']['source_id'] for step in executed)
    assert len(reference_calls)==2
    assert all(not view['references']['dependency_cards'] for view in calls
        if view['references']['selected_scope_id'] is None)


def test_rendered_scope_completion_agrees_with_historical_delivery(memory, monkeypatch):
    from semantic_runtime.legal_agent.law_navigation import Investigation
    from semantic_runtime.legal_agent import law_candidates
    session, state, wide, page, _ = memory
    state['selected']['B'] = deepcopy(wide)
    state['selected']['B']['offer']['id'] = 'new-scope-same-original'
    state['basis_history']['E']['spans'] = page['spans'][:2]
    group=state['groups']['B']
    group.update(law_id='L', page_plan=[page['spans'][:2], wide['evidence'][0]['spans'][2:]])
    group['hit']['heading']='제1조'
    state['laws']={'L':{'name':'모의법'}}
    actor=S(s=session, p=state, control=True)
    monkeypatch.setattr(law_candidates, 'token', lambda *args:'NEWPAGE')
    rendered=Investigation.render_page(actor, group, 1)
    assert rendered['text']=='ghi' and rendered['selected_scope_complete']


def test_reference_choice_receipt_does_not_claim_target_read_completed():
    from semantic_runtime.legal_agent.law_navigation import Investigation
    state={}; data={'search_queries':[]}
    data['chain_frame_id']=trail.capture(state,'REFERENCE',data)
    actor=S(p=state,s=S(repo=S(event=lambda *args:None)),save=lambda:None)
    Investigation.reference_decision(actor,data,{'decisions':[]})
    step=trail.context(state)['steps'][-1]
    assert step['action']=='REFERENCE_CHOICES' and step['status']=='DECISION_ACCEPTED'

