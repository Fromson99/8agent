"""Prospective packaging audit of Accepted1090; no product changes or new scoring."""
from pathlib import Path
import json,hashlib,subprocess,re
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1092-compact-serving-inventory';D=A/'artifacts/design';O=R/'09_ARTIFACTS/AUDITS/20261027-compact-main106'
P=R/'04_EXPERIMENTS/ADR/ADR-1090-compact-main-valid-oracle'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
f=read(P/'artifacts/design/freeze.json');b=read(P/'artifacts/design/baseline.json');excluded='02_BACKEND/lawrag/research/experiment_client.py'
criteria={'frozen_at':datetime.now(timezone.utc).isoformat(),'scope':'Release packaging metadata audit; no changed product or new model/prompt effect evaluation.',
 'parent_qualified':bound(P/'실험/manifest.json'),'parent_result':bound(P/'artifacts/run-001/result.json'),'parent_support':bound(P/'artifacts/secondary/contracts.xml'),
 'expected_serving_count':429,'expected_excluded':[excluded],'success':['Official prepare preview inventory must exactly equal frozen1090inventory except single research-only ExperimentClient file','Every serving byte and engine dependency must match qualified parent, no product edit or dropped engine pin','Parent272new engineering conditions and127observed regression results remain unchanged; retain failed1089 and failed430file prepare','Active MAIN105 pointer/data unchanged; no network/model call'],'failure':'Any mismatch blocks promotion; cannot adjust expected list after observation.',
 'new_model_calls':0,'quality_certified':False}
