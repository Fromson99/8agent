# 최종 핵심 근거에서 만드는 shortcut

2026-10-08 사용자 요청으로 core 근거 경로 소비와 CM 공통 등록을 로컬
`native-cm-serving-20261008-r1`/포인터 generation 46에 연결했다. 새 원문 1,546문서와
CM51/98근거의 source/nav/fulltext 결속·권한·실제 로컬 서비스 선택을 확인했다.
외부 모델의 내부 CM 경로 차단은 유지하며 GENOS 현장 반입·배포는 별도다.
[활성화·검증·롤백 기록](../../../09_ARTIFACTS/AUDITS/20261008-native-cm-serving/completion.json).
아래 MAIN45 선택 상태는 당시 통합 기록이다.

사용자가 요구한 재사용 대상은 최종 근거에 도달하는 데 필요한 선택이다. 최종 SELECT가 채택한 원문의 문서·조문·하위 단위·범위에서 직접 읽을 위치를 추린다. 중간에 검토했다가 제외한 원문이나 과거 답변의 법률 결론은 shortcut에 넣지 않는다. 원래 탐색과 판단 기록은 감사·복귀를 위해 보존한다.

예를 들어 `fulltext → A 검토 → B 확인 → 예외 C 확인` 뒤 B와 C를 채택했다면 새 shortcut은 B와 C의 현재 원문을 확보하는 경로다. 같은 목적·사실 조건·자료 구분으로 재사용할 때 초기 fulltext 후보 탐색을 건너뛴다. 원문과 현재 권한·데이터 세대를 확인하고, 기존 SELECT와 ASSESS에서 현재 적용 및 충분성을 판단한다. 필요한 자료가 더 있으면 기존 RESEARCH/fulltext 경로로 돌아간다.

## 멀티턴

각 질문 goal의 현재 revision과 최종 accepted route를 연결한다. 성공한 답변 발행 뒤에만 `unit:core:<goal_id>`의 새 head를 발행한다. 이전 `sw_knowledge`는 불변 이력으로 보존한다.

| 다음 턴 | 현재 shortcut |
|---|---|
| 최종 근거가 B·C에서 D로 바뀜 | 현재 채택 D로 head를 교체하고 B·C 이력은 보존 |
| 조건·목적·범위 정정이 시작됨 | 이전 head를 현재 조회·재사용 대상에서 제외 |
| 정정 도중 실패하거나 중단됨 | 이전 경로가 현재 경로로 되살아나지 않음 |
| 이전 조건으로 복귀하고 답변 발행 | 복귀한 현재 revision의 근거로 새 head 생성 |
| 표현·표 형식만 변경 | 근거를 유지하고 새 accepted route에 결속 |
| 다른 질문·branch | 조건과 goal을 분리하여 경로를 합치지 않음 |

새 READ 뒤에 이전 SELECT의 완료 checkpoint를 복원하던 연결을 보완했다. 실제 요청 내의 중단 복구·추가 조사 checkpoint는 기존 계약을 따른다. 새로운 읽기 결과는 현재 핵심 근거 선택으로 연결한다.

## 저장과 소비

`core_evidence_route.py`는 최종 SELECT의 채택 spans를 실제 원문의 block/Unicode 위치와 대조하고 source 좌표와 hash를 저장한다. 동일 SQL v4의 `sw_unit/sw_knowledge/sw_member/sw_dependency`를 사용한다. 스키마 이행이나 별도 검색 실행기는 만들지 않는다. source text는 기존 source authority에 보존하고 compact route에는 원문 위치·범위·fingerprint·현재 조건·발행 근거 참조를 저장한다. 저장 claim과 procedure는 빈 배열이다.

`ShortcutRepository.current`가 현재 goal/route/SELECT 및 권한·source dependency를 검사한다. `WikiExecution`은 조건이 맞는 현재 route를 조회하고 `law_candidates.discover`에 전달한다. 기존 원문 읽기·근거 선택·답변 판단이 소비한다. 외부 transport에는 비공개 case의 core route를 제공하지 않는다. AD의 shortcut/wiki 중지와 제외·폐기 제어를 유지한다.

