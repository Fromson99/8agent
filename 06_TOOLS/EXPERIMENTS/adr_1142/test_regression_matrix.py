from copy import deepcopy
from pathlib import Path
import json
from types import SimpleNamespace as NS
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import stable_references as sr,law_navigation as ln,law_candidates as lc,decision_projection as dp
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from test_stable_recovery_isolated import RefRepo
M=json.loads((Path(__file__).parents[3]/'04_EXPERIMENTS/ADR/ADR-1142-main108-recovery-integration/artifacts/design/regression-matrix.json').read_text())

@pytest.mark.parametrize('count,documents,order',M['references'])
def test_fresh_reference_matrix(tmp_path,count,documents,order):
 path=tmp_path/'journal';repo=RefRepo(path);known={};docmap={}
 identifiers=['J'+format(1000+i*13,'024x') for i in range(count)]
 visits=list(range(count))
 if order==1:visits.reverse()
 if order==2:visits=visits[::2]+visits[1::2]
 for step,i in enumerate(visits):
  did='fresh-doc-'+str(i%documents);name='독립규정-'+str(i%documents)
  body={'judgments':[{'id':identifiers[i],'document_id':did,'document_name':name,'finding':'J1이라는 원문 표현은 수정하지 않는다.'}]}
  with repo.transaction():v=sr.bind(repo,body)
  refs=NavigationReferences(v);short=refs.forward[identifiers[i]];assert short not in known.values();known[identifiers[i]]=short
  entry=next(d for d in v['reference_registry']['documents'] if d['document_id']==did)
  if did in docmap:assert entry['id']==docmap[did]
  else:docmap[did]=entry['id']
  if step%2==1:repo.db.close();repo=RefRepo(path)
  for ident in reversed(list(known)):
   with repo.transaction():again=sr.bind(repo,{'judgments':[{'id':ident,'finding':'J1이라는 원문 표현은 수정하지 않는다.'}]})
   rr=NavigationReferences(again);assert rr.forward[ident]==known[ident]
   assert rr.view(again)['judgments'][0]['finding']=='J1이라는 원문 표현은 수정하지 않는다.'
   sr.verify(repo,again['reference_registry'])
 repo.db.close()

@pytest.mark.parametrize('count,reverse',M['pages'])
def test_fresh_page_detail_boundaries(tmp_path,monkeypatch,count,reverse):
 allowed=['source-'+str(i) for i in range(count)];calls=[];monkeypatch.setattr(lc,'allowed',lambda s:allowed)
 text={sid:'조문 미리보기 '+sid+' 한글\n🙂 '+('범위 '*(i+1)) for i,sid in enumerate(allowed)}
 idx=NS(manifest={'index_sha256':'fresh-index'},check_unchanged=lambda:None)
 def hit(db,terms,sid,scope,**kw):calls.append(sid);return {'items':[{'unit_id':'child','article_unit_id':'root','text':text[sid]}]}
 idx.hit_page=hit;inv=NS(s=NS(store=NS(check_unchanged=lambda:None)),idx=idx,db=None,save=lambda:None,p={'binding':'fresh','candidate_preview_queries':{'q':{'terms':['새범위'],'allowed':allowed,'args':{},'document_id':'doc','index_sha256':'fresh-index'}}})
 candidates={'T'+str(i):{'identity':{'source_id':sid,'document_id':'doc'}} for i,sid in enumerate(allowed)}
 data={'laws':[{'document_id':'doc','name':'새법령','article_matches':[{'source_id':sid,'read_action':'T'+str(i),'article':'제'+str(i+1)+'조','deferred_preview':{'query':'q','source_id':sid}} for i,sid in enumerate(allowed)]}]};before=digest(data)
 pages=[list(candidates)[i:i+20] for i in range(0,count,20)]
 if reverse:pages.reverse()
 for targets in pages:
  prior=len(calls);result=ln.Investigation.prepare_read_details(inv,data,candidates,targets)
  assert len(calls)-prior==len(targets)<=20
  visible=dp.read_candidate_rows(result,{t:candidates[t] for t in targets});assert len(visible)==len(targets)
  for row in visible:assert row['preview']==text[candidates[row['target']]['identity']['source_id']][:240]
  inv.p=json.loads(json.dumps(inv.p));ln.Investigation.prepare_read_details(inv,data,candidates,targets);assert len(calls)==prior+len(targets)
 assert len(calls)==count and len(set(calls))==count and digest(data)==before
