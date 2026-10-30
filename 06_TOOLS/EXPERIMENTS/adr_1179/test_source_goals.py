from copy import deepcopy
from types import SimpleNamespace as NS
import json,pytest
from jsonschema import validate
from test_supervisor import fixture
from semantic_runtime.legal_agent import source_goal_control as sg,investigation_supervisor as su
from semantic_runtime.legal_agent.answer_progress import ProgressHandoff
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from lawrag.core.legal_coordinate import find_coordinates

def setup():
 inv,d,v,p,s,x=fixture();inv.policy.update(source_goal_control=True)
 inv.s.scope={'wanted','other'}
 inv.s.matcher=NS(sources={'wanted-source':{'document_id':'wanted','unit_id':'13'}},units={('wanted','13'):{'coordinate_scope':'body'},('other','15'):{'coordinate_scope':'body'}},stored_coordinates={('wanted','13'):find_coordinates('제13조')[0].coordinate,('other','15'):find_coordinates('제15조')[0].coordinate})
 d['laws']=[{'document_id':'wanted','name':'대상규정'},{'document_id':'other','name':'다른규정'}]
 a={'L':{'action':'SEARCH_STRUCTURE','identity':{'document_id':'wanted'}},'WRONG':{'action':'READ_ARTICLES','identity':{'document_id':'other','unit_id':'15'}},'READ':{'action':'READ_ARTICLES','identity':{'source_id':'wanted-source','document_id':'wanted','unit_id':'13'}}}
 v.update(source_targets=[{'lookup_target':'L','coordinate':'제13조','coordinate_scope':'body','issue_id':'Q1','reason':'필수 기준 확인'}],source_goal_exclusions=[])
 decision={'next_action':'READ_ARTICLES','targets':['WRONG'],'issue_refs':['Q1']}
 def expand(value):
  sg.validate(value,inv,d,a)
  if value['choice']=='READ':return {'next_action':'READ_ARTICLES','targets':[r['target'] for r in value['selections']],'issue_refs':['Q1']}
  return {'next_action':'SEARCH_STRUCTURE','targets':[value['target']],'structure_filter':value['structure_filter'],'queries':[],'issue_refs':['Q1']}
 return inv,d,v,p,a,decision,expand

def run(items):
 inv,d,v,p,a,de,x=items
 return sg.resolve(inv,d,a,p,v,de,x,su.state_for(inv,d))

def test_wrong_document_replaced_by_exact_read_without_model():
 z=setup();inv,d,v,p,a,de,x=z
 out=run(z);assert out['targets']==['READ']
 st=su.state_for(inv,d);assert st['calls']==0 and st['source_goals'][0]['status']=='REQUIRED'
 su.before_execute(inv,d,out)
 with pytest.raises(ContractError):su.before_execute(inv,d,de)
 assert inv.s.repo.events[-1][0]=='SOURCE_GOAL_DISPATCH'

def test_exact_lookup_preserves_scope_then_read_then_acquired():
 z=setup();inv,d,v,p,a,de,x=z;read=a.pop('READ')
 out=run(z);assert out['next_action']=='SEARCH_STRUCTURE' and out['structure_filter']=={'coordinate':'제13조','title':'','coordinate_scope':'body'}
 sg.after_execute(inv,d,out,True)
 assert su.state_for(inv,d)['source_goals'][0]['status']=='REQUIRED'
 d['presentation_id']='p2';a['READ']=read;v['source_targets']=[]
 out=run(z);acquire(inv,d,a)
 sg.after_execute(inv,d,out,True);st=su.state_for(inv,d)
 assert st['source_goals'][0]['status']=='ACQUIRED'
 sg.after_execute(inv,d,out,True)
 assert len([e for e in inv.s.repo.events if e[0]=='SOURCE_GOAL_RESULT'])==2

def test_success_without_original_receipt_fails_closed():
 z=setup();out=run(z)
 with pytest.raises(ContractError):sg.after_execute(z[0],z[1],out,True)

