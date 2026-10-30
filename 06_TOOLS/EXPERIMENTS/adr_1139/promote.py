from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1139-ontology-framework-local-http';D=A/'artifacts/design';O=R/'09_ARTIFACTS/AUDITS/20261027-ontology-framework-main108';O.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'baseline.json');stage=read(D/'staging.json');S=R/stage['code_root'];changed=stage['changed'];assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert read(A/'실험/manifest.json')['reservation']['status']=='completed'
# Every changed working source/config must still match its pre-integration bytes.
for n in changed:
 expected=b['working_files'].get(n)
 assert (sha(R/n) if (R/n).is_file() else None)==expected,n+' concurrent edit'
shutil.copyfile(R/'00_SYSTEM/PIPELINE.json',O/'rollback-working-pipeline.json')
q={'source':bind(A/'실험/manifest.json'),'readme':bind(A/'README.md'),'arm':'integrated','result':bind(A/'artifacts/run-001/result.json'),'rebase':bind(D/'release-rebase.json')}
put(O/'authorization.json',{'authorized_by':'user','authorization_text':'오케이 이거 메인에 반영해봐 데이터는 말고 전반적인 온톨로지 틀이거를 온톨로지는 on/off가 가능해야해','scope':'Framework only, no ontology data; default OFF, explicit operator ON/OFF, empty-data ordinary RAG. Local MAIN selection and service check. No GENOS deployment, no commit/push.','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(O/'rollback-working-pipeline.json')})
r=read(A/'artifacts/run-001/result.json');put(O/'validation.json',{'structural_checks_passed':True,'integration':read(D/'integration.json'),'technical_contracts':216,'regression_passed':r['regression_passed'],'existing_failed_same_as_parent':r['existing_regression_failures'],'new_model_calls':0,'quality_certified':False})
# Prepare before writing the working entry point, so official rollback captures MAIN107 service bytes.
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(S),'--generation',b['manifest']['data_path'],'--release-id','ontology-framework-20261027-r1','--authorization',str(O/'authorization.json'),'--validation',str(O/'validation.json')]
with (O/'prepare.log').open('w') as log:subprocess.run(cmd,cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=R/'08_DEPLOYMENT/RELEASES/ontology-framework-20261027-r1/release.json';assert read(manifest)['files']==stage['files']
assert sha(manifest.parent/'rollback/service.py')==b['manifest']['files']['service.py']
status=subprocess.check_output(['git','status','--porcelain','-z'],cwd=R).decode().split('\0')
protected={s[3:]:sha(R/s[3:]) for s in status if s and s[:2]!='??' and (R/s[3:]).is_file() and s[3:] not in changed}
for n in changed:
 expected=b['working_files'].get(n);assert (sha(R/n) if (R/n).is_file() else None)==expected,n+' concurrent edit'
 (R/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(S/n,R/n)
assert all(sha(R/n)==h for n,h in protected.items())
assert all(sha(R/n)==stage['files'][n] for n in changed)
put(O/'working-integration.json',{'source_files':{n:sha(R/n) for n in changed},'changed_count':len(changed),'selected_source_equal':True,'protected_other_modified_files':protected,'protected_unchanged':True,'no_data_modified':True,'strategy':'Selective changed files only; all preconditions checked against captured working hashes. No snapshot overwrite. Prepared rollback before entry-point edit.'})
with (O/'apply.log').open('w') as log:subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Selected MAIN',read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'])
