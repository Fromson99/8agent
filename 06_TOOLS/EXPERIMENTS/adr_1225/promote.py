from common import *
import subprocess
b=read(DES/'baseline.json');f=read(DES/'freeze.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert (OUT/'adr-final.log').read_text().startswith('OK:')
q={'source':bind(ADR/'실험/manifest.json'),'readme':bind(ADR/'README.md'),'arm':'authoring-contract','result':bind(RUN/'result.json'),'rebase':bind(DES/'release-rebase.json')}
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'남은 상태·참조 불일치랑 입력 구간 누락도 수정하고, 정규화부터 누적까지 다시 실험해봐; 앞선 전체 MAIN 반영 요청 유지','scope':'Implement and verify cumulative normalization coverage/source mapping and accumulation reference consistency/compile repair and integrate the exact candidate into selected local MAIN. No new real models, GENOS field deployment, Git or mail.','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(ART/'working-pipeline-integrated.json')})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),'technical_conditions':106,'regression_new_failures':0,'product_config_files_changed':3,'pin_files_changed':31,'external_model_calls':0,'quality_certified':False})
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(OUT/'authorization.json'),read(OUT/'validation.json'))
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/f['code_root']),'--generation',b['manifest']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')]
with (OUT/'prepare.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';assert read(manifest)['files']==f['files']
before={n:sha(ROOT/n) for n in f['files']}
with (OUT/'apply.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
after={n:sha(ROOT/n) for n in f['files']}
put(OUT/'working-preservation.json',{'before':before,'after':after,'identical':before==after});assert before==after
print('Selected MAIN',read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'])
