# MVP 구현 에이전트 안내

<!-- MAIN104_SQL_FOLLOWUP -->
**2026-10-27 — MAIN105 반영·실제 서비스 확인 완료:** [전체 반영·실제 실행·온톨로지 후속](MAIN_SQL_AND_ONTOLOGY_FOLLOWUP_20261027.md). 최초211초 원인의 MAIN104 SQL 수정에 반복 원문 확인 재사용과 네 연결 TEMP VIEW의 ID 점조회를 더했다. 보관응답1회 재생의 동일 계측35화면736.500→93.718초(87.275% 감소), 원문·행동·최종 답변 동일, 새 모델 호출0회다. 신규237조건·관측보조1,345조건을 구분한 ADR1081 검증 후 MAIN105 `navigation-validation-20261027-r1`을 선택했고 실제 서비스19확인(HEALTH·모의 HTTP1회·새 모델0회)이 통과했다. 작업 코드 통합에서 새4검사 통과, 기존7실패는 변경 전후 동일하다. 온톨로지는1074 부분실패→1077 상태 전환 수리→MAIN105 결합1079 실모델1셀/10호출을 완료했다. 두 원문의 판단 보존을 확인했지만 근거 연결 보완1회·제한 답변으로 품질 효과는 미인증이다. MAIN105 최종 누적본433파일·첨부4개를 삼성메일 SENT `1a17ae4c6976a0f7`로 발송·확인했다. 설치144명령·SQL18·상태13쌍을 통과했으며 MAIN104 첨부를 대체한다. P0~P4 전체 구현·전체 응답시간 개선·법률 품질·온톨로지 MAIN·GENOS 현장 배포 완료로 확대하지 않는다. 아래 이전 상태 기록과 구분한다.
<!-- /MAIN104_SQL_FOLLOWUP -->

**2026-10-27 — 211초 원인·최적화 확인:** [상세 측정과 결과](NAVIGATION_211S_ROOT_CAUSE_20261027.md). 정의 연결 조회의 전체 참조 VIEW 조립과 권한 ID 목록 반복이 원인이었다. 동일 계측의8개 대응 구간236.744→19.891초(91.598% 감소), 원래 화면·행동·전달 원문8/8 일치, 신규 모델 호출0회. 당시 SQL 두 수정은 작업 코드에 통합했고 선택 MAIN103·GENOS 배포는 유지했다. 이후 MAIN 반영 상태는 문서 상단 최신 기록을 따른다. 초기 준비·전체 응답시간·온톨로지 품질·GENOS 속도와 구분한다. 아래2026-10-26 상태는 선행 단계 기록이다.

**2026-10-26 성능 구현·실험 상태:** [상세 결과](NON_MODEL_LATENCY_IMPLEMENTATION_RESULT_20261026.md) · [전체 계획](NON_MODEL_LATENCY_OPTIMIZATION_PLAN_20261026.md). 격리 후보에 P0 계측·P1 일부와 온톨로지 재표시 오류 수정을 구현했다. 반복 스키마 검사96.17% 감소는 국소 비교이며 전체 서비스 개선율이 아니다. 초기 준비17.605초의98.266%를 이름 있는 구간에 귀속했고 연결 매칭·구조 결속10.676초가 가장 컸다. 실모델1회는 불완전 출력/연속 공백으로 중단, 온톨로지 효과와 전체 최적화는 미확인이다. P2/P3/P4·기본 작업 코드 통합·MAIN103·GENOS 반영은 미완료다. 과거 실험과 실패는 보존한다.

<!-- ADR1066_LIVE_STATUS -->
**2026-10-26 실제 모델 관찰: 부분 중단.** 사전 동결한 3문항×3조건 중 첫 문항 A0/A1은 제한 답변, A2는 원문 재표시의 상태 결속 오류로 중단했다. 나머지6셀은 미실행이다. 제품27호출·관찰 비용$0.17853620·제품 실행 합계762.10초, 채점 모델0회다. 관찰한 행동 응답19회에서 이전 필수 항목 누락과 입력 문자 차단은 재현되지 않았고, A1/A2 승인 묶음 실제 전달도 확인했다. 전체 성공·법률 정답·온톨로지 개선 인증은 아니다.

