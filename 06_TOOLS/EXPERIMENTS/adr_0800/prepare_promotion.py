"""Integrate reviewed handoff deltas and prepare the identical qualified release."""
from pathlib import Path
import json,hashlib,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0800-workflow-literal-request-quotes';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');b=read(D/'baseline.json');C=R/f['code_root'];result=read(A/'artifacts/run-001/result.json');w=read(D/'working-before.json')
assert result['strict_success'] and all(result['checks'].values())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(C/n)==h for n,h in f['serving_files'].items())
auth={'authorized_by':'user','authorization_text':'대사 근거 최적화 설계 후: 한번 구현해봐. 설계 범위는 통합·검증·로컬 MAIN 배선 및 실제 서비스 확인이다.',
      'quality_gate_override':False,'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),
      'arm':'connected','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),
            'source_final_validation':bound(A/'artifacts/final-validation.txt'),'limitations':result['limitations']}
sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.release_qualification import verify
verify(R,auth,validation)
changed={n:h for n,h in f['serving_files'].items() if h!=b['manifest']['files'].get(n)
         and not n.startswith('02_BACKEND/ENGINES/') and n!='00_SYSTEM/PIPELINE.json'}
for n,h in changed.items():
    actual=sha(R/n) if (R/n).exists() else None
    assert actual in (w.get(n),h),n
    # Unrelated edits are never overwritten, including changes predating this task.
    assert actual in (b['manifest']['files'].get(n),h),n
backup=A/'artifacts/working-before';backup.mkdir(exist_ok=True);changes=[]
def save(p,content):
    rel=p.relative_to(R);out=backup/rel
    before=sha(p) if p.exists() else None
    if p.exists() and not out.exists():out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
    p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content)
    changes.append({'path':str(rel),'before':before,'after':sha(p)})
    put(A/'artifacts/working-integration-progress.json',{'changes':changes})
for n in changed:save(R/n,(C/n).read_bytes())
engines={}
for p in (R/'02_BACKEND/ENGINES').rglob('*.json'):
    n=str(p.relative_to(R));v=read(p);before=encoded(v);files=v.get('files',{})
    candidate=read(C/n) if (C/n).exists() else {'files':{}}
    baseline=read(R/b['manifest']['code_root']/n) if (R/b['manifest']['code_root']/n).exists() else {'files':{}}
    for name in set(files)&set(changed):files[name]=changed[name]
    for name in candidate.get('files',{}).keys()-baseline.get('files',{}).keys():files[name]=sha(R/name)
    if encoded(v)!=before:save(p,encoded(v));engines[n]=sha(p)
p=R/'00_SYSTEM/PIPELINE.json';v=read(p);candidate=read(C/'00_SYSTEM/PIPELINE.json')
for e in v['engines'].values():
    if e['manifest'] in engines:e['sha256']=engines[e['manifest']]
for e in v['workflows']['registered']:
    chosen=next(x for x in candidate['workflows']['registered'] if x['id']==e['id'])
    e['version']=chosen['version'];e['sha256']=sha(R/e['manifest'])
save(p,encoded(v));auth['rollback_pipeline']=bound(backup/'00_SYSTEM/PIPELINE.json')
put(A/'artifacts/working-integration.json',{'status':'PASS','changes':changes,
    'preserved_other_working_differences':[n for n,h in f['serving_files'].items() if sha(R/n)!=h],
    'served_candidate':f['code_root']})
put(A/'artifacts/main-authorization.json',auth);put(A/'artifacts/main-validation.json',validation)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),
     '--generation',str(R/read(D/'data-binding.json')['path']),'--release-id','workflow-adopted-evidence-20261015-r1',
     '--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Reviewed deltas integrated; qualified identical release prepared')
