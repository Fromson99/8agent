import pytest,json,gzip
from pathlib import Path
from types import SimpleNamespace as NS
from copy import deepcopy
from semantic_runtime.legal_agent import investigation_supervisor as su, read_judgment as rj, answer_progress as ap
from semantic_runtime.legal_agent.errors import ContractError,TransportError

class Repo:
 def __init__(self):self.events=[]
 def budget(self):return {'model_limit':40,'finalization_reserve':3,'model_reserved':0}
 def event(self,k,v):self.events.append((k,deepcopy(v)))
class Called(Exception):pass

def fixture():
 d={'presentation_id':'p1','issues':[{'id':'Q1','request_quote':'기준?'}],'sources':[{'id':'E1','document_id':'law','source_id':'article','text':'원문','spans':[{'block_id':'b1','start_cp':0,'end_cp':2,'text':'원문'}]}],'laws':[]}
 inv=NS(policy={'supervisor_mode':'enforce','read_judgment':True},p={'binding':'fixed'},question='기준?',s=NS(repo=Repo(),profile={'selection_time_reserve_seconds':30},scope={'law'}),save=lambda:None,left=lambda:200)
 inv.validate=lambda *a:None
 def invoke(*a):raise Called('existing supervisor requested')
 inv.invoke=invoke
 v={'choice':'FINISH','answer_progress':{'goals':[{'issue_id':'Q1','status':'ANSWERABLE','answer_so_far':'확인한 기준','basis_refs':['E1'],'material_need':'','next_answer_change':'','previous_effect':'ANSWER_CHANGED'}]}}
 dec={'next_action':'FINISH','targets':[]}
 state={'version':rj.VERSION,'heads':{},'needs':{},'conflicts':{},'receipts':{}}
 for jid,row in rj.originals(inv,d).items():state['heads'][jid]={'id':jid,'seen_material':row['material'],'use':'CORE'}
 state['state_hash']=rj.seal(state);inv.p['read_judgments']={rj.request_key(inv,d):state}
 return inv,d,v,dec,state

def gate(inv,d,v,dec):return su.gate(inv,d,{}, {'read_judgments':{'required':['stale-before-record']}},v,dec,{'type':'object'},lambda v:dec,'key')

def test_finish_handoff_and_resume_preserve_need_history_and_final_validation():
 inv,d,v,dec,state=fixture();st=su.state_for(inv,d);st['calls']=1;st['since_review']=2;st['material_needs']={'old':{'status':'OPEN','reason':'historical declaration'}};su.save(inv,st)
 assert gate(inv,d,v,dec)==dec;su.before_execute(inv,d,dec)
 assert st['calls']==1 and st['material_needs']['old']['status']=='OPEN'
 assert inv.s.repo.events[-1][0]=='SUPERVISOR_FINISH_HANDOFF' and not inv.s.repo.events[-1][1]['legal_sufficiency_approved']
 inv.p=json.loads(json.dumps(inv.p));assert gate(inv,d,v,dec)==dec
 assert len([e for e in inv.s.repo.events if e[0]=='SUPERVISOR_FINISH_HANDOFF'])==1

@pytest.mark.parametrize('which',['need','conflict','unseen','defer','missing_state','disabled','unfinished','not_finish','material_fact','no_issues','page_pending','required_goal'])
def test_incomplete_conditions_cannot_bypass(which):
 inv,d,v,dec,state=fixture();st=su.record(inv,d,v,'key')
 if which in ('need','conflict'):state[{'need':'needs','conflict':'conflicts'}[which]]['n']={'status':'OPEN'}
 if which=='unseen':next(iter(state['heads'].values()))['seen_material']=[]
 if which=='defer':next(iter(state['heads'].values()))['use']='DEFER'
 if which=='missing_state':inv.p['read_judgments']={}
 if which=='disabled':inv.policy['read_judgment']=False
 if which=='unfinished':st['goals'][0].update(status='NEEDS_SOURCE',material_need='예외 원문')
 if which=='not_finish':dec['next_action']='READ_ARTICLES'
 if which=='material_fact':d['assessment_gaps']=[{'material':True,'kind':'MISSING_FACT'}]
 if which=='no_issues':d['issues']=[]
 if which=='page_pending':st['page_pending']={'presentation':'old'}
 if which=='required_goal':st['source_goals']=[{'status':'REQUIRED'}]
 state['state_hash']=rj.seal(state)
 assert not su.ready_for_assessment(inv,d,v,dec,st)

