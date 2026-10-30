from copy import deepcopy
import json
import pytest
from semantic_runtime.legal_agent import investigation_supervisor as su,answer_progress as ap
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from test_supervisor import fixture,seed

def setup():
 inv,d,v,p,s,x=fixture();seed(inv,d)
 actions={t:{'action':'OPEN_LAW','identity':{'document_id':t}} for t in ('T1','T2')}
 result={'directive':'CONTINUE_TARGETED','reason':'추가 조사가 필요하다','remaining_scope':'미확보 세부 기준',
         'action':{'choice':'OPEN_LAW','target':'T2'}}
 calls=[]
 def invoke(*args):calls.append(1);inv.s.repo.reserved+=1;return deepcopy(result)
 inv.invoke=invoke
 def run(key='k'):return su.gate(inv,d,actions,p,v,x(v),s,x,key)
 return inv,d,v,actions,result,calls,run

def test_reject_directive_but_execute_independent_source_route_and_resume():
 inv,d,v,actions,result,calls,run=setup();out=run();st=su.state_for(inv,d)
 assert out['target']=='T2' and not st['halt'] and len(calls)==1
 assert st['coverage_review'][-1]['directive_accepted'] is False
 assert st['coverage_review'][-1]['independent_route_authorized'] is True
 assert st['receipts']['k']['independent_recovery'] is True
 assert st['directive_rejections']['k']['remaining_scope']=='미확보 세부 기준'
 assert result['directive']=='CONTINUE_TARGETED' and result['action']['target']=='T2'
 su.before_execute(inv,d,out);su.after_execute(inv,d,out,True)
 inv.p=json.loads(json.dumps(inv.p));assert run()==out and len(calls)==1
 assert su.state_for(inv,d)['execution'][d['presentation_id']]['independent_recovery']
 assert [k for k,_ in inv.s.repo.events].count('SUPERVISOR_DIRECTIVE_REJECTED')==1
 assert not any(k=='SUPERVISOR_DECISION' for k,_ in inv.s.repo.events)

@pytest.mark.parametrize('failure',['hidden_target','unauthorized','stale','time','tools','permits','repeated'])
def test_invalid_or_exhausted_route_cannot_recover(failure):
 inv,d,v,actions,result,calls,run=setup()
 if failure=='hidden_target':result['action']['target']='not-offered'
 if failure in ('unauthorized','stale'):
  def invalid(*a):raise ContractError(failure)
  inv.validate=invalid
 if failure=='time':
  original=inv.invoke
  def elapsed(*a):r=original(*a);inv.left=lambda:30;return r
  inv.invoke=elapsed
 if failure=='tools':
  original=inv.s.repo.budget
  inv.s.repo.budget=lambda:{**original(),'tool_limit':2,'tool_used':2}
 if failure=='permits':
  st=su.state_for(inv,d);st['directive_route_permits']={'a':{},'b':{}};su.save(inv,st)
 if failure=='repeated':
  run();d['presentation_id']='next';actions['T2']['identity']={'document_id':'T2'}
  st=su.state_for(inv,d);st['unchanged']={'Q1':1};su.save(inv,st)
 with pytest.raises(ContractError if failure in ('unauthorized','stale') else ap.ProgressHandoff):run('again' if failure=='repeated' else 'k')
 assert not any(k=='SUPERVISOR_DECISION' for k,_ in inv.s.repo.events)
 if failure!='repeated':assert not any(k=='SUPERVISOR_INDEPENDENT_ROUTE_RECOVERED' for k,_ in inv.s.repo.events)

def test_same_route_redirect_is_still_rejected():
 inv,d,v,actions,result,calls,run=setup();result.update(directive='REDIRECT');result['action']['target']='T1'
 with pytest.raises(ap.ProgressHandoff):run()
 assert not any(k=='SUPERVISOR_INDEPENDENT_ROUTE_RECOVERED' for k,_ in inv.s.repo.events)

def test_invalid_terminal_never_becomes_independent_recovery():
 inv,d,v,actions,result,calls,run=setup();st=su.state_for(inv,d)
 st['coverage_review']=[{'directive':'CONTINUE_TARGETED'}];su.save(inv,st)
 assert not su.recover_changed_route(inv,d,actions,st,{},'k',result,{'next_action':'OPEN_LAW'}, {'next_action':'FINISH','targets':[]})
 assert not st.get('directive_route_permits')

@pytest.mark.parametrize('mutation',['binding','state_hash','target','presentation'])
def test_recovered_route_still_checks_commit_binding(mutation):
 inv,d,v,actions,result,calls,run=setup();out=run()
 if mutation=='binding':inv.p['binding']='other'
 if mutation=='state_hash':next(iter(inv.p['investigation_supervisor'].values()))['calls']=100
 if mutation=='target':out['targets']=['evil']
 if mutation=='presentation':d['presentation_id']='other'
 with pytest.raises(ContractError):su.before_execute(inv,d,out)