@pytest.mark.parametrize('coordinate',['제13조 및 제14조','알 수 없음','제13조쯤'])
def test_ambiguous_coordinate_not_guessed(coordinate):
 z=setup();z[2]['source_targets'][0]['coordinate']=coordinate
 with pytest.raises(ProposalError):run(z)

@pytest.mark.parametrize('scope',['appendix','addendum'])
def test_same_article_number_other_scope_not_read(scope):
 z=setup();z[2]['source_targets'][0]['coordinate_scope']=scope
 out=run(z);assert out['next_action']=='SEARCH_STRUCTURE' and out['structure_filter']['coordinate_scope']==scope

@pytest.mark.parametrize('bad',['unknown_handle','unauthorized'])
def test_acl_and_offered_target(bad):
 z=setup()
 if bad=='unknown_handle':z[2]['source_targets'][0]['lookup_target']='unknown'
 else:z[0].s.scope={'other'}
 with pytest.raises(ContractError):run(z)

def test_resume_reuses_exact_dispatch_no_duplicate_route():
 z=setup();out=run(z);z[0].p=json.loads(json.dumps(z[0].p))
 assert run(z)==out
 assert su.state_for(z[0],z[1])['source_goals'][0]['routes']==['READ']

def test_unrelated_bridge_keeps_goal_and_is_bounded():
 z=setup();inv,d,v,p,a,de,x=z;a.pop('READ');out=run(z);sg.after_execute(inv,d,out,True)
 for number in range(2):
  d['presentation_id']='bridge'+str(number);de['targets']=['WRONG'+str(number)];v['source_targets']=[]
  assert run(z)==de
  assert su.state_for(inv,d)['source_goals'][0]['status']=='REQUIRED'
 d['presentation_id']='last';de['targets']=['WRONG3']
 with pytest.raises(ProgressHandoff):run(z)

def test_finish_cannot_erase_unread_goal():
 z=setup();inv,d,v,p,a,de,x=z;a.pop('READ');out=run(z);sg.after_execute(inv,d,out,True)
 d['presentation_id']='p2';v['source_targets']=[];de.update(next_action='FINISH',targets=[])
 with pytest.raises(ProgressHandoff):run(z)
 assert su.state_for(inv,d)['source_goals'][0]['status']=='REQUIRED'

def test_grounded_exclusion_retained_and_not_automatic():
 z=setup();run(z);inv,d,v,p,a,de,x=z;d['presentation_id']='p2';v['source_targets']=[]
 v['source_goal_exclusions']=[{'goal_id':'SG1','reason':'원문에 명시된 적용 대상과 달라 제외','basis_refs':['E1']}]
 assert run(z) is None
 st=su.state_for(inv,d);assert st['source_goals'][0]['status']=='EXCLUDED' and st['source_goals'][0]['exclusion']==v['source_goal_exclusions'][0]

@pytest.mark.parametrize('refs',[[],['preview']])
def test_unfounded_exclusion_rejected(refs):
 z=setup();run(z);z[1]['presentation_id']='p2';z[2]['source_targets']=[]
 z[2]['source_goal_exclusions']=[{'goal_id':'SG1','reason':'제외','basis_refs':refs}]
 with pytest.raises(ProposalError):run(z)

def test_time_reserve_retains_target_without_execution():
 z=setup();z[0].left=lambda:30
 with pytest.raises(ProgressHandoff):run(z)
 assert not any(e[0]=='SOURCE_GOAL_DISPATCH' for e in z[0].s.repo.events)

def test_limited_final_preserves_claims_and_missing_target():
 z=setup();run(z);goals=sg.unresolved(z[0].p,z[1]['issues'])
 r={'disposition':'ANSWER','answer_coverage':'COVERED','claims':[{'text':'확인한 주장'}],'limitation_items':[]}
 sg.limit_assessment(r,goals)
 assert r['claims']==[{'text':'확인한 주장'}] and r['answer_coverage']=='PARTIAL' and '대상규정 제13조' in r['limitations'][0]

