from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0838-comparison-judgment-qualification'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def ref(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==79 and p['release_id']=='llm-comparison-judgment-20261016-r1'
release=read(R/p['manifest_path']);f=read(A/'artifacts/design/freeze.json');active=read(A/'artifacts/active-consumer-v2.json');working=read(A/'artifacts/working-consumer-v2.json');integration=read(A/'artifacts/working-integration.json')
assert release['files']==f['serving_files'] and all(sha(R/release['code_root']/n)==h for n,h in release['files'].items())
assert active['status']=='PASS' and len(active['checks'])==13 and not active['entry']['app_injected']
assert working['status']=='PASS' and working['qualified_component_hashes_match'] and '53 passed' in (A/'artifacts/working-api.log').read_text()
assert all(sha(R/r['path'])==r['after'] for r in integration['changes'])
receipt={'status':'PASS','active_pointer':p,'release':ref(R/p['manifest_path']),'workflow_version':'1.5.2',
'working_changes':len(integration['changes']),'preserved_other_working_differences':len(integration['preserved_other_working_differences']),'selected_release_changes':len(read(A/'artifacts/design/integration.json')['changes']),
'working_api_passed':53,'retained_development_passed':53,'finite_census_passed':84,'active_service_checks':13,'active_service_entry':active['entry'],'data':active['actual_data'],
'frozen_candidate':ref(A/'artifacts/design/freeze.json'),'working_integration':ref(A/'artifacts/working-integration.json'),'working_tests':ref(A/'artifacts/working-api.log'),'active_consumer':ref(A/'artifacts/active-consumer-v2.json'),'qualification':ref(A/'artifacts/run-001/result.json'),
'profile_sha256':release['files']['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'],'search_selection_fingerprint':active['health']['body']['search_selection']['sha256'],'actual_service_release_binding':active['health']['body']['release'],
'known_model_observation':ref(R/'04_EXPERIMENTS/ADR/ADR-0837-comparison-advisory-items/artifacts/model/connected-19/result.json'),
'quality_certified':False,'genos_deployed':False,'git_commit_or_push_performed':False,
'limitations':['Native retrieval and internal document scope unchanged; no fresh complete live comparison performed.','The accepted known model response checks contract acceptance only, not legal correctness.','Global ADR graph retains9 preexisting errors, none from835-838; individual final validation passed.','Existing resident servers were not restarted; actual fresh local service entry bootstrap was checked.'],
'rollback':'Only when active79: .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main returns to78. Verify pointer and exact release first. Working backups in artifacts/working-before; preserve unrelated edits.'}
(A/'MAIN_RESULT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
text='대사 의미 판단 완화 — 로컬 MAIN79 반영\n2026-10-16 / workflow 1.5.2\n\n변경\n- 항목의 미확보 설명·문구 차이·상태값 조합을 의미 오류로 거절하지 않는다. LLM의 판단과 이유를 그대로 남기며 인용 미선택은 표시한다.\n- 새 표현이 다르다는 이유로 CONFLICT를 만들지 않는다. 이전 근거와 의견은 별도로 보존한다.\n- 직접 인용 관계·판본 메타데이터·완전성·수치 차원 전체 목록을 모두 채워야 비교하는 관문을 제거했다. 모델은 필요한 차원을 판단한다.\n- 모델 입력에서 조사 도구명·anchor ID·중복 충분성/의존 필드를 없앴다. 모델은 위치와 조사 내용을 고르고 시스템이 실행 도구와 근거 ID를 결속한다.\n- 실제 선택한 인용의 원문 일치·내외규 구분·문서 권한·코드/데이터/상태 해시·재개/중복/예산은 유지한다.\n\n반영·검증\n검증 후보와 선택 릴리스342파일이 동일하다. 릴리스 변경11파일(구현5+pin6), 작업 코드 통합37파일(구현5+manifest/pin32), 다른 작업 차이39개 보존. 후보·작업 회귀53개, 고정 기술 상태84개, 활성 서비스13개 통과. 실제 service.application이 앱 주입 없이 MAIN79를 선택한 binding을 MAIN_RESULT.json에 기록했다.\n\n알려진 수치 원문 묶음에 대해 새 Qwen 응답1건을 받았고 수정 재요청 없이 보존했다. 전체 대사를 다시 실행한 결과나 정답률 개선 수치가 아니다. 내규 검색 범위에 다른 팀 서식이 섞이는 문제는 남아 있고, 저장된 Risk 내규1문서에 유동성 산식은 없다. 이번에는 검색·데이터를 변경하지 않았다.\n\n정확한 선택: llm-comparison-judgment-20261016-r1 / generation79. 원문 세대는 latest-selection-20261015-r1/generation 유지. GENOS·Git main 병합·상주 서비스 재시작은 수행하지 않았다. ADR835~838 개별 final검사는 통과했고 전역 그래프의 기존 오류9개는 별도로 남아 있다.\n\n롤백: active79일 때만 stable rag_main_promotion.py rollback --confirm-main으로 이전78 복귀. 실제 포인터와 서비스 선택을 다시 확인한다. 작업 파일 백업은 ADR0838 artifacts/working-before에 있다.\n'
(A/'MAIN_RESULT.txt').write_text(text)
D=R/'09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance';(D/'LLM_JUDGMENT_MAIN79.txt').write_text(text+'\n정본: '+str((A/'MAIN_RESULT.json').relative_to(R))+'\n')
print('MAIN79 exact-code active-service receipt saved')
