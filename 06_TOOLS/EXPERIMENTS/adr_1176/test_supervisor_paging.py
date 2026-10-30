from copy import deepcopy
import json,gzip
from pathlib import Path
import pytest
from jsonschema import validate
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import investigation_supervisor as su,read_candidate_pages as pages,answer_progress as ap
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.completion_contracts import obj
from test_supervisor import fixture,seed

def paged(page=0,count=41):
 inv,d,v,p,s,old_expand=fixture();seed(inv,d)
 inv.policy.update(minimal_input=True,read_candidate_page_size=20)
 p['read_candidates']=[{'target':f'R{i}','heading':f'제{i}조'} for i in range(1,count+1)]
 s['anyOf'].append(obj({'choice':{'const':'READ'},'selections':{'type':'array','minItems':1,'items':obj({'target':{'enum':[r['target'] for r in p['read_candidates']]}})}}))
 inv.p['read_candidate_pager']={'binding':digest(p),'page':page,'sequence':0}
 def expand(x):
  if x['choice']=='READ':
   validate({'choice':x['choice'],'selections':x['selections']},s)
   return {'next_action':'READ_ARTICLES','targets':[r['target'] for r in x['selections']]}
  return old_expand(x)
 return inv,d,v,p,s,expand

def response(action,directive='REDIRECT'):
 return {'directive':directive,'reason':'다음 후보 범위 확인','remaining_scope':'아직 읽지 않은 조항','action':action}

def run(inv,d,v,p,s,expand,callback=None):
 return su.gate(inv,d,{},p,v,expand(v),s,expand,'key',prepare_page=callback)

@pytest.mark.parametrize('page,choice,target',[(0,pages.NEXT,'R21'),(1,pages.PREVIOUS,'R1')])
def test_page_then_read_same_budget_and_preparation(page,choice,target):
 inv,d,v,p,s,expand=paged(page);calls=[];prepared=[];original=deepcopy((d,v,p))
 def prepare(view):prepared.append([x['target'] for x in view['read_candidates']]);return view
 def invoke(prompt,body,schema,*args):
  calls.append(body);inv.s.repo.reserved+=1
  action={'choice':choice} if len(calls)==1 else {'choice':'READ','selections':[{'target':target}]}
  answer=response(action);validate(answer,schema);return answer
 inv.invoke=invoke;result=run(inv,d,v,p,s,expand,prepare)
 assert result['targets']==[target] and len(calls)==2 and inv.s.repo.reserved==2
 assert calls[-1]['read_candidates'][0]['target']==target and len(prepared)==2
 assert (d,v,p)==original
 moves=[e for k,e in inv.s.repo.events if k=='READ_CANDIDATE_PAGE_SELECTED']
 assert len(moves)==1 and moves[0]['actor']=='supervisor'
 assert not moves[0]['originals_acquired'] and not moves[0]['judgments_completed']
 su.before_execute(inv,d,result)
 with pytest.raises(ContractError):su.before_execute(inv,d,expand(v))
 inv.p=json.loads(json.dumps(inv.p));assert run(inv,d,v,p,s,expand)==result
 assert len(calls)==2

def test_two_page_moves_exhaust_supervisor_without_execution():
 inv,d,v,p,s,expand=paged();calls=[]
 def invoke(*args):calls.append(1);inv.s.repo.reserved+=1;return response({'choice':pages.NEXT})
 inv.invoke=invoke
 with pytest.raises(ap.ProgressHandoff):run(inv,d,v,p,s,expand)
 assert len(calls)==2 and inv.p['read_candidate_pager']['page']==2
 with pytest.raises(ContractError):su.before_execute(inv,d,expand(v))
 with pytest.raises(ap.ProgressHandoff):run(inv,d,v,p,s,expand)
 assert len(calls)==2

@pytest.mark.parametrize('choice,hidden',[(pages.PREVIOUS,False),(pages.NEXT,True)])
def test_out_of_range_page_or_hidden_read_rejected(choice,hidden):
 inv,d,v,p,s,expand=paged();calls=[]
 def invoke(*args):
  calls.append(1)
  return response({'choice':'READ','selections':[{'target':'R21'}]} if hidden else {'choice':choice})
 inv.invoke=invoke
 with pytest.raises(ap.ProgressHandoff):run(inv,d,v,p,s,expand)
 assert inv.p['read_candidate_pager']['page']==0 and len(calls)==1
 with pytest.raises(ContractError):su.before_execute(inv,d,expand(v))

