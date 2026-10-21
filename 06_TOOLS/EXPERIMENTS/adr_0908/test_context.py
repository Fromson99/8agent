from copy import deepcopy
import json
import pytest
from test_reference_decision_continuity import connected,start,overview
from test_read_choice_input_preservation import unit,wire
from semantic_runtime.legal_agent import decision_projection as dp


def test_completed_reference_survives_focus_change_and_actual_wire(connected,monkeypatch):
    real,menus=start(connected[0]);expected=dp.previous_reference_decisions(real)
    assert len(expected['items'])==1 and expected['items'][0]['decision']['action']=='SKIP'
    real.p['window_groups']=[];assert dp.previous_reference_decisions(real)==expected
    fake,data,actions,payloads,_=unit.fixture(monkeypatch,unit.choice(queries=['다른 조문']))
    fake.p=deepcopy(real.p);fake.question=real.question;fake.s.scope=real.s.scope;fake.s.context=real.s.context;fake.read_records=real.read_records
    before=deepcopy(fake.p['action_chain'])
    dp.choose_read(fake,data,actions,'reference-history-wire')
    assert wire(payloads[0])['previous_reference_decisions']==expected
    assert fake.p['action_chain']==before
    assert expected['items'][0]['decision']['reason']==menus[0]['investigation_chain'].get('unused','이번 질문의 조사 범위에 따른 선택')


@pytest.mark.parametrize('defect',['defer','foreign_generation','foreign_scope','incomplete_follow','failed_step','missing_frame','conflicting_receipts','bad_reason'])
def test_history_cannot_promote_unbound_or_incomplete_opinions(connected,defect):
    real,_=start(connected[0]);state=real.p['reference_state'];key=next(iter(state['decisions']));d=state['decisions'][key]
    if defect=='defer':d.update(action='DEFER',applicability='UNDETERMINED')
    elif defect=='foreign_generation':real.s.context.query['generation_id']='different'
    elif defect=='foreign_scope':real.s.scope=['d']
    elif defect=='incomplete_follow':d.update(action='FOLLOW',applicability='APPLIES',scopes=['subtree:1'])
    elif defect=='failed_step':
        for step in real.p['action_chain']['steps']:
            if step.get('reference_decisions'):step['status']='INTERRUPTED'
    elif defect=='missing_frame':real.p['action_chain']['frames'].clear()
    elif defect=='conflicting_receipts':
        other=deepcopy(state);other['decisions'][key]['reason']='다른 의견';real.p['reference_states']['other']=other
    else:d.pop('reason')
    assert dp.previous_reference_decisions(real)['items']==[]


@pytest.mark.parametrize('bounds',[{'limit':0},{'max_chars':1}])
def test_history_budget_omits_whole_entries_and_keeps_durable_state(connected,bounds):
    real,_=start(connected[0]);before=deepcopy(real.p)
    out=dp.previous_reference_decisions(real,**bounds)
    assert out['items']==[] and out['omitted']==1 and real.p==before


def test_history_deduplicates_identical_decision_steps(connected):
    real,_=start(connected[0]);steps=real.p['action_chain']['steps'];step=next(s for s in steps if s['reference_decisions']);steps.extend(deepcopy(step) for _ in range(20))
    out=dp.previous_reference_decisions(real)
    assert len(out['items'])==1 and out['omitted']==0


def test_follow_option_names_current_anchor_and_keeps_target(connected):
    real,_=start(connected[0]);data,actions=real.view();refs=data['references'];assert refs['current_anchors']
    a=next(a for a in actions.values() if a['action']=='FOLLOW_CONNECTION')
    before=deepcopy(a);row=dp.navigation_option('FOLLOW_CONNECTION',a['id'],a,data)
    assert row['reference_anchors']==refs['current_anchors']
    assert row['target']==a['id'] and a==before
    for source in refs['current_anchors']:
        assert source['document_name'] in row['label'] and source['heading'] in row['label']