def test_off_mode_keeps_existing_choice_and_state():
 z=setup();z[0].policy['source_goal_control']=False
 assert run(z) is None and not su.state_for(z[0],z[1]).get('source_goals')

def test_assessment_exact_gap_seeds_goal_and_uses_global_lookup(monkeypatch):
 from semantic_runtime.legal_agent import answer_progress as ap
 z=setup();inv,d,v,p,a,de,x=z;a.pop('L');a.pop('READ');a['GLOBAL']={'action':'SEARCH_STRUCTURE','identity':{'document_id':None}};v['source_targets']=[]
 d['assessment_gaps']=[{'gap_id':'G1','issue_id':'Q1','reason':'확정된 원문 부족','target_binding':{'status':'EXACT','pairs':[{'document_id':'wanted','unit_id':'13','coordinate':'제13조','document_name':'대상규정'}]}}]
 monkeypatch.setattr(ap,'assessment_requirements',lambda *args:[{'gap_id':'G1'}])
 def expand(value):return {'next_action':'SEARCH_STRUCTURE','targets':[value['target']],'queries':value['queries'],'issue_refs':['Q1']}
 out=sg.resolve(inv,d,a,p,v,de,expand,su.state_for(inv,d))
 assert out['queries']==['대상규정 제13조']
 assert su.state_for(inv,d)['source_goals'][0]['origin_gap_id']=='G1'

def test_already_acquired_exact_original_never_reread():
 z=setup();inv,d,v,p,a,de,x=z
 sg.record(v,inv,d,a,su.state_for(inv,d));acquire(inv,d,a)
 assert run(z) is None and su.state_for(inv,d)['source_goals'][0]['status']=='ACQUIRED'

def test_judgment_display_stable_and_does_not_mutate_committed_payload():
 from test_genos_judgment_view import sample
 from semantic_runtime.legal_agent import judgment_view as view,read_judgment as rj
 from semantic_runtime.contracts import digest
 parts,case,state=sample();select=parts['SELECT']['payload']
 head={'document_id':'d','source_id':'s1','use':'CORE','finding':'판단','reason':'원문 확인','version':1}
 ledger={'version':rj.VERSION,'heads':{'Z':{**head,'id':'Z'},'A':{**head,'id':'A'}},'needs':{'n':{'status':'OPEN','text':'범위','reason':'미확인'}},'conflicts':{}}
 ledger['state_hash']=rj.seal(ledger)
 select.update(investigation_state={'read_judgments':{'key':ledger}},law_navigation={'laws':[],'branches':[]},completion_limitations=['기존 한계'],control_contract='test',investigation_chain={'steps':[{'structure_lookup':{'lookup_status':'MATCH','failure':None}},{'structure_lookup':{'lookup_status':'FAILED','failure':{'traceback':'private diagnostic'}}}]},return_points=[],saved_inventory={},evidence_inventory={})
 for name,row in parts.items():case['judgment_refs'][name]['payload_hash']=digest(row['payload'])
 before=deepcopy(parts)
 a=view.build(parts,case,state=state,run_id='r1',allowed_documents=['d'])
 b=view.build(json.loads(json.dumps(parts,sort_keys=True)),case,state=state,run_id='r1',allowed_documents=['d'])
 assert a==b and parts==before
 from semantic_runtime.chat_adapter import views
 assert views().public_response(a)==a
 assert a['content_sha256']==digest({k:v for k,v in a.items() if k!='content_sha256'})

