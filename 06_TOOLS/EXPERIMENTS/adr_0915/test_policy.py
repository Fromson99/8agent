from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import law_candidates as lc, evidence_inventory as inventory
from semantic_runtime.legal_agent.law_navigation import Investigation
from semantic_runtime.legal_agent.errors import ContractError

def test_policy_is_opt_in_and_excludes_workflow(monkeypatch):
    from semantic_runtime.legal_agent import workflow_execution
    profile={'candidate_navigation':{'answer_first':True}}
    monkeypatch.setattr(workflow_execution,'task_context',lambda:None)
    assert lc.answer_first(profile) and not lc.answer_first({})
    monkeypatch.setattr(workflow_execution,'task_context',lambda:{'return_mode':'sources'})
    assert not lc.answer_first(profile)
    with pytest.raises(ContractError):lc.validate_policy({'answer_first':'yes'})
    with pytest.raises(ContractError):lc.validate_policy({'answer_first':True})

def test_acquired_pack_verifies_before_handoff_and_never_claims_delivery(monkeypatch):
    state={'selected':{'g':{'complete':True,'source_id':'s','document_id':'d','evidence':[{'source_id':'s','document_id':'d','evidence_id':'e','spans':[{'text':'source'}]}]}},'groups':{'g':{'status':'READ'}}}
    before=deepcopy(state);verified=[]
    session=S(scope={'d'},source=S(verify=lambda e:verified.append(e['evidence_id'])))
    monkeypatch.setattr(inventory,'_pack',lambda s,p,records,spans:[{'source_id':k,'spans':v} for k,v in spans.items()])
    originals,evidence,omitted=inventory.acquired_originals_for(session,state,100)
    assert verified==['e'] and evidence and not omitted
    assert originals[0]['delivered_context_only'] and state==before
    assert inventory.acquired_originals_for(session,state,1)==([],[],['e'])
    session.scope=set()
    with pytest.raises(ContractError):inventory.acquired_originals_for(session,state,100)
    session.scope={'d'}
    def invalid(e):raise ContractError('hash changed')
    session.source.verify=invalid
    with pytest.raises(ContractError,match='hash'):inventory.acquired_originals_for(session,state,100)

def test_handoff_once_per_material_question_preserves_pending_action_and_state(monkeypatch):
    from semantic_runtime.legal_agent import investigation_diagnostics
    monkeypatch.setattr(investigation_diagnostics,'selection_report',lambda result:{'final_ids':result['final_ids']})
    i=object.__new__(Investigation);i.modern=i.completion=True;i.question='current'
    events=[];i.s=S(profile={'candidate_navigation':{'answer_first':True},'max_read_chars':100},repo=S(event=lambda k,v:events.append((k,v))))
    i.p={'gaps':['unresolved']};i.save=lambda:None
    i.result=lambda decision:{'evidence_sufficient':decision['evidence_sufficient'],'investigation_state':deepcopy(i.p)}
    monkeypatch.setattr(lc,'answer_first',lambda p:True)
    material=[{'source_id':'s','text':'original'}];evidence=[{'evidence_id':'e'}]
    monkeypatch.setattr(inventory,'acquired_originals_for',lambda *a:(deepcopy(material),deepcopy(evidence),[]))
    out=i.assessment_handoff()
    assert out['evidence_sufficient'] is False and out['answer_coverage']=='UNASSESSED'
    assert out['investigation_state']['gaps']==['unresolved'] and 'basis_history' not in i.p
    assert i.assessment_handoff() is None
    material.append({'source_id':'s2','text':'additional'});evidence.append({'evidence_id':'e2'})
    i.p['accepted']={'decision':{}}
    assert i.assessment_handoff() is None
    i.p.pop('accepted')
    assert i.assessment_handoff()['final_ids']==['s','s2']
    assert len(events)==2
    material.reverse();evidence.reverse()
    assert i.assessment_handoff() is None
    i.question='new follow-up'
    assert i.assessment_handoff() is not None
    assert len(events)==3


def test_governing_context_is_atomic_with_subordinate_rule(monkeypatch):
    e=lambda ident,text:{'evidence_id':ident,'source_id':'s','document_id':'d','spans':[{'text':text}]}
    selected={'complete':True,'source_id':'s','document_id':'d','evidence':[e('child','보고한다')]}
    context={**selected,'evidence':[e('parent','승인받은 경우')]}
    state={'selected':{'g':selected},'groups':{'g':{'status':'READ'}},'contexts':{'CONTEXT:p':context}}
    session=S(scope={'d'},source=S(verify=lambda evidence:None))
    monkeypatch.setattr(inventory,'_pack',lambda s,p,records,spans:[{'source_id':k,'spans':v} for k,v in spans.items()])
    original=deepcopy(state)
    sources,evidence,omitted=inventory.acquired_originals_for(session,state,100)
    assert {p['text'] for source in sources for p in source['spans']}=={'보고한다','승인받은 경우'}
    assert {e['evidence_id'] for e in evidence}=={'child','parent'} and not omitted
    assert inventory.acquired_originals_for(session,state,5)==([],[],['child','parent'])
    assert state==original
    context['evidence'][0]['document_id']='another-authorized-doc'
    session.scope.add('another-authorized-doc')
    with pytest.raises(ContractError,match='identity'):inventory.acquired_originals_for(session,state,100)
