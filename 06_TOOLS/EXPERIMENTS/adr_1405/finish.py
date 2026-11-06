"""Seal implementation evidence and exact local MAIN selection."""
from common import *
import re
b=read(DES/'baseline.json');a=read(ART/'main/activation.json')
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p==a['active'] and p['generation']==150
r=read(ROOT/p['manifest_path']);f=read(DES/'candidate-repaired.json')
assert r['files']==f['selected_files'] and all(sha(ROOT/r['code_root']/n)==h for n,h in r['files'].items())
assert r['data_path']==b['release']['data_path'] and r['data_manifest_sha256']==b['release']['data_manifest_sha256']
assert read(ART/'main/main-entry.json')['passed'] and read(ART/'main/gold-entry.json')['passed']
comparison=read(ART/'regression-comparison.json');prepared=read(ART/'prepared-review/result.json')
integration=read(ART/'working-integration.json')
assert comparison['new_failures']==0 and prepared['failed']==0 and prepared['code_unchanged']
assert all(sha(ROOT/n)==f['selected_files'][n] for n in integration['changed'])
assert all(sha(ROOT/n)==h for n,h in integration['preserved_other_files'].items())
result={'status':'LOCAL_MAIN150_SELECTED','active':p,'serving_files':530,'changed_files':36,'product_modules':5,'dependent_pins':31,
 'new_contracts_passed':23,'related_initial_passed':179,'related_failed':53,'same_baseline_failures':53,'new_failures':0,
 'unique_passed_after_added_journal_tests':181,'prepared_contracts_passed':prepared['passed'],'prepared_failed':0,'prepared_is_subset_recheck':True,
 'actual_service_checks':a['main_checks'],'gold_code_binding_checks':a['gold_checks'],'native_SQL_plans_unchanged':640,
 'recorded_RP_menu':read(ART/'recorded-risk-menu.json'),'working_differences_from_release':integration['working_differences_from_release'],
 'new_external_model_calls':0,'new_Oracle_connections':0,'data_unchanged':True,'quality_certified':False,'deployment_basis':'USER_DIRECTED_CUTOVER','field_deployed':False,
 'rollback_release':b['pointer']['release_id'],'rollback_gold':str((ART/'main/gold-binding-before-exact.json').relative_to(ROOT)),
 'limits':['Live Qwen navigation and end-to-end legal answers require separately frozen follow-up; contracts do not certify semantic quality.',
 'Existing 53 fixture and lifecycle regression failures reproduce on MAIN149. No production guard weakened to pass them.',
 'Scoped tools apply to default minimal-input selection. Internal legacy action names remain in execution journals; model repair constraints use public names.',
 'Concurrent working UI edit preserved; serving530 deliberately retains evaluated MAIN149 UI bytes. No GENOS field or Oracle execution.'],
 'preserved_initial_failures':['First frozen core test20/21: fixture used old presentation. Test fixture corrected only.',
 'First freeze stopped on upstream UI drift; old candidate preserved and fresh candidate-r2 frozen before tests.']}
put(RUN/'result.json',result);put(ART/'final-verification.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_MAIN':149,'same_failures':53},'repaired':result},comparisons=[],judge_disagreements=0,
 usage={'external_model_calls':0,'Oracle_connections':0},latency={'not_measured':'No controlled live-model latency comparison'},
 error_taxonomy=['53 existing failures:34 profile fixtures,3 preparation-keyword fixtures,8 reference-bundle profile fixtures,8 existing goal/lifecycle expectations.',
 'Initial new test fixture mismatch preserved; corrected without changing frozen product code.'])