새 feature를 켜면 과거 command·모델 선택 전체를 replay하지 않는다. 법률 위키 조회와 파일 projection은 같은 v4 SQL authority를 사용하며 파일 projection은 기존 compiler의 `rebuild`와 `CURRENT.json`을 따른다. 과거 파일은 보존하고 현재 권한·상태는 SQL에서 다시 확인한다.

## 확인 범위와 적용 상태

2026-10-07 작업 코드에 통합했다. 기준 릴리스는 `session-runtime-v6-20261007-r1`, local pointer generation 45다. 선택 포인터를 바꾸지 않았으므로 현재 서비스의 활성 기능으로 보고하지 않는다. GENOS 반입·배포는 수행하지 않았다.

ADR0682의 최초 실패는 보존하고 ADR0683에서 후속 후보를 고정했다. 후보와 통합 작업 코드에서 새로운 모의 계약23개를 모두 통과했다. 초기 fulltext 생략, 추가 자료 요청의 fulltext 복귀, 실제 멀티턴 채택 spans 교체, 중단 중 구 head 비노출, 법률 위키 파일 연결을 HTTP 경로로 확인했다. 저수준 계약은 제외한 A가 저장되지 않고 채택 B·C 및 필수 예외가 남는지 확인한다.

동일 기존 회귀148개는 기준146개, 동결 후보145개, 통합 작업 코드146개가 통과했다. 공통 과거 signing 검사와 혼합 설정 fixture 결과를 보존했다. 추가된 한 실패는 빈 offered knowledge에 모의 experience ID를 강제하는 검사다. 기준은 해당 명령을 실행하지 않고 cached CASE_START로 대체하여 통과했다. 현재 경로는 제공되지 않은 ID를 거절한다. 이 차이를 통과로 재채점하지 않았다.

실제 모델의 법률 정답률·표현이 다른 질문의 일반화·응답 속도는 측정하지 않았다. 현재 lookup은 정규화한 task와 사실 조건의 일치 및 source binding을 사용한다.

- [사전 기준과 실험·후속 계보](../../../04_EXPERIMENTS/ADR/ADR-0683-core-evidence-shortcut-consumer-closure/실험/manifest.json)
- [원 결과와 실패 기록](../../../04_EXPERIMENTS/ADR/ADR-0683-core-evidence-shortcut-consumer-closure/artifacts/run-001/result.json)
- [검증한 릴리스 inventory](../../../04_EXPERIMENTS/ADR/ADR-0683-core-evidence-shortcut-consumer-closure/artifacts/design/release-rebase.json)
- [작업 코드 통합과 복구용 백업](../../../04_EXPERIMENTS/ADR/ADR-0683-core-evidence-shortcut-consumer-closure/artifacts/working-install-receipt.json)

작업 코드 원복은 receipt의 after hash가 유지되는지 확인한 뒤 해당 runtime 파일과 pipeline/engine pin 백업을 적용한다. 이후 변경이 있으면 이 작업의 patch만 역으로 병합한다. 원문·DB·완료 실험·선택된 릴리스 이력은 삭제하지 않는다. MAIN 적용은 검증한 inventory로 hash 고정 plan을 만들고 별도 명시적 승격 절차를 따른다.

사용자 요청으로 [GENOS shortcut R1](../../../08_DEPLOYMENT/GENOS/handoffs/core_evidence_shortcut_20261007_r1/GUIDE_UTF8.txt)을 삼성파트너 메일로 발송했다. 기존 GENOS 인계 코드에 검증 후보의 변경분을 병합한 해시 고정 패치이며 적용에 필요한 선행 로그 롤백 R3 실행 TXT도 첨부했다. 첨부 TXT90명령, 선행 코드3종의 핵심23개씩, 동일 checkout 모의 generation gate3개를 통과했다. [발송 확인](../../../08_DEPLOYMENT/GENOS/handoffs/core_evidence_shortcut_20261007_r1/EMAIL_SENT.json)은 수신자와 첨부6개의 이름·크기·SHA를 보존한다. 메일 발송은 현장 반입·push·배포·질의 완료를 의미하지 않는다.
