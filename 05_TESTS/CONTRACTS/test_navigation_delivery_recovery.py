"""Synthetic completion transitions and real journal/API delivery boundaries."""
from copy import deepcopy
import json
import sqlite3
import uuid
import pytest
from jsonschema import ValidationError
from test_focused_input_modality import tree, session, focused, purpose, FocusedTransport
from test_investigation_completion_adr0678 import decision, apply
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_source_span_norm import SpanTransport
from semantic_runtime.legal_agent import law_navigation as ln, evidence_inventory as inventory
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from semantic_runtime.legal_agent.output_contract import diagnostics


def ready(session, version=cc.V8):
    inv = focused(session[0]);inv.s.profile['candidate_navigation']['completion_policy_version'] = version
    data, actions = inv.view()
    target = next(a['id'] for a in actions.values() if a['action']=='READ_ARTICLES')
    value = decision(data, 'READ_ARTICLES', target)
    if data.get('investigation_scope'):value['exploration'] = [purpose(data,target)]
    apply(inv,value,data,actions)
    return inv, *inv.view()


def conflict(data):
    value = decision(data,'FINISH')
    for row in value['branch_decisions']:
        row.update(status='DEFER',reason='근거가 부족하여 채택 보류')
    value.update(evidence_sufficient=False,sufficiency_reason='관련 원문 부족')
    return value


@pytest.mark.parametrize('version',[cc.V2,cc.V5,cc.V6,cc.V7,cc.V8])
@pytest.mark.parametrize('prior',[False,True])
@pytest.mark.parametrize('status',['OMIT','ADOPT','KEEP','DEFER','EXCLUDE'])
@pytest.mark.parametrize('other',[False,True])
def test_completion_transition_matrix(session,version,prior,status,other):
    inv,data,actions=ready(session,version)
    gid=data['sources'][0]['branch_id'];ref=data['sources'][0]['id']
    inv.p['issues'].append({**inv.p['issues'][0],'id':'Q2','question':'별도 쟁점'})
    if prior:
        d=decision(data,'FINISH');d['next_action']='DECIDE';apply(inv,d,data,actions)
    data,actions=inv.view();inv.p['coverage_warning']=data['presentation_id']
    v=decision(data,'FINISH');v.update(evidence_sufficient=False,basis_refs=[ref])
    v['branch_decisions']=[] if status=='OMIT' else [{'branch_id':gid,'status':status,'reason':'모의 판단',
        'issue_refs':['Q2' if other else 'Q1'],'basis_refs':[ref]}]
    allowed=status=='OMIT' or status in next(b['allowed_decisions'] for b in data['branches'] if b['id']==gid)
    # Independent oracle: accepted adoption in Q1 survives updates to Q2.
    active=(prior if status=='OMIT' else status in ('ADOPT','KEEP') or (prior and other))
    expected=allowed and active
    before=deepcopy(inv.p['groups'][gid])
    if not expected:
        with pytest.raises((ProposalError,ValidationError)):inv.validate(v,data,actions)
        assert inv.p['groups'][gid]==before
    else:
        inv.validate(v,data,actions);inv.execute_tool(v,data,actions)
        assert inv.p['groups'][gid]['status']=='ACTIVE'
        assert inventory.originals_for(inv.s,inv.p)


def test_typed_conflict_and_specific_correction_keep_choices(session):
    inv,data,actions=ready(session)
    bad=conflict(data)
    with pytest.raises(ProposalError) as exc:inv.validate(bad,data,actions)
    _,instructions=ln.repair_contract(data,actions,inv.p['groups'],bad,exc.value)
    assert diagnostics(exc.value)['issues'][0]['code']=='FINISH_WITHOUT_ADOPTED_SOURCE'
    assert instructions['conflicts'][0]['code']=='FINISH_WITHOUT_ADOPTED_SOURCE'
    assert 'PENDING' in str(instructions['conflicts']) and 'completion_rule' in data
    inv.validate(decision(data,'PENDING'),data,actions)
    inv.validate(decision(data,'FINISH'),data,actions)