put(ADR/'실험/manifest.json',m)
summary='도구 선택·목표·메뉴·보완 계약 수정, 로컬 MAIN150 반영 완료.'
limits='실제 새 Qwen 호출과 완성 법률답변 검증은 별도 후속 시험이다. 선택 실행과 보완 계약을 검증했으며 모델 판단의 모든 모순이 해결됐다는 뜻은 아니다. GENOS 현장배포·Oracle연결·원문DB 변경·메일0.'
text=summary+'\n\n릴리스 coherent-navigation-20261105-r1 / 서빙530파일 / MAIN149 대비 제품5+pin31=36변경 / 실행SQL640 동일.\n신규23계약 통과(원래21+실제 SQLite 저널 재개2). 관련179통과·기존53실패 전부 MAIN149 동일, 신규2 포함181통과. 준비본 '+str(prepared['passed'])+' 통과(부분집합 재검사). 실제 root service '+str(a['main_checks'])+' / Gold 코드 연결 '+str(a['gold_checks'])+' 통과.\n\n1. 선택한 행동을 실행하고 새 원문 목표는 저장하여 다음 조사에서 이어 처리한다. FINISH/PENDING으로 미확보 목표를 숨기지 못한다.\n2. 확보 원문·미확보 목표 문서 중심으로 도구를 표시한다. 다른 문서 도구는 SHOW_DOCUMENT_TOOLS로 열며 모든 원래 경로는 유지한다.\n3. 표시 메뉴와 허용 스키마가 일치하며 숨긴 대상 직접 실행·오래된 상태·무진전 순환은 거절한다.\n4. 행동별 설명과 FINISH 불가 이유를 전달하고 보완 메시지는 READ/LOCATE/CATALOG_SEARCH 등 모델이 실제 선택하는 이름으로 맞춘다.\n5. 문서 전환은 원문 읽기로 세지 않으며 기존 최초+보완1회·예산·UNKNOWN 재전송 금지·재개 계약을 유지한다.\n\n저장된 RP 실패 입력 재구성: 도구 대상80→25, 원문/읽기 후보 동일,80경로 모두 재접근 가능. 새 모델 성공이나 처리속도 개선으로 계산하지 않는다.\n동시 작업 중인 genos_rag_chat.py 수정은 작업 트리에 그대로 보존했다. 선택 릴리스는 검사한149 UI를 유지한다.\n\n'+limits+'\n'
(ART/'수정과_메인반영_결과.txt').write_text(text)
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^main_wiring:.*$','main_wiring: user-directed-cutover',front)
sections=[('결정 요약',summary),('문제와 변경 전 구조','실제 Risk078에서 FOLLOW_CONNECTION 선택을 별도 원문 목표 계획이 SEARCH_STRUCTURE로 대체하고 동일성 검사가 거절했다. 같은 선택기에 도구 대상80개와 읽기 후보20개, 내부/공개 명칭이 다른 보완 메시지가 함께 주어졌다.'),
 ('가설과 사전 판정 기준',json.dumps(read(DES/'criteria.json'),ensure_ascii=False)),
 ('실험 설계','MAIN149 기준 격리530파일·제품5 수정·SQL640 동일·공식 pin 동결. 단계별 계약, 실제 SQLite 결정 저널, 실제 로컬 FastAPI 대역5개, 기존 실패의149 재현, 준비본 및 실제 선택 root/Gold 검증. 최초 실패와 병행 UI drift 보존.'),
 ('데이터·모델·재현성','기존 원문·팀 권한·프로필·매핑·온톨로지 설정 불변. 저장 RP 입력의 메뉴만 재구성하고 새 모델 호출은 하지 않았다. actual native API의 모델 응답은 대역이며 실모델 평가와 구분.'),
 ('결과',json.dumps(result,ensure_ascii=False,indent=2)),
 ('사례별 오류 분석','선택 행동은 그대로 검토·승인·실행하며 새 목표는 REQUIRED로 남겨 다음 preselect가 수행한다. 목표와 행동이 같으면 기존 영수증을 쓴다. 숨은 문서 도구는 명시 표시 전환으로 열고 source/ACL/branch/final 근거 검증은 기존 담당이 수행한다. 반복 전환·UNKNOWN·만료·예산 부족은 진행을 꾸며내지 않는다.'),
 ('비용·지연·회수 규모','모델0/Oracle0. 저장 입력 도구80→25는 표시 항목 수이며 회수율/정답률/실지연 향상 수치가 아니다. 전체80경로는 문서 전환으로 재접근 가능. 준비본은 검사 부분집합으로 중복 합산하지 않는다.'),
 ('해석','도구 개수 자체보다 선택한 행동과 별도 목표의 실행권 충돌을 우선 고쳤다. 표시 개수를 줄이면서 경로를 버리지 않았고 동일 모델 담당의 보완·기존 감시자·원문 확정 권한을 유지했다. source_targets 빈 배열 필드는 여전히 공통 계약에 존재하나 즉시 실행 명령으로 사용하지 않는다.'),
 ('한계와 일반화 가능 범위',limits+' 기존53실패는 이번 수정 전149 동일. 일반 온톨로지 의미검토·모든 질문의 연결 탐색 성공은 미인증.'),
 ('운영 결정·롤백 조건','사용자 “전체 구현하고 메인에 반영해”에 따라 USER_DIRECTED_CUTOVER·quality_certified=false로150 선택. 공식 rollback 및 main/gold-binding-before-exact.json으로149와 Gold 원본 바이트를 함께 복원할 수 있다. 병행 UI 작업은 덮어쓰지 않았다.'),
 ('재현 명령','bootstrap.py → 격리후보 수정 → freeze.py → check.py → baseline failure checks → prepare.py → prepared check.py → apply_working.py → activate.py → finish.py. 신규 영구검사05_TESTS/CONTRACTS/test_coherent_navigation_contract.py. 후보 source/MAIN530 해시·원복은 artifacts/design 및 main에 보관.')]
(ADR/'README.md').write_text('---'+front+'---\n\n# 도구 선택 계약 통합과 MAIN150\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 구현 및 메인 연결 검증\n\n실모델0. 구조·실제 API 대역·SQLite 저널·이전 실패 대조와 MAIN/Gold 연결은 artifacts/run-001/result.json 및 main/에 보존한다.\n')
audit=ROOT/'09_ARTIFACTS/AUDITS/20261105-coherent-navigation-main150';audit.mkdir(exist_ok=True)
(audit/'수정과_메인반영_결과.txt').write_text(text);put(audit/'최종검증.json',result)
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'}
paths.update(Path(__file__).parent.glob('*.py'));paths.add(ROOT/'05_TESTS/CONTRACTS/test_coherent_navigation_contract.py')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1405','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen navigation implementation, failures, baseline comparison and selected MAIN evidence','contains_raw_prompts_and_outputs':False} for p in sorted(paths)]})
print(text)