@pytest.mark.parametrize('kind',['needs','conflicts'])
def test_open_need_runs_existing_supervisor(kind):
 inv,d,v,dec,state=fixture();state[kind]['n']={'status':'OPEN'};state['state_hash']=rj.seal(state)
 with pytest.raises(Called):gate(inv,d,v,dec)
 assert su.state_for(inv,d)['calls']==1

def test_source_goal_control_precedes_handoff(monkeypatch):
 from semantic_runtime.legal_agent import source_goal_control as g
 inv,d,v,dec,state=fixture();inv.policy['source_goal_control']=True;route={'next_action':'READ_ARTICLES','targets':['required']}
 monkeypatch.setattr(g,'resolve',lambda *a,**k:route)
 assert gate(inv,d,v,dec)==route
 assert not inv.s.repo.events

@pytest.mark.parametrize('kind',['pending','halt','tamper','acl','invalid_basis'])
def test_fail_closed_states_preserved(kind):
 inv,d,v,dec,state=fixture();st=su.state_for(inv,d)
 if kind=='pending':st['pending']={'key':'unknown'};su.save(inv,st)
 if kind=='halt':st['halt']='STOP';su.save(inv,st)
 if kind=='tamper':next(iter(state['heads'].values()))['seen_material']=[]
 if kind=='acl':inv.s.scope=set()
 if kind=='invalid_basis':v['answer_progress']['goals'][0]['basis_refs']=['hidden']
 expected=TransportError if kind=='pending' else ap.ProgressHandoff if kind=='halt' else ContractError
 if kind=='invalid_basis':expected=Exception
 with pytest.raises(expected):gate(inv,d,v,dec)
 assert not any(k=='SUPERVISOR_FINISH_HANDOFF' for k,x in inv.s.repo.events)

def test_actual_saved_finish005_is_eligible_without_rewriting_answer_or_history():
 root=Path('/home/jin/8-AGENT');p=root/'04_EXPERIMENTS/ADR/ADR-1309-main136-sqlite-latency/artifacts/live/ontology-369-after/canonical'
 def read(n):return json.load(gzip.open(p/n,'rt'))
 d=read('005.json.gz')['view'];v=read('005-output.json.gz');inv,_,_,dec,_=fixture();inv.question=d['current_request'];inv.s.scope={s['document_id'] for s in d['sources']}
 visible=rj.originals(inv,d);ctx=d['read_judgments'];heads={}
 # Material fingerprints are unchanged by request-key renaming; use the saved
 # canonical source identity and recorded judgments, not synthetic new opinions.
 for jid,row in visible.items():
  saved=next(h for h in ctx['judgments'] if h['source_id']==row['source_id'] and h['document_id']==row['document_id']);heads[jid]=deepcopy(saved)
 state={'version':rj.VERSION,'heads':heads,'needs':{n['id']:n for n in ctx['needs']},'conflicts':{n['id']:n for n in ctx['conflicts']},'receipts':{}};state['state_hash']=rj.seal(state);inv.p['read_judgments']={rj.request_key(inv,d):state}
 st=su.state_for(inv,d);st['source_goals']=deepcopy(d['source_goal_context']['goals']);st['calls']=1;st['since_review']=2;su.save(inv,st)
 original=deepcopy(v);assert gate(inv,d,v,dec)==dec and v==original
 assert st['calls']==1 and all(g['status']=='ACQUIRED' for g in st['source_goals'])
 assert not any(k=='SUPERVISOR_REQUESTED' for k,x in inv.s.repo.events)