같은 원문 카드의 `presentation_id` 갱신이 전체 source hash를 바꿔 동일 온톨로지 페이지의 내용 변경으로 오인됐다. 별도로 조문 선택과 목적 불일치, 탐색 화면 구성 지연, 구형 gate의 evidence-ID 카드 감사 호환 문제가 남았다. 원문 검증을 끄지 않으며 결과 후 코드·점수를 수정하지 않았다. MAIN103·GENOS·운영 골드는 미변경이다. [결과·원인·원시 기록](../../../../04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/POST_RUN_DIAGNOSIS.md). **아래 구현 당시의 “실모델0회·미실행” 표기는 과거 시점 기록이다. 이는2026-10-26의 관찰이며, 현행 상태는 [MAIN105 및 후속 실험 기록](MAIN_SQL_AND_ONTOLOGY_FOLLOWUP_20261027.md)을 따른다.**
<!-- /ADR1066_LIVE_STATUS -->


[v4 목차](../ONTOLOGY_V4.md) · [핵심 MVP](MVP.md)

2026-10-24. 온톨로지 v4 핵심 MVP를 구현·실험할 에이전트에게 이 문서 하나를 주고 시작한다.

**2026-10-26 현재 작업 지침:** [행동별 최소 입력·응답 계약](ACTION_CHOICE_CONTRACT_20261026.md)과 [구현 상태](MVP_EXECUTION_REPAIR_STATUS_20261026.md)를 먼저 읽는다. 미실행 ADR1066 후보에서 행동별 완전한 object 스키마, 확정값의 서버 복원, 현재 메뉴와 정상·보완 호출의 동일 compiler/decoder를 구현했다. 743파일 rev-002의 동일 동결본 합성 계약/API 80개가 통과했다. 새 이유·다중 쟁점·의존 관계·법률 판단은 모델이 결정하며, 현재 원문의 미제출 판단은 pending으로 보존한다. 입력 문자 차단 해제·출력 토큰 상한 없음과 기존 호출·도구·시간 예산을 유지한다. rev-001·12개 입력 한도 검사 이력은 새 계약의 검증 결과가 아니다. [구현 결과](../../../../04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/ACTION_CONTRACT_RESULT.md)와 [최종 검사](../../../../04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/action-frozen-final-summary.json)를 확인한다. 실모델 미실행·실제 생성 호환성 및 법률 품질 미확인·MAIN103/GENOS 미변경이다. **아래 인계·실험 지시는 당시 이력이며 이번 작업 지시보다 우선하지 않는다.**

**2026-10-26 후속 작업 지침:** [현재 구현·검증 기록](MVP_EXECUTION_REPAIR_STATUS_20261026.md)을 먼저 읽는다. ADR1065는736파일 rev-002·회귀1,028개/동결본104개 통과 후 실제9셀을 모두 관찰했지만 모두 답변 전 중단했다. 최초실패7개는 행동 이름만 반환한 형식 위반,2개는 후보 입력 초과다. 보완 입력 초과·목차 탐색 후 화면 증가도 남아 있다. 새 평탄화 스키마의 생성기 호환성을 합성 검증만으로 확정하지 않는다. [원인·전송 증거](../../../../04_EXPERIMENTS/ADR/ADR-1065-ontology-task-local-navigation/artifacts/POST_RUN_DIAGNOSIS.md). 원문·승인 묶음 도달0이며 A1/A2 효과는 미확인이다. ADR1061~1064 및1065 실패 원기록·동결 코드·기준은 보존하고 후속 변경은 새 ADR에서 수행한다. 아래 이전 인계를 현재 실행 지시로 혼동하지 않는다. MAIN103·GENOS 미반영이다.

