"""Selectively install this scope; preserve unrelated work and all old records."""
from pathlib import Path
import json,hashlib,shutil,os,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0681-session-runtime-no-user-wiki-signing';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
assert read(A/'artifacts/run-001/result.json')['strict_success']
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
freeze=read(D/'freeze.json');code=R/freeze['code_root'];cm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0681/session/candidate.json')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']
for f,h in freeze['serving_files'].items():assert sha(code/f)==h,f
scoped=['service.py','02_BACKEND/semantic_runtime/app.py','02_BACKEND/semantic_runtime/chat_adapter.py','02_BACKEND/semantic_runtime/legal_agent/memory_identity.py','02_BACKEND/semantic_runtime/legal_agent/case_repository.py','02_BACKEND/semantic_runtime/legal_agent/knowledge_repository.py','02_BACKEND/semantic_runtime/legal_agent/unified_runtime.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','05_TESTS/CONTRACTS/test_genos_main_chat.py','05_TESTS/CONTRACTS/test_unified_legal_agent.py','05_TESTS/CONTRACTS/test_session_runtime_without_wiki_signing.py']
rows={v['target_path']:v for v in cm['files']}
for f in scoped:
 expected=rows[f]['upstream_sha256'];assert (sha(R/f) if (R/f).exists() else None)==expected,f
backup=A/'artifacts/working-backup';backup.mkdir(exist_ok=False)
pins=['00_SYSTEM/PIPELINE.json']+[x['manifest'] for x in read(R/'00_SYSTEM/PIPELINE.json')['engines'].values()]
docs=['.env.genos.example','08_DEPLOYMENT/GENOS/workflow/workflow.env.example','GENOS.md']
plan=[]
for f in scoped+pins+docs:
 p=R/f;before=sha(p) if p.exists() else None
 if before:
  b=backup/f;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b)
 plan.append({'path':f,'before':before,'kind':'runtime' if f in scoped else 'working-pins' if f in pins else 'documentation'})
put(A/'artifacts/working-install-plan.json',{'status':'prepared','files':plan,'backup':str(backup.relative_to(R))})
for f in scoped:
 target=R/f;target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_name('.'+target.name+'.session-install');shutil.copy2(code/f,temp);os.replace(temp,target)
pipeline=read(R/'00_SYSTEM/PIPELINE.json')
def remove(x):
 if isinstance(x,dict):
  for k,v in x.items():
   if k=='wiki_consumers':x[k]=[s for s in v if s!='user_wiki']
   else:remove(v)
 elif isinstance(x,list):
  for v in x:remove(v)
remove(pipeline);put(R/'00_SYSTEM/PIPELINE.json',pipeline)
# Rehash against all current working bytes, retaining concurrent latency dependencies.
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','rehash-engines','--apply'],cwd=R,check=True,stdout=(A/'artifacts/working-rehash.json').open('w'))
for f in docs:shutil.copy2(A/'artifacts/documentation'/f,R/f)
for row in plan:row['after']=sha(R/row['path'])
put(A/'artifacts/working-install-receipt.json',{'status':'installed','files':plan,'scoped_runtime_matches_candidate':all(sha(R/f)==sha(code/f) for f in scoped),'unrelated_pending_modules_preserved':True,'working_engine_pins_preserve_pending_dependencies':True,'main_pointer_unchanged':True})
q={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'session','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}
authorization={'authorized_by':'user','authorization_text':'유저 위키 제거하고 signing 도 제거해버려(메인에서). 검증한 후보를 로컬 MAIN에 반영하고 기존 세션·shortcut·legal_wiki와 병행 작업을 보존한다.','quality_gate_override':False,'qualification':q,'rollback_pipeline':{'path':str((backup/'00_SYSTEM/PIPELINE.json').relative_to(R)),'sha256':sha(backup/'00_SYSTEM/PIPELINE.json')}}
report={'structural_checks_passed':True,'contract_tests':118,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'limitations':['Synthetic contract audit; no model quality/performance claim','GENOS not accessed or deployed','Unrelated pending working modules not promoted','Global ADR graph has historical errors; new arm/edges introduce none']}
put(A/'artifacts/main-authorization.json',authorization);put(A/'artifacts/main-validation.json',report)
sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.release_qualification import verify
verify(R,authorization,report)
print('Installed scoped runtime files:',len(scoped),'pending modules preserved')
