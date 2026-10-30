from common import *
import shutil,subprocess,sys
O=ROOT/'09_ARTIFACTS/AUDITS/20261028-ontology-workflow-main';O.mkdir(parents=True,exist_ok=True)
b=read(DES/'baseline.json');stage=read(DES/'staging.json');f=read(DES/'freeze.json');source=ROOT/f['code_root'];staged=ROOT/stage['code_root']
changed=stage['changed'];operator=[n for n in f['files'] if n.startswith(('03_FRONTEND/APPS/legal-knowledge-streamlit/','08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1/')) or n=='06_TOOLS/pipeline.py']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert read(O/'execution-coordination.json')['safe_to_activate']
assert read(ADR/'실험/manifest.json')['reservation']['status']=='completed'
for n in [*changed,*operator]:
 expected=b['working_files'].get(n)
 assert (sha(ROOT/n) if (ROOT/n).is_file() else None)==expected,n+' concurrent edit'
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
shutil.copyfile(ROOT/'00_SYSTEM/PIPELINE.json',O/'rollback-working-pipeline.json')
q={'source':bind(ADR/'실험/manifest.json'),'readme':bind(ADR/'README.md'),'arm':'connected','result':bind(ART/'run-001/result.json'),'rebase':bind(DES/'release-rebase.json')}
put(O/'authorization.json',{'authorized_by':'user','authorization_text':'그럼 빠진 스키마부터 고치고 온톨로지 생성→화면 승인→DB 적재→RAG 사용까지 연결해봐. 기존 화면 활용하고 테이블 설계랑 문서도 최신 MVP에 맞춰 반영해줘. 온톨로지 on/off는 유지하고','prior_authorization':'이 선택 개선도 최신 메인에 반영해봐 온톨로지 on/off는 유지하고 데이터는 넣지 말고','scope':'Latest MAIN110 plus verified workflow framework/schema only; same data,defaultOFF. Working UI/CLI/Dataiku delivery also integrated. No field deploy or ontology data.','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(O/'rollback-working-pipeline.json'),'execution_coordination':bind(O/'execution-coordination.json')})
put(O/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),'technical_conditions':254,'new_model_calls':0,'quality_certified':False,'default_off':True,'data_not_included':True,'actual_local_oracle':True,'field_deployment':False})
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(O/'authorization.json'),read(O/'validation.json'))
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(staged),'--generation',b['manifest']['data_path'],'--release-id','ontology-workflow-20261028-r1','--authorization',str(O/'authorization.json'),'--validation',str(O/'validation.json')]
with (O/'prepare.log').open('w') as log:subprocess.run(cmd,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=ROOT/'08_DEPLOYMENT/RELEASES/ontology-workflow-20261028-r1/release.json';assert read(manifest)['files']==stage['files']
status=subprocess.check_output(['git','status','--porcelain','-z'],cwd=ROOT).decode().split('\0')
protected={v[3:]:sha(ROOT/v[3:]) for v in status if v and v[:2]!='??' and (ROOT/v[3:]).is_file() and v[3:] not in [*changed,*operator]}
for n in [*changed,*operator]:
 expected=b['working_files'].get(n);assert (sha(ROOT/n) if (ROOT/n).is_file() else None)==expected,n+' concurrent edit'
 dest=ROOT/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,dest)
assert all(sha(ROOT/n)==h for n,h in protected.items())
put(O/'working-integration.json',{'serving_changed':{n:sha(ROOT/n) for n in changed},'operator_files':{n:sha(ROOT/n) for n in operator},'protected_other_modified_files':protected,'protected_unchanged':True,'data_modified':False,'strategy':'Precondition hashes then changed files only; prior user edits preserved.'})
with (O/'apply.log').open('w') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Selected MAIN',read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'])
