from common import *
import subprocess
b=read(DES/'baseline.json');f=read(DES/'freeze.json');OUT.mkdir(parents=True,exist_ok=True)
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
with (OUT/'adr-final.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','validate','--path',str(ADR),'--final'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
q={'source':bind(ADR/'실험/manifest.json'),'readme':bind(ADR/'README.md'),'arm':'source-contract','result':bind(RUN/'result.json'),'rebase':bind(DES/'release-rebase.json')}
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'잘못된 판단을 왜 그대로 지지하는지 원인 찾아서 수정하고 다시 실험해봐. 없는 이유랑 목적을 채우는 문제도 같이 고쳐봐; 너무 하드코딩으로 바꾸진마; 앞선 누적 MAIN 반영 요청 유지','scope':'Integrate exact tested independent source analysis, interpretation/evidence separation, nullable recorded roles and no-base state request contract into local selected MAIN. Real experiments9 retained separately with storage failure; no claim of complete semantic success. No GENOS field deployment/Git/mail.','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(ART/'working-pipeline-integrated.json')})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),'technical_conditions':84,'regression_new_failures':0,'product_config_files_changed':4,'pin_files_changed':31,'external_model_calls':0,'quality_certified':False})
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(OUT/'authorization.json'),read(OUT/'validation.json'))
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/f['code_root']),'--generation',b['manifest']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')]
with (OUT/'prepare.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';assert read(manifest)['files']==f['files']
before={n:sha(ROOT/n) for n in f['files']}
with (OUT/'apply.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
after={n:sha(ROOT/n) for n in f['files']};assert before==after
put(OUT/'working-preservation.json',{'before':before,'after':after,'identical':True})
print('Selected MAIN',read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'])
