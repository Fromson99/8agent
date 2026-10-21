from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance';Q=R/'04_EXPERIMENTS/ADR/ADR-0830-comparison-main-confirmation';L=R/'04_EXPERIMENTS/ADR/ADR-0827-comparison-resume-live-check'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(Q/'artifacts/design/freeze.json');v=read(Q/'artifacts/run-001/result.json');live=read(L/'artifacts/run-001/result.json');replay=read(Q/'artifacts/replay-result.json')
active=read(Q/'artifacts/active-consumer-v2.json');working=read(Q/'artifacts/working-consumer-v2.json');pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path'])
assert v['strict_success'] and active['status']==working['status']=='PASS' and not active['entry']['app_injected']
assert pointer['release_id']=='comparison-task-guidance-20261016-r1' and release['files']==f['serving_files']
assert '58 passed' in (Q/'artifacts/working-api.log').read_text()
receipts=[read(R/('04_EXPERIMENTS/ADR/'+name+'/artifacts/working-integration.json')) for name in ('ADR-0823-comparison-partial-qualification','ADR-0826-comparison-resume-qualification','ADR-0830-comparison-main-confirmation')]
paths=sorted({r['path'] for receipt in receipts for r in receipt['changes']});implementation=[n for n in paths if n!='00_SYSTEM/PIPELINE.json' and not n.startswith('02_BACKEND/ENGINES/')]
assert all(sha(R/n)==f['serving_files'][n] for n in implementation)
binding={'workflow_version':'1.4.2','qualified_code_root':f['code_root'],'selected_release':pointer,'release_manifest_sha256':sha(R/pointer['manifest_path']),'serving_file_count':len(f['serving_files']),'serving_files':f['serving_files'],'working_implementation_files':{n:sha(R/n) for n in implementation},'integrated_file_count':len(paths),'implementation_file_count':len(implementation),'candidate_equals_selected_release':True,'working_service':working['entry'],'active_service':active['entry'],'data':active['actual_data'],'main_profile_sha256':sha(R/release['code_root']/'00_SYSTEM/PIPELINE.json'),'working_profile_sha256':sha(R/'00_SYSTEM/PIPELINE.json'),'active_health':active['health'],'qualification_result':str((Q/'artifacts/run-001/result.json').relative_to(R)),'actual_model_result':str((L/'artifacts/run-001/result.json').relative_to(R)),'known_failure_replay':replay,'genos_accessed':False}
(A/'IMPLEMENTATION_BINDING.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n')
text=f'''대사 조사 과제 설계 구현·검증 결과
2026-10-16 / workflow 1.4.2 / 로컬 MAIN generation {pointer['generation']}

완료 범위
설계 A–F를 기존 RAG 및 대사 실행 경로에 구현하고, 변경 파일별 작업 코드 통합,
동일 코드 검증, hash 고정 MAIN 승격, 활성 포인터의 실제 service 진입까지 확인했다.
선택 릴리스: {pointer['release_id']}
검증 후보와 선택 릴리스의 서빙 파일 {len(f['serving_files'])}개가 모두 SHA-256으로 일치한다.
작업 코드의 구현·설정 {len(implementation)}개 파일도 같은 후보와 일치한다.
엔진·워크플로우 pin을 포함한 관련 통합 파일은 {len(paths)}개다.
작업 트리 전체가 후보와 같다는 뜻은 아니다. 다른 동시 작업 변경은 보존했고,
그 변경은 이번 릴리스에 포함됐다고 주장하지 않는다. 원문·색인 세대는 기존 선택을 유지했다.
GENOS 반입·배포·내부 모델 검증은 수행하지 않았다.

구현 내용
1. 성공 근거와 후속 실패 분리: 마지막 유효 결과·누적 원문·최근 시도·미완료 과제를
   각각 보존한다. 후속 실패가 기존 성공을 덮어쓰지 않고 상충한 주장은 원문과 함께 남는다.
2. 업무별 비교 항목표: 일반/절차/전결/비율 profile과 여러 쟁점을 설정으로 관리한다.
   대상·의무·수치·조건·예외·전결·기준일 등을 선택한다. 정답 조문·숫자의 질문별 하드코딩은 없다.
3. 양방향 단서 전달: 상대 규정의 검증된 위치·정의·의무를 SEARCH_HINT_ONLY로 전달한다.
   상대 원문을 자기 쪽 규정의 증거로 쓰지 못하도록 출처와 인용을 검증한다.
4. 항목별 추가 조사: 기존 Pipeline.run 안에 연구 과제를 연결하고, 정확 위치·정의·명시 참조·
   문서 내부 검색 도구부터 실행한다. 같은 과제의 반복 실패와 재개 예산 초기화를 막는다.
5. 필요한 범위만 전달: 같은 source_id라는 이유로 전체 조문/별표를 자동 확장하지 않는다.
   비교 항목의 본문과 조건·예외 의존성을 함께 검토한다. source_complete와 항목 충분성은 별개다.
6. 부분 결과 반환: 항목 문구·내용 차이·제정 근거·적용성·법적 부합을 분리한다.
   한쪽 제안이 잘못돼도 다른 쪽의 검증된 항목을 유지하며 원래 실패 제안도 저장한다.
7. 기존 조사 경로 재사용: 과제 맥락을 기존 경로 저장에 결속한다. 과거 답변·실패를 정답으로
   승격하지 않고 원문·판본·권한·상태가 달라지면 다시 검증하거나 사용을 차단한다.

검증 중 추가로 고친 결함
- 부모만 재개되고 자식 RUNNING 요청이 충돌하던 경로를 수정했다. 부모와 사건 잠금을
  가진 정확한 동일 요청만 복구한다. 이미 커밋된 판단은 기존 원문 ID와 함께 검증해 재사용한다.
- 첫 항목 검토가 429/전송·스키마·예산 오류로 끝날 때, 이미 채택한 원문까지 답변에서
  사라지던 경로를 수정했다. 확보 원문을 '항목별 검토 미완료'로 표시하며 법률 결론을 만들지 않는다.
  조사 중 본 모든 자료를 붙이지 않고 기존 자식이 채택한 정확 span만 반환한다.

실제 연결
service.py → workflow.api/runtime → risk_team_compare_workflow.flow/task_board
→ RagAdapter.ask_rag → workflow_rag → 기존 Pipeline.run 및 원문 조사 도구.
설정: 02_BACKEND/workflow/risk_team_compare_workflow/comparison_fields.json
과제 계약: comparison-research-v1. workflow-result-v1에 comparison_items,
research_attempts, latest_rag_attempts, item_validation_failures, unreviewed_sources를 연결했다.
코드 binding이 다른 기존 실행에 새 계약을 암묵적으로 채우지 않는다.
활성 포인터 검사에서는 앱을 주입하지 않고 workspace service.application()으로 부팅했다.

검증 결과
- 유한 계약 306/306: 항목96, 원문 묶음16, 조사 과제42, 부분 제안40, 재개64, 실패 원문 반환48.
- 최종 고정 후보 API·실패·재개 검사 58/58.
- 공통 회귀: 기준/후보 각각208통과·동일6실패. 새 실패0.
  기존 실패는 test_source_span_norm.py의 direct_note=True 6조합이다. 정확한 ID와 로그는 최종 result.json.
- 실제 선택 데이터의 서비스 연결: 후보13/13, 기준12/12.
- 통합 작업 코드 API58/58, 서비스13/13. 활성 MAIN service/HTTP13/13.
- 원문·권한·세대·저장 결과 변조, 반복/중복, 원래 deadline·누적 호출 유지, 저장 응답 소비자를 포함한다.

실제 모델 관측과 한계
ADR0827은 실제 Qwen3.8/Parasail FP8/reasoning none/no fallback으로 risk104를 실행했다.
4회 호출 뒤 원문 체크포인트에서 계획된 프로세스 종료를 주입하고 같은 예산·deadline으로 재개했다.
누적12회 호출, 원문 span 불일치0. 자식 재개는 성공했지만 ITEMS 두 호출이 공급자429로 실패했다.
외규6근거를 확보했으나 당시1.4.1 최종 답변의 인용은0이었다. 그 실패 기록은 보존했다.
최종1.4.2의 읽기 전용 재표시 검사에서는 같은 외규6근거를 정확한 원문으로 반환했다.
이 재표시는 새로운 모델 실행이 아니며 원래 원장을 수정하지 않았다. 법적 비교 행은 여전히0,
미완료 항목3개다. 외규로 내규 내용을 만들거나 미확보를 규정 부재로 바꾸지 않는다.
법률 정확도·검색 적합성 개선률·비용 절감률은 인증하지 않았다. risk_cm은 question_only이며
필요한 내규 자체의 부재/미반입은 별도 데이터 보강이 필요하다.

실행 이력과 남은 문제
- ADR0819/0820은 완료 후 발견한 메타데이터 TODO 오류를 역사 그대로 남겼다.
  최종 승격은 완료·Accepted·decision_eligible인 ADR0830의 독립 고정 기술 계약 결과를 사용했다.
- ADR0826의 API 파일 복사 누락은 기존16개 보충으로 기록했다. 최종0829는58개를 한 실행에서 검사했다.
- ADR0828의 최초6실패는 fixture 조문 제목을 빠뜨린 검사 기대값 오류였다. 제품 코드는 같았다.
  이후 /tmp 공간 소진으로1건 중단돼 원장을 디스크로 보존 이동한 뒤 같은1건을 다시 검사했다.
- ADR0829는 디스크 회귀627.34초로 사전600초한도를 넘겨 승격에서 제외했다.
  ADR0830은 같은 제품 코드와 성공/시간 기준을 유지하고 빈 tmpfs 검사환경에서 재검증했다.
- ADR0829의 최초 과거 원장 재표시 어댑터는 SourcePort의 side projection을 빠뜨렸다.
  동결 제품·기준·기대값은 변경하지 않고 실제 SourcePort projection을 적용한 보충 어댑터를 기록했다.
- 전체 ADR graph 검사의 잔여 역사 오류는 GRAPH.txt에 남긴다. 이번 최종 ADR의 --final은 별도로 통과했다.

재현·복원
최종 정본: 04_EXPERIMENTS/ADR/ADR-0830-comparison-main-confirmation/artifacts/run-001/result.json
후보/원문/설정 동결: 같은 ADR artifacts/design/freeze.json 및 release-rebase.json
MAIN 결속: IMPLEMENTATION_BINDING.json 및 같은 ADR artifacts/active-consumer-v2.json
승격 계획·검증·rollback: 08_DEPLOYMENT/RELEASES/{pointer['release_id']}/release.json,
  authorization.json, validation.json, rollback/ 및 01_DATA/ACTIVE/local/receipts/.
로컬 서빙 원복 명령: .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
이는 이전 선택 릴리스로 되돌리는 동작이다. 작업 코드 원복은 ADR0830→0826→0823의
working-integration.json과 working-before를 역순 대조하고 현재 after 해시가 같은 파일만 복원한다.
원래 없었던 파일만 해당 receipt에 따라 제거한다. 다른 변경이 있으면 먼저 병합한다.
임시 검사 폴더 이동은 test-workdirs/relocations.json, 압축 보존은 해당 archive manifest를 따른다.
'''
(A/'IMPLEMENTATION.txt').write_text(text)
(Q/'MAIN_RESULT.txt').write_text(text)
print('Final implementation and binding report written')
