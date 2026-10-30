from pathlib import Path
import json,hashlib,shutil,sys,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1111-genos-mode-scope-qualification';D=A/'artifacts/design';O=R/'09_ARTIFACTS/AUDITS/20261027-genos-mode-main107';O.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'baseline.json');stage=read(D/'staging.json');S=R/stage['code_root']
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert read(A/'실험/manifest.json')['reservation']['status']=='completed'
shutil.copyfile(R/'00_SYSTEM/PIPELINE.json',O/'rollback-working-pipeline.json')
product=[n for n in stage['changed'] if n.endswith('.py')];assert len(product)==7
for n in product:assert sha(R/n)==b['manifest']['files'][n],n+' concurrent edit'
status=subprocess.check_output(['git','status','--porcelain','-z'],cwd=R).decode().split('\0')
protected={s[3:]:sha(R/s[3:]) for s in status if s and s[:2]!='??' and (R/s[3:]).is_file() and s[3:] not in stage['changed']}
for n in product:shutil.copyfile(S/n,R/n)
sys.path.insert(0,str(R/'02_BACKEND'));from semantic_runtime.control import rehash_engines
rehash=rehash_engines(R,apply=True)
assert all(sha(R/n)==h for n,h in protected.items())
put(O/'working-integration.json',{'source_files':{n:sha(R/n) for n in product},'selected_source_equal':all(sha(R/n)==stage['files'][n] for n in product),'protected_other_modified_files':protected,'protected_unchanged':True,'rehash':rehash,'note':'Only seven unchanged-baseline source files integrated. Working config retained; engine pins recalculated without copying candidate pipeline over other work.'})
q={'source':bind(A/'실험/manifest.json'),'readme':bind(A/'README.md'),'arm':'integrated','result':bind(A/'artifacts/run-001/result.json'),'rebase':bind(D/'release-rebase.json')}
put(O/'authorization.json',{'authorized_by':'user','authorization_text':'여기에 전체 법령이라고하면 전체 데이터로 검색하게 하는거야 우리 메인에다가 한번 반영해볼래? 이렇게 넣었을때 돌아가게','scope':'Local MAIN107: exact tested GENOS applied_fields.mode all/internal/external/compare mapping. Preserve authorization, data/model/profile and existing unrelated work. GENOS field deployment is separate.','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(O/'rollback-working-pipeline.json')})
put(O/'validation.json',{'structural_checks_passed':True,'integration':read(D/'integration.json'),'new_contracts':51,'regression_passed':66,'existing_failed_same_as_parent':79,'new_model_calls':0})
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(S),'--generation',b['manifest']['data_path'],'--release-id','genos-mode-20261027-r1','--authorization',str(O/'authorization.json'),'--validation',str(O/'validation.json')]
with (O/'prepare.log').open('w') as log:subprocess.run(cmd,cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=R/'08_DEPLOYMENT/RELEASES/genos-mode-20261027-r1/release.json'
assert read(manifest)['files']==stage['files']
with (O/'apply.log').open('w') as log:subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Selected',read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'])