이전 상태 — **ADR1059에서 반복 입력을 줄이고 실제3문항 A0 검증을 마쳤다. 최종21호출 모두HTTP200, 입력 초과·기술 오류0, 최대88,877자다.** [MVP 이전 후보 절](MVP.md#이전-후보-반복-입력-축소와-실제-전송-검증--adr-10591060)을 먼저 읽는다. 허용 문서 내부 ID는 서버에 결속하고, 원문·좌표·필드의 공통값을 무손실 참조한다. 필수 판단·원문·권한·상태·20조문/더보기·전체 적중 법령은 유지한다. 저장4입력은44.5~49.3% 줄었고 회귀359개·동결32개를 통과했다. [ADR1059 제품 실행](../../../../04_EXPERIMENTS/ADR/ADR-1059-compact-input-guidance-binding/README.md)과 [ADR1060 실제 전달 감사](../../../../04_EXPERIMENTS/ADR/ADR-1060-exact-wire-reference-audit/README.md)가 정본이다. 감사는 실제 요청21건·원문324span·권한·변조 거부30검사 통과, 추가 모델 호출0회다.1059 원집계의 참조번호 재생성 오류8건은1060 별도 집계로 대체하고 원기록은 보존한다. **답변은 부분1·근거부족2이며 완전 답변·법률 정답 인증은 없다.**1058 중간 코드 오류12호출과 과거 실험을 보존한다. 원문·색인 공유, MAIN103·GENOS 미반영이다.

이전1054 실험은111셀 실행을 마쳤다. 서비스 완료15, 제한 종료96(입력 한도93·판단 연결3)이며 평가 수집은 모듈 import 오류로 중단됐다. 아래 “진행 중” 표현은 해당 기록 시점의 이력이다. 이전 결과를 수정하거나 그 실험에1056 코드를 섞지 않는다.

후속 수정 상태 — **ADR1055의 판단 연결 부분 보완 후보를 구현하고 계약/API75개를 통과했다.** 사용자 요청에 따라 누락된 연결만 기존 수정1회에서 보완한다. 해당 판단·연결 가능한 주장·필요한 현재 원문만 보내고 해당 판단 행만 받는다. 원래 평가에 합친 뒤 주장·원문·권한·상태 전체를 재검증한다. 반복 누락은 검토 미완료와 미확인을 보존한 제한 답변으로 남기며, 근거·권한·해시 오류를 우회하지 않는다. [MVP 후속 후보](MVP.md#후속-후보-판단-연결의-부분-보완--adr-1055)와 [ADR1055](../../../../04_EXPERIMENTS/ADR/ADR-1055-judgment-link-delta-repair/README.md)를 먼저 확인한다. 이 후보는698파일 rev-001이며 동결 API 재검사 결과는 해당 ADR이 정본이다. 실모델 호출0회, MAIN103·GENOS 미반영이며 **진행 중1054의111셀에는 아직 포함되지 않았다.**

현재 인계 상태 — **ADR1054의 상태 전달 후보를 검증·동결하고2026-10-25 14:31 KST 새37문항×3조건 실험을 시작했다.** 관련 계약/API140개·실행기31개 통과. 동결 코드22개 재검사에서 실제 어댑터 초기화도 확인했다. ADR1053의 시작 오류는0호출로 보존하며 [최신 ADR1054](../../../../04_EXPERIMENTS/ADR/ADR-1054-ontology-mvp-state-binding/README.md)를 따른다. 사용자2026-10-25 승인에 따른 작업이다. [MVP의 최신 후보 절](MVP.md#현재-후보-매-단계-서버-상태-전달--adr-1053)과 [ADR1053](../../../../04_EXPERIMENTS/ADR/ADR-1053-ontology-mvp-step-state/README.md)을 먼저 확인한다. ADR1052의 전체 법령 개요·20조문 후보·선택 항호 읽기를 이어 사용한다. 기존1049는44번째 셀에서 중단됐으며 결과는 보존한다. 공통 호출 경로에서 상태를 전달하되 원문·권한·필수 판단·재개 검증은 유지한다. MAIN103·GENOS 미반영이다.

아래는 당시의 이전 인계 기록이다. 과거 보류·재시도 지시를 최신 실행 승인으로 혼동하지 않는다.

이전 인계 상태 — **2026-10-25 사용자 요청에 따른 동일 r10 한 차례 재시도도 제공자429로 중단됐다.** [ADR1048](../../../../04_EXPERIMENTS/ADR/ADR-1048-ontology-mvp-r10-restart/README.md)의 첫 A0에서 정상 응답1개 뒤 두 번째 호출이 Parasail 공유 처리 용량 제한으로 거절됐다. 완료0/111, 제품 호출2회, 평가0회다. 코드684파일·모델·데이터·37문항·31묶음·평가·예산은 ADR1047과 동일하고 실행기20검사는 다시 통과했다. 제품/API619검사는 동일 바이트 이력을 상속했다. 자동재시도0회이며 추가 호출 없이 종료·실패·미확인 사용량을 보존했다. 실제 기록은 ADR1048의 design-freeze.json·matrix-progress.json·matrix-stop.json·stopped-run-closeout.json이다. MAIN103·GENOS는 바꾸지 않았다.

이전 r10 최초 실행 기록 — **2026-10-25 사용자 “전부다 진행해보고 이제는 실험도 돌려봐봐” 지시로 새 최적화 후보의 37문항 × 3조건 실행이 승인됐다.** [ADR1047](../../../../04_EXPERIMENTS/ADR/ADR-1047-ontology-mvp-state-format/README.md)의 r10은619개 제품/API·20개 실행기 검사를 통과하고684파일로 동결됐다. 새 실험은 첫 A0의6번째 호출이 제공자429로 거절되어 완료0/111에서 중단됐다. 자동 재시도 없이 제한된429 처리 정책을 사용자에게 확인 중이며, ADR1045의 중단 실행을 재개하거나 실패 기록을 덮어쓰지 않는다. 실제 진행은 ADR1047의 design-freeze.json·matrix-progress.json·matrix-stop.json이 정본이다. 출력 상한 없음·현재 데이터·31개 승인 묶음·37문항·평가 기준·미확보 상태를 유지한다. MAIN103·GENOS는 미반영이다. 아래 기록은 각 시점의 이력으로 읽는다.

이전 보류 및 r9 인계 기록: **사용자 지시로 37문항 × 3조건 실험을 계속 보류한다. 자동 재개하지 않는다.** ADR1045는 1/111 완료 후 HTTP429로 중단됐으며 실패 기록을 보존했다. 후속 [ADR1046](../../../../04_EXPERIMENTS/ADR/ADR-1046-ontology-mvp-shared-io/README.md)의 `shared-io-r9/rev-001`에서 원문·좌표 공유, 명시적 이전 판단 문장 참조, 단계별 입력·안내를 구현하고 합성 계약/API 537개를 통과했다. 기존 r8에서 이어 개발한 679파일이며 MAIN103·GENOS는 미반영이다. 외부 모델 호출·실제 원문 DB 실행은 0회로, 토큰·지연·정확도 효과는 미검증이다. 출력 상한 없음·현재 데이터·37문항·평가 기준·미확보 상태는 유지한다. 아래 이전 구현·승인·실행 기록은 이력으로 읽는다.

## 목표

1. **MVP-1 컴파일:** 온톨로지 묶음이 있는 조문에 도착하면, 연결을 목록으로 주는 대신 조립한 묶음으로 준다. A0(지금 그대로) / A1(같은 원문을 조립 없이) / A2(컴파일)를 비교한다.
2. **MVP-2 부분 온톨로지화:** 묶음이 없는 연결은 에이전트가 직접 판단하고, 실행 뒤 "이렇게 온톨로지화하면 된다"를 제안한다. 기존 스키마에 맞으면 채우고, 맞지 않으면 새 스키마를 제안한다. 사용자가 고칠 수 있다.

## 읽을 문서 — 이 순서로

| # | 문서 | 왜 |
|---|---|---|
| 1 | [AGENTS.md](../../../../AGENTS.md) | 저장소 규칙: 실험 ADR 절차, RAM·저장공간 제약, 반출 승인, MAIN·GENOS 상태 구분 |
| 1-1 | [행동별 최소 입력·응답 계약](ACTION_CHOICE_CONTRACT_20261026.md) · [구현 상태](MVP_EXECUTION_REPAIR_STATUS_20261026.md) | 현재 개발 계약과 실제 확인 범위. 아래 과거 후보의 한도·인계를 그대로 재적용하지 않음 |
| 2 | [MVP.md](MVP.md) | **정본.** 컴파일 예(제97조 → 시행령 제163조), 실험 조건·지표, 구현 목록 |
| 3 | [SEED_ARTICLES_20261024.json](SEED_ARTICLES_20261024.json) | 묶음을 만들 씨앗 조문 31개와 시험 문항 37개 |
| 4 | [CONTROLLED_KNOWLEDGE.md](CONTROLLED_KNOWLEDGE.md)의 "스키마 v0", "개념 묶음 JSON", "새 스키마 제안", "개념 묶음 작업", "S3 폴더 구조" | 묶음·제안 JSON 형식과 LLM 출력 검사 규칙. MVP에서는 S3 대신 `01_DATA/ONTOLOGY_WORK/` |
| 5 | [SOURCE_ENTRY_COMPOSITION.md](SOURCE_ENTRY_COMPOSITION.md)의 "원하는 관계까지의 경계", "설명도 컴파일 산출물이다" | 최소 범위·상위 조건, 미읽은 조문 요약 금지, 설명과 실행은 같은 계획에서 |
| 6 | [CURRENT_STATE.md](CURRENT_STATE.md)의 "2026-10-24 구축 결정을 위한 확인" | 현재 코드 사실. 기본 v6 프로필 부팅 실패(고정값 불일치), `read_judgment`의 작업 코드/MAIN103 차이 |
| 7 | [실패 복구 정책](../../OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md) | 에이전트·도구 코드를 고칠 때 필수 |
| 8 | [EXPERIMENT_AGENT_PROMPT.md](../../../../04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md), [STANDARD.md](../../../../04_EXPERIMENTS/LEGACY_ADR/STANDARD.md) | 실험 단계 전에 끝까지 읽기 |

MVP 다음 단계로 랜딩을 다룰 때만 [LANDING.md](LANDING.md)를 읽는다.

## 볼 코드

| 파일 | 왜 |
|---|---|
| `02_BACKEND/semantic_runtime/legal_agent/definition_context.py` | **본보기.** 원문 읽기 뒤 코드가 모델 선택 없이 관련 원문을 읽어 오는 기존 기능(최대 4개·12,000자·재귀 없음, 실패 기록, 이벤트). 컴파일 전달을 같은 틀로 만든다 |
| `02_BACKEND/semantic_runtime/legal_agent/law_navigation.py` 1848행 부근 | 정의 문맥 획득을 부르는 자리. 컴파일 전달을 같은 자리에 붙인다 |
| `02_BACKEND/semantic_runtime/legal_agent/unit_relations.py` (`catalog`) | 읽은 범위의 연결 목록. "남은 연결" 계산에 쓴다. 별도 파일 별표 연결은 이미 들어가 있다 |
| `02_BACKEND/semantic_runtime/legal_agent/unit_reading.py` (`read`, `offer_plan`) | 원문 읽기 도구 |
| `02_BACKEND/semantic_runtime/legal_agent/structure_query.py` | 정확한 조문 조회(묶음 조항 → 현재 원문) |
| `02_BACKEND/semantic_runtime/annex_files.py` | 별표 파일 연결 규칙 |
| `00_SYSTEM/PIPELINE.json`, `00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json` | 프로필과 고정값 |

## 쓸 데이터

| 데이터 | 비고 |
|---|---|
| `01_DATA/review/cm_core_e2e_v3.json` | 질문·기준답변. 근거 좌표는 아래 패키지 기준으로 본다 |
| `09_ARTIFACTS/AUDITS/20261024-cm-rebind/CM51_SOURCE_PACKAGE_SELECTION_20261015.json` | CM 근거를 현재 선택 세대로 다시 묶은 결과(조문 본문 변경 0건) |
| `01_DATA/review/fsc_hard_retrieval_v3.json` | 공개 금융위 질의회신 기반 문항 |
| `01_DATA/GOLDEN/risk_cm/` | RISK-CM-029·030. 기준답변 없음, 근거 확보 지표만 |
| `04_EXPERIMENTS/ADR/ADR-1037-uncapped-judgment-live-question/artifacts/known-request.json` | 양도 필요경비 질문 |
| `01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation` | 현재 선택 데이터 세대(MAIN103) |

CM·risk_cm은 외부 실험 모델 전송이 승인됐다. 기준답변·판정은 평가 쪽에서만 쓰고 답변 모델 입력에 넣지 않는다.

## 읽지 말 것 (MVP 범위 밖이거나 지난 판)

- `ONTOLOGY_V4/HISTORY/` — 재작성 전 판
- [BUILD_PLAN.md](BUILD_PLAN.md)의 단계 1~8, [MULTITURN_LEGAL_AGENT.md](MULTITURN_LEGAL_AGENT.md), [COMPILATION_AND_SCENARIOS.md](COMPILATION_AND_SCENARIOS.md), [JUDGMENT_AND_CORRECTION.md](JUDGMENT_AND_CORRECTION.md) — MVP 뒤 단계
- [PERFORMANCE_EVIDENCE_PLAN.md](PERFORMANCE_EVIDENCE_PLAN.md) — 대형 모델·벡터 기준군까지 넣은 큰 비교 설계. MVP에서는 쓰지 않는다
- `ONTOLOGY_V4/*.json` 검증 기록 — 문서 검사 이력

## 할 일 — 이 순서로

| # | 할 일 | 끝난 조건 |
|---|---|---|
| 0 | **기준선 복구.** `PIPELINE.json`의 v5·v6 프로필 고정값을 실제 파일에 맞춘다. v6는 `read_judgment` 켬, `small_connection_context` 끔. 기본 v6 경로를 막는 기존 실패 테스트(설정 해시 불일치, v6~v8 모의 전송 `KeyError: 'laws'` 등)를 원인별로 정리 | 작업 코드 기본 v6 프로필로 `/v1/rag/ask`가 부팅하고 모의 전송 검사가 통과 |
| 1 | **ADR 선점.** 코드 수정 전에 `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py new --adr-root 04_EXPERIMENTS/ADR` | ADR 생성, 가설·조건·지표·문항 동결 |
| 2 | **씨앗 묶음 초안.** 씨앗 조문 31개마다 `ontology-bundle-v0` JSON 초안을 쓴다. 조항 원문은 현재 세대에서 읽어 해시를 붙인다 | **사용자 승인 전에는 실험하지 않는다** |
| 3 | **컴파일러.** 묶음 + 현재 원문 → 컴파일 묶음(JSON + 읽기용 텍스트). 순서: 법이 정한 것 → 위임받은 내용 → 공통 조건 → 예외. 묶음이 고른 호·목만 넣고, 남은 연결을 붙인다. 원문 해시가 다르면 그 묶음을 쓰지 않는다. 모델 호출 없음 | 단위 검사: 순서·범위·해시 불일치·남은 연결 |
| 4 | **도착 시 전달.** `definition_context`와 같은 틀로, 묶음 원문을 확보하고 컴파일 카드를 조사 화면에 넣는다. 프로필 설정으로 A0/A1/A2 전환(기본 꺼짐), 온톨로지 스냅샷 해시 고정 | 합성 문서 검사 + 실제 `/v1/rag/ask` 진입점 검사 1개 이상. 엔진 고정값 갱신 |
| 5 | **MVP-1 실행.** 37문항 × 3조건, Qwen3.8, 한 번에 하나씩 순차 실행 | 지표 집계, 실패 보존, `validate --final`·`graph` |
| 6 | **MVP-2 제안 단계.** 실행 뒤 판단 기록 → 묶음·스키마 제안 JSON(코드로 형식·원문·판단 ID 검사, 1회만 다시 요청) → 사용자 검토 → 받아들인 것으로 재실행 | 새 ADR로 기록 |

## 지킬 것

- MAIN103 릴리스·선택 포인터·GENOS는 바꾸지 않는다. MAIN 반영은 사용자가 따로 지시한다.
- 사용자 확정(2026-10-24): 승인 묶음도 **기존 조사 범위 안에서만 읽는다**. 범위 밖 조항은 미확보로 표시하고, 온톨로지 관계를 새 범위 확장의 근거로 쓰지 않는다. 문서 접근권한도 유지한다.
- 무거운 실행은 한 번에 하나만 한다. 실행 전 RAM·디스크를 확인한다.
- 다른 세션과 작업 트리를 함께 쓴다. `git stash`를 쓰지 않고, 커밋·푸시는 지시가 있을 때만 한다.
- 모델 출력은 제안이다. 조항 ID·판본·판단 ID는 서버가 실제 기록에서 붙인다.
- 사용자 확정(2026-10-24): 시험 문항은 **현재 37개**로 고정한다. 약 60개로 확대하지 않는다([MVP.md 표본 수](MVP.md#표본-수)). 진행 중 설계가 모호하면 작업을 멈추고 사용자에게 확인한다.
- 완료 보고에는 작업 코드·ADR 후보·MAIN103·GENOS 상태를 구분해 적는다.

## 구현·승인 이력 — ADR-1041

ADR-1041의 `compiler-r4/rev-001` 후보에서 컴파일러·도착 시 전달을 구현했고 88개 합성 검사가 통과했다. **미확인을 보존한 31개 초안의 실험용 승인은 유지한다.** [승인 기록](../../../../01_DATA/ONTOLOGY_WORK/review/ADR-1041/APPROVAL_20261024_MVP37_R1.json)과 [승인 스냅샷](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/approved-bundles-20261024-r1.json)을 사용하며 원본 CANDIDATE와 HEAD는 바꾸지 않았다. 이후 FSC 7문항의 현재 기준답변 재검토를 위해 실험을 보류했던 [기록](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/experiment-hold-fsc-reference-review.json)은 이력으로 보존한다. [구현 기록과 남은 작업](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/IMPLEMENTATION.md), [검토표](../../../../01_DATA/ONTOLOGY_WORK/review/ADR-1041/SEED_REVIEW.md)도 참고한다. 초기 `compiler`·실패한 `compiler-r2`·중간 `compiler-r3` 후보 대신 최종 결속 기록을 사용한다. MVP-2 제안 단계·MAIN 승격은 완료되지 않았다.

당시 사용자 결정은 **현재 데이터를 유지하고 FSC 7문항의 검토 기준답변을 채택하여 37문항 × 3조건 실험을 재개하며, 미확보를 별도 평가**하는 것이다([재개 승인 기록](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/execution-authorization-20261024-r1.json)). 앞선 법령 보충 선택은 즉시 대체됐고 반입은 수행하지 않았다. [재검토표](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/FSC_CURRENT_REFERENCE_REVIEW.md)의 최소 핵심 기준·보충 설명·미확인은 [평가 전용 자료](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/cases-evaluator-r1.json)로 결속했으며 제품 입력에 넣지 않는다. FSC003에 필요한 상호저축은행법·개인채무자보호법은 현재 세대에 없는 상태를 보존하고, 미확보만으로 답변 전체를 자동 오답 처리하지 않는다. [데이터 결속 기록](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/dataset-freeze-r1.json)은 `READY_FOR_DESIGN_FREEZE`다. 설계 동결과 실행은 준비 중이며, 이 기록 시점의 실모델 호출은 0회다.


최종 실행 후보 보완: `compiler-r5/rev-001`의656파일로 A0/A1/A2를 연결하며102검사가 통과했다. 승인된 CM 질문을 공개로 잘못 표시하지 않도록 새 독립 세션의 반출 승인 연결을 보완했고, 기존 private history는 허용하지 않는다. 상세는 [구현 기록](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/IMPLEMENTATION.md)의 마지막 절을 따른다. r4와 이전 검사 이력은 보존한다.


실행 상태 갱신: 승인된 현재 데이터 선택과 FSC 기준답변으로 111회 순차 실험을 시작했다. [실행 동결](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/design-freeze.json)과 [실행 전 검사](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/execution-ready-r1.json)가 정본이다. 시작은 완료·성능 통과를 뜻하지 않으며, 실제 완료·중단 상태는 matrix-progress.json 및 matrix-stop.json에 기록한다.


ADR-1041 중단 당시 상태: 첫 문항 A0의12번째 모델 전송에서 연결 오류로 중단했다. 완료0/111이며 자동 재시도하지 않았다. 당시 사용자에게 같은 조건의 새 실험 기록으로 처음부터 재실행할지 확인했다. [중단 기록](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/STOP_REVIEW.md)은 보존한다.

## 실행 이력 — ADR-1042 중단

사용자가 동일 조건 재실행을 승인했다. [ADR-1042](../../../../04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/README.md)에서 제품 코드·현재 데이터·승인 묶음 31개·37문항·평가 기준·모델·예산을 유지하고 새 실행 식별자와 경로로 111회를 처음부터 순차 실행하기 시작했다. 동결·실행 전 연결 확인·ADR 검사는 통과했으며 제품·실행 도구를 추가 수정하지 않는다.

새 실행의 정본은 [재실행 승인](../../../../04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/artifacts/restart-authorization.json), [동결 설계](../../../../04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/artifacts/design-freeze.json), [실행 전 확인](../../../../04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/artifacts/execution-ready.json), [실행 도구 동일성](../../../../04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/artifacts/runner-identity.json), [질문 인덱스](../../../../04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/실험/README.md)다. 실행기는 `06_TOOLS/EXPERIMENTS/adr_1042/run_matrix.py`, 산출물은 `04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/artifacts/`에 둔다.

첫 문항 A0의 12번째 모델 호출이 제공자 HTTP 400의 문맥 길이 초과 오류로 실패하여 실행을 중단했다. 완료 0/111, 제품 호출 시도 12회 중 정상 응답 11회이며 실패 호출의 사용량은 미확인이다. 평가 모델 호출은 0회다. 제공자 오류에는 `input at least 131073 + output 131072 > max 262144`가 표시됐다. 중단 당시 원인 분석과 다음 실행 방식에 대한 사용자 확인을 기다렸다. 이후 입력 구성 수정·검증 후 재실행 승인을 받아 ADR-1043으로 분리했고 출력 상한은 계속 없다. [중단 검토](../../../../04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/artifacts/STOP_REVIEW.md)와 [결과 기록](../../../../04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/artifacts/RESULT.md)을 따른다. 기존 ADR-1041 산출물·MAIN103·GENOS는 변경하지 않는다.

## 최신 인계 — ADR-1043 스키마 간소화 범위 사용자 확인 대기

**현재 상태 — 2026-10-24 11:49:33 UTC:** 스키마 필수 응답 항목과 실패 처리의 **간소화 범위를 사용자에게 확인하는 중**이다. `matrix-stop.json`에 `SCHEMA_CONTRACT_DECISION_REQUIRED`를 기록하여 추가 모델 호출을 차단했다. 이는 사용자 확인을 위한 중단이며 제공자·실행기 장애로 분류하지 않는다. 6/111이 종료됐고, 그중 4개는 서비스 응답, 2개는 `NATIVE_BOUNDED_FAILURE`다. 서비스 응답은 의미 정확도 통과를 뜻하지 않는다. 7번째 실행은 중단 처리와 프로세스 회수를 완료했다. 부모 실행기는 exit 2로 종료됐고 시작한 7개 실행 모두 `process_reaped=true`를 확인했다. 중단 이후 추가 모델 호출은 0회이며 결과 보고서를 생성했다. **111회는 미완료이며 품질 비교도 미확정**이다.

첫 A1에서 공백·CR·LF가 반복된 미완성 JSON이 `finish_reason=length`로 끝난 사실은 확인했다. 스키마 자체 모순, 스키마 복잡성 또는 제공자 디코더가 이 반복을 일으켰다는 인과관계는 아직 확정하지 않았다. 사용자에게 제시한 범위는 중복 판단 설명 정리, 이미 선택한 근거 ID의 서버 합산, ASSESS 최종 검토의 변경분 중심 기록, 보조 검토 결속 오류의 분리 처리다. 이는 단순 표현 압축을 넘어 필수 응답 항목과 실패 처리 계약을 바꾸는 제안이며, [관찰·간소화 범위](../../../../04_EXPERIMENTS/ADR/ADR-1043-ontology-mvp-input-budget/artifacts/SCHEMA_CONTRACT_FOLLOWUP.md)를 따른다. 현재 동결 코드·기존 결과·평가 기준은 변경하지 않는다. 출력 상한 없음, 현재 데이터·조사 범위·승인 묶음 31개·37문항과 MAIN103·GENOS 상태를 유지한다. 사용자 확인 이후의 구현·검증·새 실험은 별도 기록한다.

사용자가 **출력 상한 없음**을 유지하며 입력 구성·스키마 최적화를 검증한 뒤 37문항 × 3조건을 새로 실행하도록 승인했다. [ADR-1043](../../../../04_EXPERIMENTS/ADR/ADR-1043-ontology-mvp-input-budget/README.md)에서 같은 현재 데이터·승인 묶음 31개·평가 기준·조사 범위를 유지한다. FSC003의 미확보 두 법률은 추가하지 않는다. ADR-1041/1042는 `abandoned`로 종료했고 실패 원문과 예산 이력을 보존한다.

새 후보 `compiler-r6`와 `compiler-a1-r6`의 동일 661파일을 `rev-001`로 동결했다. [제품/API 합성 검사 188개](../../../../04_EXPERIMENTS/ADR/ADR-1043-ontology-mvp-input-budget/artifacts/compiler-r6-contracts-01-validation.json)와 [보충 지표 검사 9개](../../../../04_EXPERIMENTS/ADR/ADR-1043-ontology-mvp-input-budget/artifacts/host-excerpt-metrics-validation.json), 총 **197개가 통과**했다. 사전 검증의 외부 모델 호출은 0회였으며 후보 밖 runtime import도 없었다. 과거 r5의 102개 통과를 새 후보 검증으로 상속하지 않았다.

저장된 ADR1042 실패 요청의 정적 비교에서 출력 스키마는 canonical UTF-8 **15,858 → 13,787바이트(13.06% 감소)**, 조사 화면 view는 **338,737 → 317,363바이트(6.31% 감소)**였다. 후자는 system/schema를 제외한 user view 측정이다. 바이트는 토큰이 아니며 이 결과만으로 실제 문맥 수용·토큰 절감·답변 품질을 확정하지 않는다.

기존 `max_context_chars=100000`을 이제 system·schema·수정 피드백·제공자 필드를 포함한 **최종 전송 요청의 canonical 문자 수**에 적용한다. 이전 부분 화면 검사보다 엄격한 동작 변경이다. 전송과 같은 preview로 물리 호출 예약 전에 검사하며, 초과 사유·남은 예산·deadline은 저장·재개 시 유지한다. 보내지 않은 원문을 모델 전달로 표시하지 않는다. ASSESS 입력 초과는 `INCOMPLETE`/법률 주장 0개와 검증된 원문 발췌만 남기고, COMPOSE는 스트리밍 전 이미 검증된 판단만 결정적으로 표시할 수 있다. 상세 [실패 계약](../../../../04_EXPERIMENTS/ADR/ADR-1043-ontology-mvp-input-budget/artifacts/DESIGN.md)을 따른다.

초기 실행 이력: [실행 설계](../../../../04_EXPERIMENTS/ADR/ADR-1043-ontology-mvp-input-budget/artifacts/design-freeze.json)를 동결하고 **111회 순차 실험을 시작했다**. 2026-10-24 11:23:40 UTC 확인 시 첫 A0는 제한 종료, A1 실행 중; 실행 종료 1/111이었다. 당시 호출 영수증에서 A0의 5회와 A1의 1회, 총 6회 물리 호출을 확인했다. 첫 A0는 `NATIVE_BOUNDED_FAILURE`로 종료한 것이며 정답·품질 통과를 뜻하지 않는다. 이후 진행·완료·중단은 `artifacts/matrix-progress.json`, 각 셀의 `result.json`, `matrix-stop.json`이 정본이다. 실행기는 `06_TOOLS/EXPERIMENTS/adr_1043/run_matrix.py`이며 중복 실행하지 않는다. **완료·품질 결과는 미확정**, MVP-2·MAIN103·GENOS 상태는 바뀌지 않았다.