def test_continue_cannot_change_page():
 inv,d,v,p,s,expand=paged();inv.invoke=lambda *a:response({'choice':pages.NEXT},'CONTINUE_TARGETED')
 with pytest.raises(ap.ProgressHandoff):run(inv,d,v,p,s,expand)
 assert inv.p['read_candidate_pager']['page']==0

@pytest.mark.parametrize('when',['before','after'])
def test_resume_page_transition_once(monkeypatch,when):
 class Interrupted(BaseException):pass
 inv,d,v,p,s,expand=paged();calls=[];native=pages.move
 def invoke(*args):
  calls.append(1)
  return response({'choice':pages.NEXT} if len(calls)==1 else {'choice':'READ','selections':[{'target':'R21'}]})
 def crash(*args,**kwargs):
  if when=='after':native(*args,**kwargs)
  raise Interrupted()
 inv.invoke=invoke;monkeypatch.setattr(pages,'move',crash)
 with pytest.raises(Interrupted):run(inv,d,v,p,s,expand)
 assert su.state_for(inv,d)['page_pending'] and su.state_for(inv,d)['pending'] is None
 inv.p=json.loads(json.dumps(inv.p));monkeypatch.setattr(pages,'move',native)
 out=run(inv,d,v,p,s,expand);assert out['targets']==['R21'] and len(calls)==2
 assert inv.p['read_candidate_pager']['sequence']==1
 assert len([1 for k,e in inv.s.repo.events if k=='READ_CANDIDATE_PAGE_SELECTED'])==1

def test_resume_page_rejects_changed_menu():
 inv,d,v,p,s,expand=paged();st=su.state_for(inv,d)
 st['page_pending']={'presentation':digest(d),'menu':digest(p['read_candidates']),'choice':pages.NEXT,'before':deepcopy(inv.p['read_candidate_pager'])};su.save(inv,st)
 p['read_candidates'][-1]['target']='foreign'
 with pytest.raises(ContractError):su.complete_page_transition(inv,st,d,p)

@pytest.mark.parametrize('field,value',[('binding','other'),('sequence',5),('page',True)])
def test_shared_pager_denies_stale_or_invalid_state(field,value):
 inv,d,v,p,s,expand=paged();before=deepcopy(inv.p['read_candidate_pager']);inv.p['read_candidate_pager'][field]=value
 with pytest.raises(ContractError):pages.move(inv,p,pages.NEXT,expected_state=before)

def test_existing_model_reserve_preserved_after_page():
 inv,d,v,p,s,expand=paged();inv.s.repo.reserved=36;calls=[]
 def invoke(*a):calls.append(1);inv.s.repo.reserved+=1;return response({'choice':pages.NEXT})
 inv.invoke=invoke
 with pytest.raises(ap.ProgressHandoff):run(inv,d,v,p,s,expand)
 assert len(calls)==1 and inv.s.repo.reserved==37

def test_saved007_guidance_schema_mismatch_is_removed():
 root=Path(__file__).resolve().parents[3];p=root/'04_EXPERIMENTS/ADR/ADR-1169-supervisor-cm3-memory-reclaimed/artifacts/run-001/cm-007'
 wire=json.load(gzip.open(p/'wire/006.json.gz','rt'))
 assert 'NEXT_READ_CANDIDATES' in wire['messages'][0]['content']
 assert 'NEXT_READ_CANDIDATES' not in json.dumps(wire['response_format'])
 raw=json.load(gzip.open(p/'canonical/006.json.gz','rt'));payload=raw['view']
 assert payload['read_candidate_page']['more_available']
 # Saved view contains20 visible cards. Add a synthetic boundary card only;
 # this is contract validation, not reconstructed real retrieval quality.
 data={**payload,'read_candidates':payload['read_candidates']+[{'target':'SYNTHETIC_HIDDEN'}]}
 base=next(b['properties']['action'] for b in raw['schema']['anyOf'] if 'action' in b['properties'])
 view,schema=pages.page_view(data,base,0,20)
 assert pages.NEXT in view['read_candidate_page']['actions']
 validate(response({'choice':pages.NEXT}),su.schema_for(schema))
