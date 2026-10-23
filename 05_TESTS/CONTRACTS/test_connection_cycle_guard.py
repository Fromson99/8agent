from copy import deepcopy
import json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import connection_scope as cs, unit_relations as rel
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_final_connection_selection import setup


def scopes(inv,data):
    rows=cs.candidates(inv,data)
    return [next(s for s,_ in rows if s['structural_selection'].get('unit_id')==u) for u in ('6','9')]

@pytest.mark.parametrize('status',['COMPLETE','PARTIAL','FAILED'])
def test_a_b_a_b_and_resume_never_reopen_same_directory(monkeypatch,status):
    inv,data=setup(monkeypatch);a,b=scopes(inv,data);calls=[]
    def lookup(i,s):
        calls.append(s['id'])
        return dict(status=status,groups=[],connection_count=0,absence_proven=False)
    monkeypatch.setattr(cs,'preview',lookup)
    for s in (a,b):
        cs.reject_repeated_follow(inv,s)
        cs.accept(inv,s,data,'해당 범위의 연결 필요')
        cs.inspect_directory(inv,s)
    for target in (a,b,a,b):
        actions={};cs.offer_choices(inv,data,actions)
        assert not any(x['identity'].get('connection_scope',{}).get('id')==target['id'] for x in actions.values())
        with pytest.raises(ProposalError,match='already inspected'):cs.reject_repeated_follow(inv,target)
        assert not data['connection_review']['required_before_finish']
        assert all(not h['repeat_available'] for h in data['connection_action_history'])
        inv.p=json.loads(json.dumps(inv.p))  # persisted checkpoint roundtrip
        assert cs.inspect_directory(inv,target)['status']==status
    assert calls==[a['id'],b['id']]
    assert {h['scope_id'] for h in data['connection_action_history']} >= {a['id'],b['id']}


def test_new_scope_bytes_allow_lookup_but_equivalent_ui_scope_does_not(monkeypatch):
    inv,data=setup(monkeypatch);a,b=scopes(inv,data)
    monkeypatch.setattr(cs,'preview',lambda *a:dict(status='COMPLETE',groups=[],connection_count=0))
    cs.accept(inv,a,data,'읽음');cs.inspect_directory(inv,a)
    alias=deepcopy(a);alias['label']='다른 화면의 동일 원문';alias['id']=digest({k:v for k,v in alias.items() if k!='id'})
    with pytest.raises(ProposalError):cs.reject_repeated_follow(inv,alias)
    expanded=deepcopy(a);expanded['members'][0]['spans']+=b['members'][0]['spans'];expanded['id']=digest({k:v for k,v in expanded.items() if k!='id'})
    cs.reject_repeated_follow(inv,expanded)
    assert cs.directory_receipt(inv,expanded) is None


@pytest.mark.parametrize('change',['hash','binding','acl','source'])
def test_receipt_mutation_never_authorizes_cached_directory(monkeypatch,change):
    inv,data=setup(monkeypatch);a,_=scopes(inv,data)
    monkeypatch.setattr(cs,'preview',lambda *a:dict(status='COMPLETE',groups=[],connection_count=0))
    cs.accept(inv,a,data,'확인');cs.inspect_directory(inv,a)
    if change=='hash':inv.p['connection_directories'][cs.directory_key(a)]['result']['connection_count']=99
    if change=='binding':inv.p['binding']['generation']='other'
    if change=='acl':inv.s.scope=[]
    if change=='source':inv.s.tools.sources[a['members'][0]['source_id']]['document_id']='other'
    with pytest.raises(ContractError):cs.inspect_directory(inv,a)


def test_cached_directory_updates_acquisition_without_another_query(monkeypatch):
    inv,data=setup(monkeypatch);a,_=scopes(inv,data);inv.read_records=lambda:{}
    group={'anchor':{'source_id':'article92','document_id':'d'},'target':{'source_id':'article97','document_id':'d'},
        'connections':[{'endpoint_block_ids':['10'],'already_read':False}]}
    calls=[]
    monkeypatch.setattr(cs,'preview',lambda *args:(calls.append(1) or dict(status='COMPLETE',groups=[group],connection_count=1)))
    known={};monkeypatch.setattr(rel,'acquired_blocks',lambda *a:(known,{}))
    cs.accept(inv,a,data,'선택');assert not cs.inspect_directory(inv,a)['groups'][0]['connections'][0]['already_read']
    before=deepcopy(inv.p['connection_directories']);known['article97']={'10'}
    assert cs.inspect_directory(inv,a)['groups'][0]['connections'][0]['already_read']
    assert len(calls)==1 and before==inv.p['connection_directories']


def test_execution_boundary_rejects_repeated_scope_even_with_injected_menu(monkeypatch):
    from semantic_runtime.legal_agent import law_navigation as nav, tool_availability as availability
    inv,data=setup(monkeypatch);a,_=scopes(inv,data)
    monkeypatch.setattr(cs,'preview',lambda *a:dict(status='COMPLETE',groups=[],connection_count=0))
    cs.accept(inv,a,data,'최초 조회');cs.inspect_directory(inv,a)
    inv.completion=False;inv.control=False;inv.policy['structure_first']=False
    inv.p['catalogue']={'query_fingerprint':'q'}
    monkeypatch.setattr(availability,'require_navigation',lambda *a:None)
    action={'id':'OLD','action':'FOLLOW_CONNECTION','identity':{'connection_scope':a}}
    decision={'next_action':'FOLLOW_CONNECTION','targets':['OLD'],'law_decisions':[],
        'branch_decisions':[],'notes':'','reason':'이미 본 범위 재조회'}
    before=deepcopy(inv.p['connection_directories'])
    with pytest.raises(ProposalError,match='already inspected'):
        nav.Investigation.execute_tool(inv,decision,{'sources':[]},{'OLD':action})
    assert inv.p['connection_directories']==before


def test_accepted_action_restore_preserves_completed_directory_and_counters(monkeypatch):
    from semantic_runtime.legal_agent import law_navigation as nav, comparison_research, source_investigation, definition_entry
    from semantic_runtime.basis_links import resolver
    inv,data=setup(monkeypatch);a,_=scopes(inv,data);calls=[]
    monkeypatch.setattr(cs,'preview',lambda *a:(calls.append(1) or dict(status='COMPLETE',groups=[],connection_count=0)))
    cs.accept(inv,a,data,'최초 확인');cs.inspect_directory(inv,a)
    saved=deepcopy(inv.p['connection_directories'])
    inv.p.update(decisions=[],turn=0,no_progress=2)
    before=deepcopy(inv.p);before.pop('connection_directories');before['no_progress']=0
    decision={'next_action':'FINISH'}
    inv.p['accepted']={'before':before,'decision':decision,'data':data,'actions':{},'phase':'resume','input_hash':digest(data)}
    inv.control=False;inv.completion=False;inv.left=lambda:100;inv.assessment_handoff=lambda:None
    inv.result=lambda d:{'finished':True};inv.question='모의 질문'
    for module,name in ((resolver,'acquire'),(comparison_research,'acquire'),(source_investigation,'acquire_preferred'),(definition_entry,'acquire_initial')):
        monkeypatch.setattr(module,name,lambda *a:None)
    def execute(*args):
        assert inv.p['connection_directories']==saved and inv.p['no_progress']==2
        assert cs.inspect_directory(inv,a)['status']=='COMPLETE'
        return True
    inv.execute=execute
    assert nav.Investigation.run(inv)=={'finished':True}
    assert len(calls)==1 and inv.p['turn']==1