@pytest.mark.parametrize('damage',[None,'hash','path','fallback','authorization','main','judge','model'])
def test_scoped_proxy_comparison_validator(tmp_path,damage):
 import sys
 from pathlib import Path
 root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'06_TOOLS/COMMANDS'))
 import adr_structure as ac
 adr=tmp_path/'ADR-9999-test';(adr/'artifacts').mkdir(parents=True)
 auth={'source':'user_message','text':'비교 실험','scope':'이번 실험','session_id':'task','fallback_allowed':False}
 cfg={'schema_version':'qwen38-proxy-comparison-v1','adr_id':'ADR-9999','experiment_id':'test','models':['qwen/qwen3.5-122b-a10b'],'proxy_policy':deepcopy(ac.GENOS_PROXY_POLICY),'authorization':auth,'fallback_allowed':False,'main_wiring':'unchanged'}
 m={'adr_id':'ADR-9999','experiment_id':'test','in_sample':True,'decision_eligible':False,'llm_policy':{'llm_calls':[{'model':cfg['models'][0],'class':'product'}]}};meta={'main_wiring':'unchanged'}
 if damage=='fallback':cfg['fallback_allowed']=True
 if damage=='authorization':cfg['authorization']['text']=''
 if damage=='main':meta['main_wiring']='promotion-candidate'
 if damage=='judge':m['llm_policy']['llm_calls'][0]['class']='offline_evaluator'
 if damage=='model':cfg['models']=['unapproved/model']
 path=adr/'artifacts/design.json';path.write_text(json.dumps(cfg));m['llm_policy']['proxy_comparison']={'path':str(path),'sha256':ac._sha256(path)}
 if damage=='hash':m['llm_policy']['proxy_comparison']['sha256']='bad'
 if damage=='path':m['llm_policy']['proxy_comparison']['path']=str(tmp_path/'outside.json')
 models,errors=ac._qwen38_proxy_comparison(adr,m,meta)
 assert bool(errors)==(damage is not None)
 assert models==({'qwen/qwen3.5-122b-a10b'} if damage is None else set())


def acquire(inv,data,actions):
    st=su.state_for(inv,data)
    for goal in st['source_goals']:goal['expected']=[{'document_id':'wanted','block_id':'b','start_cp':0,'end_cp':4}]
    su.save(inv,st)
    evidence={'source_id':'wanted-source','document_id':'wanted','spans':[{'block_id':'b','start_cp':0,'end_cp':4,'text':'실제원문'}]}
    def verify(e):assert e==evidence
    inv.s.source=NS(verify=verify)
    inv.p.update(read_plans={'plan':{'status':'ACQUIRED','targets':[actions['READ']['identity']],'completed':{'READ':'g1'}}},
        selected={'g1':{'source_id':'wanted-source','document_id':'wanted','offer':{'unit_id':'13','block_ids':['b']},'evidence':[evidence]}})


def test_partial_receipt_cannot_mark_goal_acquired():
    z=setup();out=run(z);inv,d,v,p,a,de,x=z;acquire(inv,d,a)
    inv.p['selected']['g1']['evidence'][0]['spans'][0].update(end_cp=2,text='실제')
    sg.after_execute(inv,d,out,True)
    assert su.state_for(inv,d)['source_goals'][0]['status']=='BLOCKED'


def test_other_batch_target_receipt_cannot_mark_goal_acquired():
    z=setup();out=run(z);inv,d,v,p,a,de,x=z;acquire(inv,d,a)
    inv.p['selected']['g1']['document_id']='other'
    sg.after_execute(inv,d,out,True)
    assert su.state_for(inv,d)['source_goals'][0]['status']=='BLOCKED'


def test_document_goal_contract_roundtrip_and_no_tool_number():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    inv,d,v,p,a,de,x=setup();schema=sg.fields(inv,d,a)
    assert 'document_ref' in schema['source_targets']['items']['properties']
    assert 'lookup_target' not in schema['source_targets']['items']['properties']
    rows=sg.public_options(d,a);assert rows==[{'document_ref':'wanted','name':'대상규정'}]
    r=NavigationReferences({});r.document_forward={'wanted':'D1'};r.document_reverse={'D1':'wanted'}
    value={'source_targets':[{'document_ref':'wanted','coordinate':'제13조'}]}
    assert r.restore(r.view(value))==value
    assert r.schema(schema)['source_targets']['items']['properties']['document_ref']['enum']==['D1']

