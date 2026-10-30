from common import *
import subprocess
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-final-answer-main116';b=read(DES/'baseline.json');s=read(DES/'staging-final.json');r=read(RUN/'result.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for field in ('product_files','pins'):
 for n,h in read(ART/'working-integration.json')[field].items():assert sha(ROOT/n)==h,n
q={'source':bind(ADR/'실험/manifest.json'),'readme':bind(ADR/'README.md'),'arm':'integrated','result':bind(RUN/'result.json'),'rebase':bind(DES/'release-rebase.json')}
put(O/'authorization.json',{'authorized_by':'user','authorization_text':'불필요한 일반 미확인 문구를 빼버리고 지금까지 한거 전체 메인에 반영해','prior_context':'User requested accumulated final-prompt and limitation correction in MAIN; known UNKNOWN and quality limitations retained','scope':'Working code and local selected MAIN integration; GENOS and new real model runs outside current scope','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(ART/'working-pipeline-integrated.json')})
put(O/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),'technical_conditions':130,'working_conditions':130,'product_files_changed':3,'external_model_calls':0,'quality_certified':False})
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(O/'authorization.json'),read(O/'validation.json'))
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/s['code_root']),'--generation',b['manifest']['data_path'],'--release-id','final-answer-20261029-r1','--authorization',str(O/'authorization.json'),'--validation',str(O/'validation.json')]
with (O/'prepare.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=ROOT/'08_DEPLOYMENT/RELEASES/final-answer-20261029-r1/release.json';assert read(manifest)['files']==s['files']
with (O/'apply.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Selected MAIN',read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'])
