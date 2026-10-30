from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace as NS
from concurrent.futures import ThreadPoolExecutor
import json,time
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import stable_references as sr,read_judgment as rj,compact_model_input as cm
from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
from semantic_runtime.legal_agent.navigation_input import NavigationReferences,STABLE_INSTRUCTIONS
from semantic_runtime.legal_agent.gateway import compact_wire_view,WIRE_PROJECTION
from semantic_runtime.legal_agent.repository import encoded
from semantic_runtime.legal_agent.errors import ContractError
from test_stable_recovery_isolated import view,new_setup,fresh,validate_new


def init(path):
 binding={'profile_sha256':'test-profile','data_generation':'synthetic','principal':'owner'}
 ctx=NS(run_id='run',query={'id':'q'},binding=binding,binding_hash=digest(binding),request={'question':'synthetic'},deadline_at='2099-01-01T00:00:00Z',deadline=time.monotonic()+500)
 return UnifiedRepository(path,ctx,{'max_model_attempts':40,'max_tool_actions':1024,'finalization_reserve':5})


def test_actual_v6_save_view_and_reserve_verify_stable_mapping_and_wire(tmp_path):
 repo=init(tmp_path/'journal');v=repo.save_view('investigate',view(),[]);refs=NavigationReferences(v)
 wire=cm.project(compact_wire_view(refs.view(v),'investigate'));request={'messages':[{'role':'system','content':'test'},{'role':'user','content':encoded({'view':wire})}]}
 ident=repo.reserve_attempt(v,request,'logical',1,'investigate',numbered_references=refs,wire_projection=WIRE_PROJECTION,minimal_input_projection=cm.VERSION)
 assert ident and repo.budget()['model_reserved']==1
 assert repo.db.execute("SELECT count(*) FROM event WHERE kind='MODEL_REFERENCE_REGISTERED'").fetchone()[0]==1
 repo.close();repo=UnifiedRepository(tmp_path/'journal');v2=repo.save_view('investigate',view(),[])
 assert NavigationReferences(v2).forward==refs.forward
 registry=deepcopy(v2['reference_registry']);registry['binding']='changed';registry['hash']=digest({k:v for k,v in registry.items() if k!='hash'})
 with pytest.raises(ContractError):sr.verify(repo,registry)
 repo.close()


def test_concurrent_view_writers_allocate_unique_stable_ids(tmp_path):
 path=tmp_path/'journal';repo=init(path);repo.close()
 def write(i):
  r=UnifiedRepository(path)
  try:return r.save_view('investigate',view(i,'규정'+str(i),'d'+str(i)),[])['reference_registry']
  finally:r.close()
 with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,[5,1]))
 r=UnifiedRepository(path);last=r.save_view('investigate',view(5,'규정5','d5'),[])['reference_registry']
 assert len(last['documents'])==2 and len(set(last['mapping'].values()))==len(last['mapping'])
 for registry in results:sr.verify(r,registry)
 r.close()

@pytest.mark.parametrize('field',['stable_navigation_references','new_read_reviews','independent_read_recovery'])
def test_actual_profile_flags_and_types(field):
 from semantic_runtime.legal_agent import law_candidates as lc
 root=Path(lc.__file__).resolve().parents[3];p=json.loads((root/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
 assert lc.validate_policy(p['candidate_navigation'])[field] is True
 bad=deepcopy(p['candidate_navigation']);bad[field]=1
 with pytest.raises(ContractError):lc.validate_policy(bad)
 assert '이 화면에만' not in STABLE_INSTRUCTIONS and '조사 동안' in STABLE_INSTRUCTIONS


def test_new_conflict_is_explicit_and_retains_both_opinions():
 inv,data,page,*_=new_setup();ctx=rj.context(inv,data,'a');raw=fresh(ctx);v,ch=validate_new(raw,ctx,data);rj.record(inv,data,v,'a',ctx,{})
 old=next(iter(rj.state_for(inv,data)['heads']));data['sources']=[page('b','다른 조건 원문')];ctx=rj.context(inv,data,'b');raw=fresh(ctx)
 row=next(iter(raw['read_review']['new_reviews'].values()));row.update(operation='CONFLICT',use='DEFER',conflicts_with=[old])
 v,ch=validate_new(raw,ctx,data);rj.record(inv,data,v,'b',ctx,{})
 conflict=next(iter(rj.state_for(inv,data)['conflicts'].values()));assert len(conflict['opinions'])==2 and conflict['status']=='OPEN'


def test_previous_final_review_semantics_stay_in_model_copy():
 v={'read_judgments':{'previous_final_review':[{'finding':'이전 검토 의견','reason':'예외 원문 필요','basis_refs':['E1']}]}}
 assert cm.project(v)['read_judgments']['previous_final_review'][0]['reason']=='예외 원문 필요'