@pytest.mark.parametrize('damage',[None,'no_reference','excluded','generation','target','unauthorized','cross_source'])
def test_required_target_scope_is_bounded(monkeypatch,damage):
 from semantic_runtime.legal_agent import query_scope as qs,request_repair as rr
 from semantic_runtime.contracts import digest
 gap={'gap_id':'G','material':True,'kind':'MISSING_SOURCE','target_binding_hash':'v1','target_binding':{'status':'EXACT','source_ids':['s'],'pairs':[{'document_id':'d','unit_id':'1'}]}}
 scope={'hash':'h','targets':[{'document_id':'origin','unit_id':None}],'selections':[]}
 session=NS(scope={'d','origin'},direct_search_scope=scope,tools=NS(sources={'s':{'document_id':'d','blocks':[{'block_id':'1'},{'block_id':'2'}]}}),matcher=NS(),scope_read_grants={'s':{'2':{'reference_id':'R'}}},repo=NS(event=lambda *x:None))
 monkeypatch.setattr(rr,'bind_gap',lambda *a:{**deepcopy(gap),'target_binding_hash':'changed' if damage=='generation' else 'v1','target_binding':{'status':'AMBIGUOUS'} if damage=='target' else gap['target_binding']})
 monkeypatch.setattr(sg,'pair_expected',lambda *a:[{'block_id':'1'},{'block_id':'2'}])
 if damage=='no_reference':session.scope_read_grants={}
 if damage=='cross_source':session.tools.sources['s']['blocks']=[{'block_id':'2'}]
 if damage=='excluded':monkeypatch.setattr(qs,'check_selection_exclusions',lambda *a:(_ for _ in ()).throw(qs.UnresolvedScope('excluded')))
 if damage=='unauthorized':session.scope.remove('d')
 if damage in ('generation','target','unauthorized'):
  with pytest.raises(ContractError):sg.grant_required_targets(session,{'assessment_gaps':[gap]})
  return
 sg.grant_required_targets(session,{'assessment_gaps':[gap]})
 assert ('1' in session.scope_read_grants.get('s',{})) == (damage is None)
 assert session.direct_search_scope==scope
 if damage is None:
  assert session.scope_read_grants['s']['1']['gap_hash']==digest(gap)
  assert session.scope_read_grants['s']['2']=={'reference_id':'R'}


def test_missing_facts_never_become_source_goal():
 z=setup();inv,d,v,p,a,de,x=z
 inv.p['assessment_gaps']=[{'material':True,'kind':'MISSING_FACT','target_binding':{'status':'EXACT'}}]
 assert not sg.pending_before_selection(inv)


def test_gap_closure_proof_and_target(monkeypatch):
 from semantic_runtime.legal_agent import evidence_inventory as invt
 inv,d,v,p,a,de,x=setup();sg.record(v,inv,d,a,su.state_for(inv,d));st=su.state_for(inv,d)
 goal=st['source_goals'][0];goal.update(origin_gap_id='G',expected=[{'block_id':'needed','start_cp':0,'end_cp':4}]);su.save(inv,st)
 d['assessment_gaps']=[{'gap_id':'G'}]
 d['sources']=[{'id':'E1','document_id':'other','text':'검증 원문','spans':[{'block_id':'other','start_cp':0,'end_cp':4}]}]
 monkeypatch.setattr(invt,'check_presented_page',lambda *x:None)
 for status in ('RESOLVED','NOT_NEEDED'):
  with pytest.raises(ProposalError):sg.validate_gap_closure(inv,d,{'gap_id':'G','status':status,'reason':'제','basis_refs':[]})
 # A current original can support an explicit exclusion; it cannot prove arrival.
 sg.validate_gap_closure(inv,d,{'gap_id':'G','status':'NOT_NEEDED','reason':'적용 대상이 달라 제외','basis_refs':['E1']})
 with pytest.raises(ProposalError):sg.validate_gap_closure(inv,d,{'gap_id':'G','status':'RESOLVED','reason':'확보','basis_refs':['E1']})
 st=su.state_for(inv,d);st['source_goals'][0]['status']='ACQUIRED';su.save(inv,st)
 with pytest.raises(ProposalError):sg.validate_gap_closure(inv,d,{'gap_id':'G','status':'RESOLVED','reason':'다른 원문','basis_refs':['E1']})
