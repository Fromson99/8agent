from common import *
import subprocess
O=ROOT/'09_ARTIFACTS/AUDITS/20261028-source-contract-main113';b=read(DES/'baseline.json');s=read(DES/'staging-final.json');f=read(DES/'freeze.json');r=read(RUN/'result.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for n,h in read(ART/'working-integration.json')['product_files'].items():assert sha(ROOT/n)==h,n
q={'source':bind(ADR/'실험/manifest.json'),'readme':bind(ADR/'README.md'),'arm':'integrated','result':bind(RUN/'result.json'),'rebase':bind(DES/'release-rebase.json')}
put(O/'authorization.json',{'authorized_by':'user','authorization_text':'일단 지금까지 한거 메인에 반영해 가치가 있어보여','scope':'Cumulative source-goal, response/assessment recovery, routing and deadline; technical integration, known semantic failures retained','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(ART/'working-backup/00_SYSTEM/PIPELINE.json')})
put(O/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),'technical_conditions':r['technical_conditions'],'serving_conditions':r['same_serving_conditions'],'working_conditions':r['working_conditions'],'new_regression':0,'new_model_calls':0,'quality_certified':False,'genos_field_verified':False})
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(O/'authorization.json'),read(O/'validation.json'))
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/s['code_root']),'--generation',b['manifest']['data_path'],'--release-id','source-contract-20261028-r1','--authorization',str(O/'authorization.json'),'--validation',str(O/'validation.json')]
with (O/'prepare.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=ROOT/'08_DEPLOYMENT/RELEASES/source-contract-20261028-r1/release.json';assert read(manifest)['files']==s['files']
with (O/'apply.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Selected MAIN',read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'])