def delivery(inv,data,phase='source-law-navigation-2'):
    repo=inv.s.repo
    view=repo.save_view('investigate',{**data,'source_stage':phase},[])
    request={'messages':[{'role':'system','content':'synthetic'}, {'role':'user','content':json.dumps({'view':view})}]}
    attempt=repo.reserve_attempt(view,request,uuid.uuid4().hex,1,'investigate');repo.attempt_sent(attempt)
    repo.finish_attempt(attempt,'SUCCEEDED',wire({}),{'model':'scripted','usage':{}})
    inventory.record_delivery(repo,view,attempt)
    return view,attempt


def test_receipt_is_separate_idempotent_and_resume_preserves_budget(session):
    inv,data,_=ready(session);view,attempt=delivery(inv,data)
    before=inv.s.repo.budget();state=deepcopy(inv.p)
    assert inventory.reconcile_delivery(inv.s,state,data,'source-law-navigation-2')
    assert not inventory.reconcile_delivery(inv.s,state,data,'source-law-navigation-2')
    assert inv.s.repo.budget()==before and not state['basis_history']
    assert not inventory.originals_for(inv.s,state)
    assert inventory.delivered_originals_for(inv.s,state)
    assert all(not b['accepted'] for b in state['delivery_history'].values())
    inv.p=state;inv.save()
    inv.invoke=lambda *args:conflict(args[1])
    result=inv.run();again=inv.run()
    assert result['adoption_fallback'] and again['adoption_fallback']
    assert inv.s.repo.budget()==before


@pytest.mark.parametrize('mutation',['sources','state','scope','bytes','view','event','attempt'])
def test_receipt_cannot_cross_identity_or_bytes(session,mutation):
    from semantic_runtime.legal_agent.repository import encoded
    inv,data,_=ready(session);view,attempt=delivery(inv,data);db=inv.s.repo.db
    if mutation=='sources':data['sources'][0]['text']+='변조'
    if mutation=='state':inv.p['state_version']+=1
    if mutation=='scope':inv.s.scope=[]
    if mutation=='bytes':
        data['sources'][0]['spans'][0]['text']='변조'
    if mutation in ('view','event'):
        with pytest.raises(sqlite3.IntegrityError,match='immutable'):
            if mutation=='view':db.execute('UPDATE model_view SET body_json=? WHERE view_id=?',(encoded({}),view['view_id']))
            else:db.execute("UPDATE event SET payload_hash=? WHERE kind='NAVIGATION_INPUT_DELIVERED'",('0'*64,))
        assert not inv.p.get('delivery_history')
        return
    if mutation=='attempt':db.execute("UPDATE model_attempt SET status='UNKNOWN' WHERE attempt_id=?",(attempt,))
    with pytest.raises(ContractError):inventory.reconcile_delivery(inv.s,inv.p,data,'source-law-navigation-2')
    assert not inv.p.get('delivery_history')


@pytest.mark.parametrize('status',['DEFER','EXCLUDE'])
def test_accepted_rejection_never_becomes_fallback(session,status):
    inv,data,actions=ready(session);delivery(inv,data)
    inventory.reconcile_delivery(inv.s,inv.p,data,'source-law-navigation-2')
    v=conflict(data);v['next_action']='DECIDE'
    for row in v['branch_decisions']:row['status']=status
    apply(inv,v,data,actions)
    assert inv.p['delivery_history'] and not inventory.delivered_originals_for(inv.s,inv.p)


