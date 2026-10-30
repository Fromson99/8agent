from pathlib import Path
import json,hashlib,sys,shutil
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1126-stable-review-serving-qualification';ART=ADR/'artifacts';PARENT=ROOT/'04_EXPERIMENTS/ADR/ADR-1125-final-disposition-shape';OBS=ROOT/'04_EXPERIMENTS/ADR/ADR-1125-final-disposition-shape';HERE=Path(__file__).parent

def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation']==107
f=read(PARENT/'artifacts/design/freeze.json');observed=read(OBS/'artifacts/design/freeze.json');assert f['files']==observed['files']
matrix={'references':[[n,d,o] for n in (5,12,19,27) for d in (3,6) for o in (0,1,2)],'pages':[[n,r] for n in (17,20,21,39,40,41,58,60,61) for r in (False,True)],'native_api':['normal','navigation_repair','independent_after_failure','independent_conflict_after_failure','final_repair','final_failed']};put(ART/'design/matrix.json',matrix)
case={'id':'privacy-definitions-001','source':{'type':'prospectively-authored-public-question','legal_quality_holdout_certified':False},'request':{'API_TYPE':'rag','json':{'question':'개인정보 보호법 제2조에서 정한 개인정보와 가명처리의 정의를 각각 원문을 인용해 설명해 주세요.','document_ids':['ab58f0d6419c6868','491860cf4b5ef92d'],'public_question':True,'use_llm':True}}};put(ART/'design/case.json',case)
c={'frozen_at':datetime.now(timezone.utc).isoformat(),'hypothesis':'Exact completed1125 product preserves unseen finite source/ID/page/recovery inputs and independent public-question native execution, and matches official serving inventory. Technical qualification only.','primary':['All42new finite matrix conditions and6new synthetic-source native HTTP cases pass.','All296observed regression conditions pass on the same frozen code, including MAIN107 modes.','One independent public question completes native HTTP with exact source/ACL/stable reference checks and no runtime/hash/binding/wire implementation failure. Legally limited answer allowed and reported; no correctness certification.','Official prepare inventory432 exact; source19existing+3new/config and31pins explicitly integrated without unrelated overwrite.','Qualified MAIN pointer and actual selected service entry/HEALTH/mock provider wire checked before completion.'],'resources':{'max_rss_gib':4,'min_available_gib':3,'max_swap_gib':.5,'min_disk_gib':20,'heavy_processes':1},'quality_certified':False,'known1120_run_is_separate_observation':True,'model':{'model':'qwen/qwen3.8-27b','provider':'Parasail','reasoning':'none','max_output_tokens':None,'max_calls':40,'tools':1024,'seconds':1800,'fallback':False,'minimum_provider_start_interval_seconds':65},'performance_goal':'Whole-request nonLLM1s excluding glossary only remains unmet; no performance claim from paced functional model run.','rollback':'Exact MAIN107. Old/new journal runtime bindings are not reinterpreted.'};put(ART/'design/criteria.json',c)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=c['hypothesis'];m['design'].update(hypothesis=c['hypothesis'],primary_metric='Independent finite engineering invariants and exact serving integration',success_criteria=c['primary'],failure_criteria='Any protected source/ACL/hash/state/wire guard violation or failed qualification condition; no quality threshold retroactively imposed.',criteria_frozen_before_run=True);m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None);m['dataset'].update(name='Prospective48engineering conditions and independent public privacy definition question',version='v1',frozen_source=str((ART/'design/matrix.json').relative_to(ROOT)),sha256=sha(ART/'design/matrix.json'));m['in_sample']=False;m['decision_eligible']=True;m['llm_policy']['llm_calls']=[]
for a in m['design']['arms']:a.update(changes='Exact1125product; no new implementation change',controls='Same generation andMAIN107scope rules; fresh inputs and independent oracle; observed296tests separate')
m['runs'][0]['selection_rule']='All48prospective primary engineering conditions and296observed regressions; no sampling after results'
m['runs'].append({'id':'run-002','purpose':'holdout','parent_run_id':'run-001','arm_ids':['integrated'],'selection_rule':'One independent public privacy definition question;65sprovider interval inside1800s; only after contract gates','status':'planned','artifact_path':'TODO','sha256':'PENDING'});put(ADR/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P=ROOT/f['code_root'];new=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('schema_preparation','stable_references','independent_read_recovery')]
C=ac.snapshot(ADR,'integrated-r1',[n for n in f['files'] if n not in new],experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001','run-002']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(P/n)==h;shutil.copyfile(P/n,S/n)
for n in new:ac.register_file(C,n,upstream_state='absent')
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1125').glob('*.py'):
 if p.name in ('prepare.py','finish.py','finish_component.py','probe_final.py','probe_native_transport.py','patch.py'):continue
 t=p.read_text().replace('ADR-1125-final-disposition-shape',ADR.name).replace('adr_1125','adr_1126');(HERE/p.name).write_text(t)
for name in ('baseline.json','test-support.json','merge.json','observed-schema-fixture.json','final-probe-inputs.json'):shutil.copyfile(OBS/'artifacts/design'/name,ART/'design'/name)
shutil.copyfile(OBS/'artifacts/design/matrix.json',ART/'design/regression-matrix.json')
p=HERE/'test_regression_matrix.py';p.write_text((HERE/'test_fresh_matrix.py').read_text().replace('design/matrix.json','design/regression-matrix.json'))
p=HERE/'test_fresh_matrix.py';t=p.read_text().replace('fresh-doc-','qualification-doc-').replace('독립규정-','독립검증자료-').replace('조문 미리보기 ','새 검증 원문 ').replace('fresh-index','qualified-index').replace("'source-'+str(i)","'qualified-source-'+str(i)");p.write_text(t)
p=HERE/'test_native_qualification.py';p.write_text((HERE/'test_native_integrated.py').read_text().replace('원문검토검증규정','원문재검증규정').replace('이 확인 업무는 서면 승인 후 시행한다.','이 신청에는 담당자의 사전 서면 확인이 필요하다.'))
p=HERE/'check_integrated_bootstrap.py';t=p.read_text();a=t.index("files={'primary':");b=t.index("paths=[",a);t=t[:a]+"files={'primary':['test_fresh_matrix.py','test_native_qualification.py'],\n 'support':['test_preparation.py','test_stable_recovery_isolated.py','test_output_contract_local.py','test_runtime_binding.py','test_regression_matrix.py','test_native_integrated.py','test_conflict_diagnostics.py','test_review_ownership.py','test_complete_alternatives.py','test_final_diagnostics.py','test_final_shape.py'],\n 'modes':[str(ROOT/'05_TESTS/CONTRACTS/test_genos_applied_mode.py')]}[mode]\n"+t[b:];p.write_text(t)
# The independent question is the only new model input; its dataset declaration
# is frozen now, while the separate1120known-case observation is still running.
p=HERE/'live.py';t=p.read_text().replace("'in_sample':True","'in_sample':False");p.write_text(t)
# Bind the untouched never-executed prospective inputs to their original hashes.
U=ROOT/'04_EXPERIMENTS/ADR/ADR-1122-stable-review-qualification/artifacts/design'
assert read(U/'matrix.json')==read(ART/'design/matrix.json')
assert read(U/'case.json')==read(ART/'design/case.json')
put(ART/'design/prospective-input-origin.json',{n:{'path':str((U/n).relative_to(ROOT)),'sha256':sha(U/n)} for n in ('matrix.json','case.json')})
print(S)
