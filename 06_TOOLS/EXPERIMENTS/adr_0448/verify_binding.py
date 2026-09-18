"""Read-only storage contract verification; no model calls, no answer comparison."""
import json,sqlite3,subprocess,os
from collections import Counter
from types import SimpleNamespace
from binding_runtime import load,R,T,D,A,C,read,sha

def main():
 if (A/'verification.json').exists():raise ValueError('completed audit is immutable')
 module,mods,root=load();cm=read(C/'candidate.json');revision=cm['revisions'][-1]
 m=read(D/'실험/manifest.json');m['design']['code_isolation']['candidates']=[{'candidate_id':'inherited','experiment_id':m['experiment_id'],'arm_id':'inherited','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],'runner_path':str((T/'binding_runtime.py').relative_to(R)),'runner_sha256':sha(T/'binding_runtime.py')}]
 (D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/active['manifest_path']);data=R/release['data_path'];manifest=read(data/'manifest.json');before=sha(data/'store.sqlite');assert before==manifest['store_sha256']
 files=[T/'binding_runtime.py',T/'test_binding.py',T/'verify_binding.py',A/'design-before-snapshot.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',data/'manifest.json',data/'store.sqlite',C/'candidate.json']
 for c in [R/'02_BACKEND/lawrag/research/candidates/adr_0445/structured',R/'02_BACKEND/lawrag/research/candidates/adr_0446/routing',R/'02_BACKEND/lawrag/research/candidates/adr_0447/bound',C]:
  parent=read(c/'candidate.json');files+=[c/'candidate.json']+[R/f['frozen_path'] for f in parent['revisions'][-1]['files']]
 hashes={str(p.relative_to(R)):sha(p) for p in sorted(set(files))};(A/'input-lock.json').write_text(json.dumps(hashes,indent=2)+'\n')
 db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;store=SimpleNamespace(db=db,manifest=manifest)
 bound=module.bind_structure(SimpleNamespace(_unit_sources=lambda d,u:[],starts=lambda q,s:{}),store);counts=Counter();reasons=Counter();scopes=Counter();examples=[];raw_errors=[]
 for (d,u),n in bound.units.items():
  counts['total_nodes']+=1;raw=n['raw_structure'];b=n.get('coordinate_binding',{});mode=b.get('mode','not_eligible');counts[mode]+=1
  if mode=='stored_ancestry':
   assert not raw.get('coordinate_key') and not raw.get('coordinate_scope');assert b['ancestor_coordinate_key']==bound.units[(d,b['ancestor_unit_id'])]['raw_structure']['coordinate_key'];scopes[n['coordinate_scope']]+=1
   if len(examples)<5:examples.append({'document_id':d,'unit_id':u,'surface':raw['surface'],'coordinate_key':n['coordinate_key'],'binding':b})
  elif mode=='unresolved':reasons[b['reason']]+=1
  if raw.get('coordinate_scope') and raw.get('coordinate_key'):
   for k in ('coordinate_scope','coordinate_key','legal_coordinate'):
    if raw.get(k)!=n.get(k):raw_errors.append({'document_id':d,'unit_id':u,'field':k})
 db.close();assert sha(data/'store.sqlite')==before
 command=['.venv/bin/python','-B','-m','pytest','-q','-p','no:cacheprovider',str((T/'test_binding.py').relative_to(R))]
 tests=subprocess.run(command,text=True,capture_output=True,env={**os.environ,'PYTHONPATH':'02_BACKEND'});(A/'tests.json').write_text(json.dumps({'command':command,'returncode':tests.returncode,'output':tests.stdout+tests.stderr},ensure_ascii=False,indent=2)+'\n')
 drift=[p for p,h in hashes.items() if sha(R/p)!=h]
 result={'kind':'structure binding contract audit; not new answer or retrieval score','model_calls':0,'active_release':active['release_id'],'generation_id':manifest['generation_id'],'store_sha256':before,'counts':dict(counts),'inherited_by_scope':dict(scopes),'unresolved_reasons':dict(reasons),'examples':examples,'existing_coordinate_errors':raw_errors,'input_drift':drift,'source_unchanged':True,'contract_tests_passed':tests.returncode==0,'passed':tests.returncode==0 and not raw_errors and not drift}
 (A/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='examples'},ensure_ascii=False))
if __name__=='__main__':main()
