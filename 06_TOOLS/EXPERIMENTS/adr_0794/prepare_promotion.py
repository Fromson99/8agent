"""Integrate only qualified deltas, then prepare an exact release and rollback."""
from pathlib import Path
import json,hashlib,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0794-definition-entry-storage-binding';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');b=read(D/'baseline.json');C=R/f['code_root'];result=read(A/'artifacts/run-001/result.json')
assert result['strict_success'] and all(result['checks'].values())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(C/n)==h for n,h in f['serving_files'].items())
auth={'authorized_by':'user','authorization_text':'정의연결 최초검색에 활용하게 바꿔봐잘','quality_gate_override':False,'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'connected','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'limitations':result['limitations']}
sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.release_qualification import verify
verify(R,auth,validation)
backup=A/'artifacts/working-before';backup.mkdir(exist_ok=False);changes=[]
def save(p,content):
 rel=p.relative_to(R);out=backup/rel;before=sha(p) if p.exists() else None
 if p.exists():out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content);changes.append({'path':str(rel),'before':before,'after':sha(p)})
changed={n:h for n,h in f['serving_files'].items() if h!=b['manifest']['files'].get(n) and not n.startswith('02_BACKEND/ENGINES/') and n!='00_SYSTEM/PIPELINE.json'}
for n,h in changed.items():
 if n in b['manifest']['files']:assert sha(R/n)==b['manifest']['files'][n],n
 else:assert not (R/n).exists(),n
for n in changed:save(R/n,(C/n).read_bytes())
for p in (C/'05_TESTS').glob('test_definition_entry*.py'):
 assert not (R/'05_TESTS'/p.name).exists();save(R/'05_TESTS'/p.name,p.read_bytes())
engines={}
for p in (R/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p);files=v.get('files',{});old=dict(files)
 for n,h in changed.items():
  if n in files:files[n]=h
 if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in files:files['02_BACKEND/semantic_runtime/legal_agent/definition_entry.py']=changed['02_BACKEND/semantic_runtime/legal_agent/definition_entry.py']
 if files!=old:save(p,(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode());engines[str(p.relative_to(R))]=sha(p)
p=R/'00_SYSTEM/PIPELINE.json';v=read(p)
for e in v['engines'].values():
 if e['manifest'] in engines:e['sha256']=engines[e['manifest']]
def profile_pin(obj):
 if isinstance(obj,dict):
  if obj.get('path')=='00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json' and 'sha256' in obj:obj['sha256']=changed[obj['path']]
  for x in obj.values():profile_pin(x)
 elif isinstance(obj,list):
  for x in obj:profile_pin(x)
profile_pin(v);save(p,(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
auth['rollback_pipeline']=bound(backup/'00_SYSTEM/PIPELINE.json')
put(A/'artifacts/working-integration.json',{'status':'PASS','changes':changes,'preserved_other_working_differences':[n for n,h in f['serving_files'].items() if sha(R/n)!=h],'served_candidate':f['code_root']})
put(A/'artifacts/main-authorization.json',auth);put(A/'artifacts/main-validation.json',validation)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',str(R/read(D/'data-binding.json')['path']),'--release-id','definition-entry-navigation-20261015-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Qualified deltas integrated and exact local release prepared')
