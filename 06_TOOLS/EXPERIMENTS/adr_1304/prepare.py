"""Prospective continuation for three cells never dispatched by ADR1303."""
from pathlib import Path
import sys,json,shutil,hashlib
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1303-main135-nearai-answer-probe';ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1304-main135-nearai-remaining-cells';ART=ADR/'artifacts';DES=ART/'design'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert read(OLD/'실험/manifest.json')['reservation']['status']=='completed'
for name in ('common.py','live.py','resource_guard.py','pinned_imports.py','authorization.py','audit.py','ledger.py','run_all.py','freeze.py','archive_runtime.py','finalize.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1303'/name).read_text().replace('ADR-1303-main135-nearai-answer-probe','ADR-1304-main135-nearai-remaining-cells').replace('adr_1303','adr_1304').replace('adr1303','adr1304').replace('ADR1303','ADR1304').replace('ADR-1303','ADR-1304')
 if name=='run_all.py':
  s=s.replace("('ontology-365','baseline'),",'')
  s=s.replace("'reason':'prior unknown physical outcome'","'reason':read(ART/'STOP_EXTERNAL.json')['reason']")
  s=s.replace("if p.returncode or (result.get('http_status',0)>=500 and not result.get('unknown')):","if p.returncode:")
 if name=='ledger.py':s=s.replace("for case in read(DES/'cases.json'):","for case in read(DES/'cases.json'):\n  if arm not in case['arms']:continue")
 if name=='finalize.py':
  s=s.replace("'planned':2,","'planned':sum(arm in c['arms'] for c in read(DES/'cases.json')),")
  s=s.replace("'not_run':2-len(ar)","'not_run':sum(arm in c['arms'] for c in read(DES/'cases.json'))-len(ar)")
  s=s.replace('complete==4','complete==3').replace("'planned_cells':4","'planned_cells':3")
  s=s.replace("('ontology-365','baseline'),",'')
  s=s.replace('{complete}/4건(실행 {attempted}/4)','{complete}/3건(실행 {attempted}/3)')
  s=s.replace('["complete_correct"]}/2, 온톨로지ON','["complete_correct"]}/1, 온톨로지ON')
  s=s.replace('상법365 OFF→ON,369 ON→OFF 각1회.','첫365OFF는 ADR1303의6호출/Oracle500 실패로 보존. 이번에는 미실행365ON,369ON,369OFF만 각1회.')
  s=s.replace('UNKNOWN/자원/실행기/5xx 뒤 새셀 중단.','UNKNOWN/자원/실행기실패 뒤 새셀 중단. 확정 API/SQL 실패는 보존 후 다른 미실행셀을 새프로세스로 실행.')
  s=s.replace('Known2 questions,4 cells','Known2 questions,3 previously unexecuted cells')
  s=s.replace('20261103-main135-nearai','20261103-main135-nearai-remaining')
  s=s.replace('두 질문·네 셀','두 질문·추가 세 셀').replace('4셀순차실행','미실행3셀순차실행')
  s=s.replace('준비 단계의 부모기록 경로·불변요약 writer·모의 import·질문 scaffold 형식 오류는 모두 실제모델0 상태에서 보존/정정했다.','부모1303의 준비오류 및 첫365OFF Oracle500 실패는 원본보존. 이번엔 검증된 실행기와 같은 제품을 사용하고 미실행3셀만 별도로 동결했다.')
 (T/name).write_text(s)
sys.path.insert(0,str(T));from common import put
DES.mkdir(exist_ok=False)
for p in (OLD/'artifacts/design').glob('*.json'):
 if p.name not in ('candidate.json','freeze.json','criteria.json','cases.json'):shutil.copyfile(p,DES/p.name)
cases=read(OLD/'artifacts/design/cases.json');cases[0]['arms']=['ontology-on'];put(DES/'cases.json',cases)
criteria=read(OLD/'artifacts/design/criteria.json');criteria.update(primary_metric='Complete supported answers /3 previously unexecuted cells; alongside immutable parent first-cell failure, no retries or score exclusions.',order=['ontology-365/ontology-on','ontology-369/ontology-on','ontology-369/baseline'],continuation='Parent stopped all new cells after known SQL/API500. Read-only diagnosis found all6provider replies known HTTP200, no UNKNOWN or resource failure. Run only previously unexecuted independent cells, fresh process; preserve first failure in all-task accounting. Product and reference criteria unchanged.')
criteria['success'][0]=criteria['success'][0].replace('All 4 cells','All 3 remaining cells')
criteria['failure'][1]='UNKNOWN, resource stop or runner failure stops all remaining dispatch. A completed API error with known provider outcomes is preserved and the next distinct predeclared cell may run; no cell retry.'
put(DES/'criteria.json',criteria)
for folder in ('transport','gold-connector'):shutil.copytree(OLD/'artifacts'/folder,ART/folder)
put(DES/'inherited-admission.json',{'parent':str(OLD.relative_to(ROOT)),'observer':{'path':str((OLD/'artifacts/observer-selfcheck/result.json').relative_to(ROOT)),'sha256':sha(OLD/'artifacts/observer-selfcheck/result.json')},'routing':{'path':str((OLD/'artifacts/routing-selfcheck/result.json').relative_to(ROOT)),'sha256':sha(OLD/'artifacts/routing-selfcheck/result.json')},'native_grant_replay':{'path':str((OLD/'artifacts/replay/ontology-365-baseline/result.json').relative_to(ROOT)),'sha256':sha(OLD/'artifacts/replay/ontology-365-baseline/result.json')},'same_product516':True,'admission_tests_network0':True})
m=read(ADR/'실험/manifest.json');old=read(OLD/'실험/manifest.json')
for k in ('design','llm_policy','dataset','retrieval_accounting'):m[k]=old[k]
m['design'].update(primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0]['derived_from']=['ADR-1303-experiment-v1/baseline'];m['design']['code_isolation']['candidates']=[]
m['lineage']['hypothesis_delta']='Only remaining3cells on unchangedMAIN135/NearAI; known individual SQL/API errors do not cancel distinct cases; first failed cell kept, no rerun.'
m['llm_policy']['provider_override'].update(path=str((DES/'nearai-only.json').relative_to(ROOT)),sha256=sha(DES/'nearai-only.json'))
m['dataset'].update(frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),version='20261103-remaining3-v1')
m['runs'][0].update(arm_ids=['baseline','ontology-on'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)),selection_rule=criteria['continuation'])
for q in m['questions']:
 p=next((OLD/'실험').glob('*'+q['case_id']+'.md'));s=p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\nNot dispatched yet; new3cell design frozen.\n';(ADR/'실험'/q['file']).write_text(s)
put(ADR/'실험/manifest.json',m)
release=read(DES/'baseline.json')['release'];code=ROOT/release['code_root'];assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation']==135
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=[str((code/n).relative_to(ROOT)) for n in release['files']]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py']
candidate=ac.snapshot(ADR,'selected-main135',paths,experiment_id=m['experiment_id'],arm_id='ontology-on',run_ids=['run-001']);ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];snap=candidate/'revisions'/rev['revision_id']/'snapshot'
put(DES/'candidate.json',{'code_root':str((snap/release['code_root']).relative_to(ROOT)),'snapshot_root':str(snap.relative_to(ROOT)),'pin':{'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']},'selected_files':release['files']})
print('Prepared3 unexecuted cells; same MAIN135516/NearAI; initial failure preserved')
