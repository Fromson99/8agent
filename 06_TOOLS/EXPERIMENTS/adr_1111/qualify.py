from pathlib import Path
import json,hashlib,subprocess,re,xml.etree.ElementTree as ET
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1111-genos-mode-scope-qualification';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def outcomes(p):return {t.get('classname')+'::'+t.get('name'):('failed' if t.find('failure') is not None else 'error' if t.find('error') is not None else 'skipped' if t.find('skipped') is not None else 'passed') for t in ET.parse(p).iter('testcase')}
tests=outcomes(O/'tests.xml');reg=outcomes(O/'regression.xml');prior=outcomes(O/'regression-baseline.xml')
assert len(tests)==51 and set(tests.values())=={'passed'}
assert reg==prior, {k:(prior.get(k),v) for k,v in reg.items() if prior.get(k)!=v}
put(D/'regression-comparison.json',{'exact_outcomes_equal':True,'total':len(reg),'passed':sum(v=='passed' for v in reg.values()),'existing_failed':sorted(k for k,v in reg.items() if v!='passed'),'new_failures':[],'baseline':bind(O/'regression-baseline.xml'),'candidate':bind(O/'regression.xml')})
b=read(D/'baseline.json');f=read(D/'freeze.json');stage=read(D/'staging.json');S=R/stage['code_root']
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(S/n)==h for n,h in stage['files'].items())
put(D/'preview-auth.json',{'purpose':'integration_preview'});put(D/'preview-validation.json',{'structural_checks_passed':True,'basis':bind(O/'tests.xml')})
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(S),'--generation',b['manifest']['data_path'],'--release-id','genos-mode-preview-20261027-r1','--authorization',str(D/'preview-auth.json'),'--validation',str(D/'preview-validation.json'),'--integration-preview',str(D/'official-preview.json')]
with (D/'preview.log').open('w') as log:subprocess.run(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
draft=read(D/'official-preview.json');actual=dict(b['manifest']['files'])
for row in draft['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==stage['files'] and len(actual)==429 and len(draft['changes'])==38
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':draft['base_release_manifest_sha256'],'candidate':f['candidate'],'staged_files':actual,'excluded_candidate_paths':{}}
put(D/'release-rebase.json',rebase)
for row in draft['changes']:row['reason']='Explicit GENOS mode binding at input, ALL source routing, pre-validation source binding and session scope state' if row['path'].endswith('.py') else 'Recomputed engine dependency hashes for the seven exact tested source files; other MAIN106 configuration preserved'
draft.update(candidate=f['candidate'],rebase_receipt=bind(D/'release-rebase.json'));put(D/'integration.json',draft)
checks={'all51_ui_contracts':True,'actual_chat_service_scope':True,'session_internal_external_all_and_dedup':True,'compare_registered_workflow_and_identity':True,'all145_regression_outcomes_equal_main106':reg==prior,'no_new_regression':True,'official429_inventory_exact':True,'exact38_changes_frozen':True,'model_profile_and_data_unchanged':all(actual[n]==h for n,h in b['manifest']['files'].items() if n.startswith('00_SYSTEM/LEGAL_AGENT/') or n=='00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'active_main106_unchanged_before_promotion':True,'no_live_model_calls':True}
put(O/'result.json',{'strict_success':all(checks.values()),'checks':checks,'new_tests':len(tests),'regression_passed':sum(v=='passed' for v in reg.values()),'existing_regression_failures':sum(v!='passed' for v in reg.values()),'new_regression_failures':0,'new_model_calls':0,'quality_certified':False,'genos_field_verified':False,'selected_files':429,'changed_files':38,'scope':'Technical input/state/authorization contract audit; no legal quality or speed claim','failed_predecessors_preserved':['ADR1108','ADR1109']})
p=A/'실험/manifest.json';m=read(p);m['decision_eligible']=True;m['lineage']['hypothesis_delta']='Same1109product code; correct search-scope observation and verify all explicit UI modes through actual native chat/service; preserve model choice of final citations'
m['design']['release_rebase']=bind(D/'release-rebase.json');m['runs'][0].update(status='complete',artifact_path=str((O/'result.json').relative_to(R)),sha256=sha(O/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'immutable MAIN106;66pass79existing_failures'},'integrated':{'status':'complete','new_contracts_passed':51,'regression_passed':66,'existing_failures':79}},usage={'new_model_calls':0},latency={'performance_measured':False},error_taxonomy=['79 existing regression failures identical to MAIN106; old fixture/profile/display contracts retained'],main_wiring='promotion-candidate',quality_certified=False)
put(p,m)
meta=(A/'README.md').read_text().split('---',2)[1]
for key,value in [('status','Accepted'),('main_wiring','promotion-candidate'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+key+':.*$',key+': '+value,meta)
parts=[('결정 요약','신규51계약 통과. 기존145검사의66통과·79실패는 MAIN106과 항목별 동일, 신규 회귀0. 제품7파일·pin31파일, 총429서빙파일을 공식 준비 경로와 일치시켰다. 로컬 MAIN 승격 후보이며 현장 배포는 별도다.'),('문제와 변경 전 구조','화면의 applied_fields.mode가 우리 채팅 요청으로 전달되지 않았다. 전체 법령·내규·외규·대사를 기존 검색 및 대사 경로로 연결하고, 전체는 허용된 내규·외규·미분류 자료를 검색한다.'),('가설과 사전 판정 기준','criteria.json과 freeze.json에 조건·코드·검사 해시를 실행 전 고정했다. 입력·범위·권한·세션·대사·중복 요청·기존 호환 모두 통과하고 신규 회귀가 없어야 한다. 전체 검색 범위와 모델의 최종 인용 선택은 구분한다.'),('실험 설계','완료1092/serving과 MAIN106을 부모로 사용한다. 실패1108·1109는 informed_by 이력이며 부모로 쓰지 않는다.1109제품 코드와 동일한38파일을 새 격리 후보에 동결했다. 원문3개·합성 모델로 실제 /chat→service→API→scope를 검사했다.'),('데이터·모델·재현성','후보429파일을 실행 전후 대조하고 공식 prepare preview를 확인했다. 신규 실제 모델0회. 기존 데이터·모델·프로필·출력상한 없음·40/1024/1800예산 유지. 법령 정답 실험은 아니다.'),('결과','JSON/SSE 네 선택·별칭·잘못된 값·충돌·미선택 호환·실제 자료 범위·동일 대화 internal→external→ALL과 PLAN 이하 재실행·중복 재사용 및 변경409·대사 runtime 전달51검사 통과. 실제 권한에 없는 unknown은 세션 ALL에서도 배제된다.'),('사례별 오류 분석','1108은 KEEP replan이 UI 범위 결속 전에 거절되는 결함을 발견했다.1109에서 명령 검증 전에 명시 분류를 결속했다.1109 검사는 모든 검색 대상을 최종 인용해야 한다고 잘못 가정했고 권한 목록 순서도 고정했다.1111은 제품을 바꾸지 않고 실제 open 범위와 인용 부분집합을 별도로 확인했다. 기존79실패는 최신 선택을 생성하지 않는 구 대사 fixture, 변경된 표시·권한·스키마 기대값 등이 포함되며 모두 부모에서도 재현된다.'),('비용·지연·회수 규모','실제 모델0회, 합성 자료3개. 전체 데이터 회수율·법률 품질·사용자 응답시간은 측정하지 않았다. 한 무거운 프로세스씩 실행했고 주소공간4GiB로 제한했다.'),('해석','전체 법령은 현재 적재되고 허용된 모든 분류를 검색하는 설정이다. 실제 읽기·최종 인용은 질문과 모델의 선택에 따른다. 새로운 인터넷 법령 수집이나 권한 확대가 아니다.'),('한계와 일반화 가능 범위','망분리 GENOS의 actual applied_fields 전송·현장 리비전·Oracle 전체 조회는 미검증이다. 승호 integration의 applied_fields 계약과 로컬 모의 입력을 확인했다. 대사 엔진의 법률 품질을 이번 변경으로 새로 인증하지 않는다.'),('운영 결정·롤백 조건','사용자가 MAIN 반영을 지시했다. 공식 prepare/apply --confirm-main 후 선택 포인터와 실제 서비스 소비자를 확인한다. 원문·권한·상태·해시 중대 회귀 시 공식 rollback으로 MAIN106을 복구한다. 이전 이력과 다른 작업 변경을 보존한다.'),('재현 명령','06_TOOLS/EXPERIMENTS/adr_1111/run_tests.py, run_baseline.py, qualify.py. artifacts/design/freeze.json·staging.json·release-rebase.json과 run-001의 XML·로그가 정본이다. 완료 결과를 덮어쓰지 않는다.')]
(A/'README.md').write_text('---'+meta+'---\n\n# GENOS 조회 선택의 실제 검색 범위 검증\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n');(A/'실험/README.md').write_text('# 합성 입력·검색 범위 검사\n\n신규51통과. 기존145검사는 MAIN106과 같은66통과79실패. ../artifacts/run-001/result.json 및 XML을 참조한다. 새 모델0회.\n')
print('qualified',len(tests),'new contracts;',len(reg),'regression outcomes preserved;429files38changes')
