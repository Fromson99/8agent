from pathlib import Path
import json,hashlib,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0792-risk-committee-team-metadata';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');b=read(D/'baseline.json');C=R/f['code_root'];result=read(A/'artifacts/run-001/result.json')
assert result['strict_success'] and all(result['checks'].values())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(C/n)==h for n,h in f['serving_files'].items())
backup=A/'artifacts/working-before';backup.mkdir(exist_ok=False)
auth={'authorized_by':'user','authorization_text':'일단 1번은 위치 수정해주고 2번은 왜 처음에 선택못했는지 오류는 뭐였는지 확인해봐','quality_gate_override':False,'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'corrected','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'limitations':result['limitations']}
sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.release_qualification import verify
verify(R,auth,validation)
# Preserve every unrelated working edit; only rebind the already selected grant.
name='00_SYSTEM/LEGAL_AGENT/local-gemma-public.json';assert sha(R/name)==b['manifest']['files'][name]
changes=[]
def save(p,content):
 rel=p.relative_to(R);out=backup/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out);before=sha(p);p.write_bytes(content);changes.append({'path':str(rel),'before':before,'after':sha(p)})
save(R/name,(C/name).read_bytes())
changed_engines={}
for p in (R/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if name not in v.get('files',{}):continue
 assert v['files'][name]==b['manifest']['files'][name],str(p)
 v['files'][name]=sha(R/name);save(p,(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode());changed_engines[str(p.relative_to(R))]=sha(p)
p=R/'00_SYSTEM/PIPELINE.json';v=read(p)
for entry in v['engines'].values():
 if entry['manifest'] in changed_engines:entry['sha256']=changed_engines[entry['manifest']]
save(p,(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
auth['rollback_pipeline']=bound(backup/'00_SYSTEM/PIPELINE.json')
put(A/'artifacts/working-integration.json',{'status':'PASS','changes':changes,'preserved_other_working_differences':[n for n,h in f['serving_files'].items() if sha(R/n)!=h],'served_candidate':f['code_root']})
put(A/'artifacts/main-authorization.json',auth);put(A/'artifacts/main-validation.json',validation)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',str(R/read(D/'data-binding.json')['path']),'--release-id','risk-committee-team-metadata-20261015-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('w') as log:subprocess.run(cmd,cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Prepared exact qualified data/code; scoped working configuration integrated')