def test_terminal_transport_requires_new_epoch_and_retains_budget(session):
    from semantic_runtime.legal_agent.errors import TransportError
    from semantic_runtime.legal_agent import request_repair as rr
    inv,data,actions=ready(session);calls=[];budget=inv.s.repo.budget()
    def fail(*args):calls.append(args[3]);raise TransportError('unknown synthetic delivery',unknown=True)
    inv.invoke=fail
    for _ in range(2):
        with pytest.raises(TransportError):inv.request_decision(data,actions,'source-law-navigation-2')
    assert len(calls)==1 and inv.s.repo.budget()==budget and inv.p['decision_stop']['unknown']
    inv.p=rr.new_epoch(inv.p,reason='ASSESS_GAP_REENTRY')
    with pytest.raises(TransportError):inv.request_decision(data,actions,'source-law-navigation-2')
    assert len(calls)==2 and inv.s.repo.budget()==budget


class RecoveryTransport(SpanTransport):
    def __init__(self,mode):super().__init__(False,False);self.mode=mode;self.conflicts=[];self.assessments=[]
    def send_once(self,*,body,ticket):
        from semantic_runtime.legal_agent.navigation_input import expand_cards
        v=expand_cards(json.loads(body['messages'][1]['content'])['view']);phase=v.get('source_stage',v['phase'])
        if phase.startswith('memory-assess'):self.assessments.append(v)
        if phase.startswith('source-law-navigation-') and v['sources']:
            self.phases.append(phase);self.conflicts.append(phase)
            value=decision(v,'FINISH') if self.mode=='repaired' and phase.endswith('-repair') else conflict(v)
            response=wire(value);response['body_json']['choices'][0]['finish_reason']='stop'
            if self.mode=='malformed':response['body_json']['choices'][0]['message']['content']='{invalid'
            if self.mode in ('length','content_filter'):response['body_json']['choices'][0]['finish_reason']=self.mode
            if self.mode=='model_mismatch':response['body_json']['model']='wrong-model'
            if self.mode=='unknown':
                from semantic_runtime.legal_agent.errors import TransportError
                raise TransportError('unknown outcome',unknown=True)
            return response
        return super().send_once(body=body,ticket=ticket)


@pytest.mark.parametrize('mode',['repaired','repeated','malformed','length','content_filter','model_mismatch','unknown'])
def test_native_v8_api_delivery_failure_and_publication(tmp_path,tree,mode):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    gen,idx=tree;t=RecoveryTransport(mode)
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
            'completion_policy_version':cc.V8,'compact_input':True,'length_recovery_max_tokens':12800}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=t,runtime_root=tmp_path/'runtime',
        memory_identity=lambda _:{'user_id':'synthetic','team_id':'synthetic','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        body={'question':'모의승인규정 제1조 승인 기준은?','session_id':mode,'request_id':'r1'}
        response=api.post('/v1/rag/ask',json=body);count=len(t.phases);navigation_count=len(t.conflicts)
        if mode in ('repaired','repeated','malformed'):assert response.status_code==200,response.text
        again=api.post('/v1/rag/ask',json=body)
        assert len(t.conflicts)==navigation_count
        if mode in ('repaired','repeated','malformed'):assert len(t.phases)==count
    receipts=0
    for path in (tmp_path/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'):
        with sqlite3.connect(path) as db:
            receipts+=db.execute("SELECT count(*) FROM event WHERE kind='NAVIGATION_INPUT_DELIVERED'").fetchone()[0]
    assert len(t.conflicts)<=2
    if mode in ('repaired','repeated','malformed'):
        assert response.status_code==200,response.text
        assert again.json()['answer']==response.json()['answer']
        assert again.json()['assembly']==response.json()['assembly']
        assert again.json()['execution_stats']['llm_calls']==0
        assert any(p=='memory-assess' for p in t.phases) and receipts==2
        assert '승인 후 보고한다.' in response.json()['answer']['text']
        if mode!='repaired':
            assert t.assessments[0]['adoption_fallback']
            assert all(r['status']!='ACTIVE' for r in t.assessments[0]['saved_inventory'])
    else:
        assert response.status_code!=200 and receipts==0
        assert not any(p=='memory-assess' for p in t.phases)
