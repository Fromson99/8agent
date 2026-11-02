from common import *
import subprocess,shutil,os
b=read(DES/'baseline.json');f=read(DES/'freeze.json');pf=read(DES/'port-freeze.json');OUT.mkdir(parents=True,exist_ok=True)
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items())
with (OUT/'adr-final.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','validate','--path',str(ADR),'--final'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
q={'source':bind(ADR/'실험/manifest.json'),'readme':bind(ADR/'README.md'),'arm':'integrated','result':bind(RUN/'result.json'),'rebase':bind(DES/'release-rebase.json')}
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'rag관련해서 1. 우리 에이전트 판단이 자꾸 이상하게 갈렸을 때 공백이 있어 확인해봐 2. 골드 수정본 통합은 해결해봐','scope':'Integrate verified judgment continuity/unknown-stop and Gold fixes into local selected MAIN and bind the separate Gold port to that same engine. Preserve data/model/default profile; no external model call or field GENOS/Git/mail.','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(ART/'working-pipeline-integrated.json')})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),'technical_conditions_passed':223,'existing_failed':4,'regression_new_failures':0,'product_files_changed':5,'pin_files_changed':31,'external_model_calls':0,'quality_certified':False,'gold_port_candidate':pf['candidate_revision'],'gold_source_vector':bind(ART/'gold-candidate/consumer-verification.json'),'gold_ontology':bind(ART/'gold-candidate/ontology-verification.json')})
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(OUT/'authorization.json'),read(OUT/'validation.json'))
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/f['code_root']),'--generation',b['manifest']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')]
with (OUT/'prepare.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';release=read(manifest);assert release['files']==f['files']
gold=dict(b['gold_binding']);gold.update(schema_version='selected-main-gold-port-v2',engine_root=release['code_root'],engine_files=release['files'],engine_release_id=RELEASE,engine_manifest_sha256=sha(manifest),data_path=release['data_path'],connector_files={Path(n).name:h for n,h in pf['files'].items()},inference_status='INTEGRATED_MAIN_TECHNICAL_PASS_REAL_INFERENCE_NOT_RETESTED',engine_candidate_revision=f['candidate_revision'],port_candidate_revision=pf['candidate_revision'],runtime_patches_active=False)
put(OUT/'gold-binding-prepared.json',gold)
rollback=OUT/'gold-before';rollback.mkdir()
for name in ('connect.py','binding.json','README.txt','MAPPING_GUIDE.txt','ONTOLOGY_ON_GUIDE.txt'):
 shutil.copy2(GOLD/name,rollback/name)
put(OUT/'gold-rollback.json',{'prior_engine_common_existed':False,'prior_main':b['active'],'prior_gold_files':b['gold_files'],'restore':['connect.py','binding.json'],'new_file':'engine_common.py','instructions':'MAIN123 official release is preserved. Restore prior Gold connect.py and binding.json together; remove maintained engine_common.py only if it matches this integration hash. Old runtime patches and mapping remain intact.'})
assert not (GOLD/'engine_common.py').exists()
with (OUT/'apply.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
# Activation is fail-closed for new processes until the maintained files and
# exact release binding are all present. Existing historical files stay intact.
for name in ('engine_common.py','connect.py'):
 src=ROOT/pf['code_root']/GOLD.relative_to(ROOT)/name;assert sha(src)==pf['files'][str(GOLD.relative_to(ROOT)/name)]
 tmp=GOLD/(name+'.main124-tmp');assert not tmp.exists();shutil.copy2(src,tmp);os.replace(tmp,GOLD/name)
tmp=GOLD/'binding.json.main124-tmp';assert not tmp.exists();shutil.copy2(OUT/'gold-binding-prepared.json',tmp);os.replace(tmp,GOLD/'binding.json')
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert all(sha(GOLD/Path(n).name)==h for n,h in pf['files'].items())
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items() if n not in {str((GOLD/'connect.py').relative_to(ROOT)),str((GOLD/'binding.json').relative_to(ROOT))})
put(OUT/'activation.json',{'active':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_exact':True,'gold_binding':bind(GOLD/'binding.json'),'gold_connector_exact':True,'mapping_settings_and_patches_preserved':True,'data_changed':False,'field_deployed':False})
print('Selected MAIN',read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'],'and same engine Gold binding')
