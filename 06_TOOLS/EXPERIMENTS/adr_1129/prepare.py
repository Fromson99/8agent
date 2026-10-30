from pathlib import Path
import json,hashlib,sys,shutil
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1129-catalog-recovery-serving';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-1128-catalog-binding-native';H=Path(__file__).parent;D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');parent=R/f['code_root'];m=read(A/'실험/manifest.json');c=read(P/'artifacts/design/criteria.json')
c.update(frozen_at=datetime.now(timezone.utc).isoformat(),hypothesis='Complete durable catalogue receipt validation and verify new finite inputs, independent native public question, and exact serving inventory. Preserve source/ACL/hash/state and failed known cases.',primary=['New42matrix+6native source cases+4catalogue receipt tampering cases all pass','All350observed regressions pass','Independent public processing/controller question completes native HTTP with exact source/ACL/reference/wire checks; semantic limitations allowed and reported','Official432inventory exactly equals candidate except experiment transport;53changes explicitly integrated preserving MAIN107','After source qualification, officialMAIN and actual selected service verified before task completion'],quality_certified=False,new_holdout_is_engineering_only=True,known_question_in_sample_secondary=False)
put(D/'criteria.json',c)
m['in_sample']=False;m['decision_eligible']=True;m['lineage']['hypothesis_delta']=c['hypothesis'];m['design'].update(hypothesis=c['hypothesis'],primary_metric='New source/ID/page/recovery inputs and exact serving integration',success_criteria=c['primary'],failure_criteria='Protected invariant failure or failed required technical gate; legal correctness not certified.',criteria_frozen_before_run=True);m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
for a in m['design']['arms']:a.update(changes='Complete repository catalogue binding, same1128A-F product and MAIN107',controls='Source,model,scope,budgets unchanged; primary inputs new;350observed regressions separate')
m['runs'][0]['selection_rule']='All52prospective primary technical conditions plus350observed regressions';m['runs'].append({'id':'run-002','purpose':'holdout','parent_run_id':'run-001','arm_ids':['integrated'],'selection_rule':'One prospectively frozen independent public question after all contract gates; existing40/1024/1800budgets','status':'planned','artifact_path':'TODO','sha256':'PENDING'})
put(A/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
new=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('schema_preparation','stable_references','independent_read_recovery')]
C=ac.snapshot(A,'integrated-r1',[n for n in f['files'] if n not in new],experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001','run-002']);S=C/'snapshot'
for n,h in f['files'].items():assert sha(parent/n)==h;shutil.copyfile(parent/n,S/n)
for n in new:ac.register_file(C,n,upstream_state='absent')
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1128').glob('*.py'):
 if p.name in ('prepare.py','finish.py','finish_failed.py','stage.py','patch.py'):continue
 (H/p.name).write_text(p.read_text().replace(P.name,A.name).replace('adr_1128','adr_1129'))
for p in (P/'artifacts/design').glob('*.json'):
 if p.name in ('freeze.json','criteria.json','staging.json'):continue
 shutil.copyfile(p,D/p.name)
shutil.copyfile(D/'matrix.json',D/'observed-matrix.json')
(H/'test_observed_matrix.py').write_text((H/'test_fresh_matrix.py').read_text().replace('design/matrix.json','design/observed-matrix.json'))
shutil.copyfile(H/'test_native_qualification.py',H/'test_observed_native.py')
matrix={'references':[[n,d,o] for n in (6,13,24,33) for d in (3,7) for o in (0,1,2)],'pages':[[n,r] for n in (22,38,42,57,59,62,79,80,81) for r in (False,True)],'native_api':['normal','navigation_repair','independent_after_failure','independent_conflict_after_failure','final_repair','final_failed']};put(D/'matrix.json',matrix)
case={'id':'privacy-processing-controller-001','source':{'type':'prospectively-authored-public-question','legal_quality_holdout_certified':False},'request':{'API_TYPE':'rag','json':{'question':'개인정보 보호법 제2조에서 처리와 개인정보처리자는 각각 무엇을 뜻하나요? 해당 원문을 인용해 주세요.','document_ids':['ab58f0d6419c6868','491860cf4b5ef92d'],'public_question':True,'use_llm':True}}};put(D/'case.json',case)
p=H/'test_fresh_matrix.py';p.write_text(p.read_text().replace('qualification-doc-','serving-qualified-doc-').replace('독립검증자료-','서빙검증문서-').replace('새 검증 원문 ','서빙 신규 원문 ').replace('qualified-index','serving-qualified-index'))
p=H/'test_native_qualification.py';p.write_text(p.read_text().replace('원문재검증규정','공식심사규정').replace('이 신청에는 담당자의 사전 서면 확인이 필요하다.','이 심사는 책임자의 사전 서면 동의가 필요하다.'))
p=H/'check_integrated_bootstrap.py';t=p.read_text();a=t.index("files={'primary':");b=t.index('paths=[',a);t=t[:a]+"files={'primary':['test_fresh_matrix.py','test_native_qualification.py','test_catalogue_receipt.py'],\n'support':['test_preparation.py','test_stable_recovery_isolated.py','test_output_contract_local.py','test_runtime_binding.py','test_regression_matrix.py','test_native_integrated.py','test_conflict_diagnostics.py','test_review_ownership.py','test_complete_alternatives.py','test_final_diagnostics.py','test_final_shape.py','test_observed_matrix.py','test_observed_native.py','test_document_catalog.py'],\n'modes':[str(ROOT/'05_TESTS/CONTRACTS/test_genos_applied_mode.py')]}[mode]\n"+t[b:];p.write_text(t)
p=H/'live.py';p.write_text(p.read_text().replace("'in_sample':True","'in_sample':False"))
p=H/'audit_case.py';p.write_text(p.read_text().replace('privacy-definitions-001','privacy-processing-controller-001'))
m['dataset'].update(name='52prospective technical conditions and public processing/controller question',version='v1',frozen_source=str((D/'matrix.json').relative_to(R)),sha256=sha(D/'matrix.json'));m['llm_policy']['llm_calls']=[];put(A/'실험/manifest.json',m);print(S)