put(D/'criteria.json',criteria)
put(D/'preview-authorization.json',{'purpose':'integration_preview'})
put(D/'preview-validation.json',{'structural_checks_passed':True,'basis':criteria['parent_result']})
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',f['code_root'],'--generation',b['manifest']['data_path'],'--release-id','compact-serving-preview-20261027-r1','--authorization',str(D/'preview-authorization.json'),'--validation',str(D/'preview-validation.json'),'--integration-preview',str(D/'actual-preview.json')]
with (D/'preview.log').open('w') as log:subprocess.run(cmd,cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
draft=read(D/'actual-preview.json');staged=dict(b['manifest']['files'])
for row in draft['changes']:
 if row['after'] is None:staged.pop(row['path'])
 else:staged[row['path']]=row['after']
expected={n:h for n,h in f['files'].items() if n!=excluded};assert staged==expected and len(staged)==429
code=R/f['code_root'];assert all(sha(code/n)==h for n,h in staged.items())
pins=set();config=read(code/'00_SYSTEM/PIPELINE.json')
for entry in config['engines'].values():
 engine=read(code/entry['manifest']);pins.update(engine['files']);assert all(staged.get(n)==h for n,h in engine['files'].items())
assert excluded not in pins
parent=read(P/'실험/manifest.json');result=read(P/'artifacts/run-001/result.json')
assert parent['reservation']['status']=='completed' and parent['results']['status']=='complete' and parent['decision_eligible'] and not parent['in_sample']
assert result['strict_success'] and all(result['checks'].values())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':draft['base_release_manifest_sha256'],'candidate':f['candidate'],'staged_files':staged,'excluded_candidate_paths':{excluded:'Research runner transport only; official serving pack excludes this unpinned file; native local_gemma transport remains included and unchanged.'}}
put(D/'release-rebase.json',rebase)
prior=read(P/'artifacts/design/integration.json');reasons={x['path']:x['reason'] for x in prior['changes']}
for row in draft['changes']:row['reason']=reasons[row['path']]
draft.update(candidate=f['candidate'],rebase_receipt=bound(D/'release-rebase.json'));put(D/'integration.json',draft)
put(A/'artifacts/run-001/result.json',{'strict_success':True,'checks':{'parent_qualified':True,'official_inventory_exact':True,'all429bytes_match_parent':True,'all_engine_dependencies_preserved':True,'only_unpinned_research_client_excluded':True,'main105_unchanged':True,'no_new_product_code':True},'selected_files':429,'changed_from_main105':len(draft['changes']),'inherited_primary_conditions':272,'inherited_observed_regressions':127,'new_product_model_calls':0,'quality_certified':False,'scope':'Packaging eligibility of already qualified product; not a new legal holdout','parent':criteria['parent_qualified'],'criteria':bound(D/'criteria.json')})
m=read(A/'실험/manifest.json');m['decision_eligible']=True;m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Exact official429file package and preserved qualified dependency hashes',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,release_rebase=bound(D/'release-rebase.json'))
m['design']['code_isolation'].update(mode='not_applicable',reason='No new product implementation, prompt, data or retrieval candidate. Metadata-only packaging audit of exact completed1090candidate; reuse immutable candidate via release-rebase receipt.')
for arm in m['design']['arms']:arm.update(changes='Qualified1090code unchanged; fixed expected serving inventory' if arm['id']=='baseline' else 'Only release metadata records official pack omission of unpinned research file',controls='No new product run or output rescoring; inherited272primary and127support explicitly labeled')
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['serving'],'status':'complete','selection_rule':'All429official serving files and every configured engine pin, fixed excluded file before preview','artifact_path':str((A/'artifacts/run-001/result.json').relative_to(R)),'sha256':sha(A/'artifacts/run-001/result.json'),'success_criteria_met':True}]
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='Official release file inventory',version='v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=False,reference_version_checked=False)
reason='No retrieval or answer generation; metadata-only package audit of qualified parent.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'Qualified parent fixed inventory'},'serving':{'status':'complete','selected_files':429,'changed_files':65}},comparisons=[],usage={'new_model_calls':0},latency={'performance_measured':False},error_taxonomy=[],main_wiring='promotion-candidate',quality_certified=False)
put(A/'실험/manifest.json',m)
meta=(A/'README.md').read_text().split('---',2)[1]
for key,value in [('status','Accepted'),('main_wiring','promotion-candidate'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+key+':.*$',key+': '+value,meta)
parts=[('결정 요약','Accepted1090의 제품 코드를 바꾸지 않고 공식 prepare의429서빙 파일을 결속했다. MAIN105대비65변경이다. 모델 입력 축소·후보20개·SQL배치와 기존 판단/구조 기능을 포함한다. 로컬 MAIN승격 후보이며 활성화는 별도 receipt다.'),('문제와 변경 전 구조','1090은430후보 파일이 모두 서빙된다고 잘못 가정해 실제 prepare에서 연구 전용 experiment_client.py 하나의 차이로 거절됐다. 그 실패로그와1090기록은 보존한다. 제품 검증272조건·보조127검사의 결과를 변경하지 않는다.'),('가설과 사전 판정 기준','criteria.json에 원래 동결 후보에서 연구용1파일만 제외한429파일을 기대값으로 먼저 정했다. 공식 preview가 정확히 일치하고 모든 엔진 pin과 활성 데이터·포인터가 유지되어야 한다. 이 감사로 법률 품질을 인증하지 않는다.'),('실험 설계','새 제품 실험·모델 호출·재채점이 없는 메타데이터 감사다. 정확한 완료1090/qualified를 부모로 사용하며 원래 연구후보의430파일 해시를 보존한다. 서빙429파일과 제외1파일의 이유를 evaluated-release-rebase-v1에 기록한다.'),('데이터·모델·재현성','공식 stable runner의 prepare --integration-preview를 사용했다. 새 모델0회, 실제 법률 데이터 질의0회. 같은 데이터 manifest·코드·프로필·검색·40호출/1024도구/1800초 예산·출력상한 없음을 유지한다.'),('결과','공식 inventory429개, 변경65개, 엔진pin 전부 일치. 원문·권한·상태 보호 코드의 제외는0이다. 신규272기계조건 및127보조검사는1090에서 상속한 근거이며 이번에 새로 수행했다고 하지 않는다.'),('사례별 오류 분석','1089의 fixture 기대값 오류와1090의 포장 목록 오류를 보존했다. 1086의 실제 질문은 모델이 새 원문의 판단에 다른 조문의 J번호를 중복 사용해 보완1회 후 제한 답변이었다. 해당 판단 실패는 이번 메타데이터 감사에서 수정하거나 법률 정답으로 바꾸지 않았다.'),('비용·지연·회수 규모','신규 모델0회이며 속도·회수율 비교를 하지 않았다.1086의 잔여49.973초 중 준비18.054초·후속화면8.988초·함수별 미계측 잔여22.930초는 별도 읽기 전용 진단이다.'),('해석','기술 검증된 제품과 실제 선택할 파일 사이의 차이를 명시하는 배포 무결성 감사다. 연구용 외부 실험 클라이언트를 로컬 서비스 코드로 오인하지 않는다. 로컬 native transport는 원래 포함된 local_gemma를 쓴다.'),('한계와 일반화 가능 범위','법률 품질·GENOS 현장·Oracle 실환경·새 온톨로지 실험의 통과 근거가 아니다. 판단 ID 오류와 첫화면32초 등의 병목은 남아 있다. 기계 검증과 실제 의미 판단을 구분한다.'),('운영 결정·롤백 조건','사용자가 MAIN 반영을 명시했다. 공식 prepare/apply --confirm-main과 실제 service HEALTH/선택 프로필/모의 HTTP를 확인한다. 심각한 원문·권한·hash 회귀 시 공식 rollback으로MAIN105의 코드·데이터를 복원한다. Git push/GENOS 배포는 하지 않는다.'),('재현 명령','06_TOOLS/EXPERIMENTS/adr_1092/qualify.py와 design/criteria.json·actual-preview.json에 명령과 입력이 있다. 완료 결과는 덮어쓰지 않는다. stable adr_structure validate --final 및 graph를 사용한다.')]
(A/'README.md').write_text('---'+meta+'---\n\n# ADR1092 검증 제품의 실제 서빙 목록\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 서빙 목록 감사\n\n질문별 법률 평가 없음. 제품 코드는1090동결본 그대로이며 공식429서빙파일 전체를 대조한다. 신규 모델0회.\n')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']+[Path(__file__).resolve()]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1092','created_at':m['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),'files':[dict(bound(p),bytes=p.stat().st_size,description='Qualified product packaging metadata audit',contains_raw_prompts_and_outputs=False) for p in paths]})
print('Official429file serving inventory qualified;65changes; no product edits; MAIN105 unchanged')
