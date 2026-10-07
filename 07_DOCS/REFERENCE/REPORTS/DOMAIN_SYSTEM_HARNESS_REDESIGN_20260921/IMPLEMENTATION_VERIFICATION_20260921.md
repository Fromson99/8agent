# 수정 설계서 전체 기준 v4 구현 검증

2026-09-21. **로컬 v4 구현 및 모의 계약 검증 완료. 전체 TO-BE 전항목 충족, 실제 출처 품질 개선, MAIN 승격, GENOS 배포 완료를 뜻하지 않는다.** 아래 부분 충족 항목을 남긴다. 후속 실제 Qwen 검증은 [QWEN_VERIFICATION_20260921.md](QWEN_VERIFICATION_20260921.md)에 있으며 출처 품질 목표 미달이다. 수정 설계서와 이전 완료 실험은 변경하지 않았다.

## 1. 검증 binding

| 항목 | 값·근거 |
|---|---|
| 대상 설계 | SOURCE_TIERS_REVISION.md 전체 1~10절; SHA-256 `11e67b81ba971a16f70d3b8fd277f98b05a0a628c507832803cc3a10472473bd` |
| 환경·검증자 | WSL `/home/jin/8-AGENT`, 저장소 `.venv/bin/python`, Codex. 실제 내부 데이터·GENOS 접속 없음 |
| 코드 HEAD | `a3ac254cc8fba708e39cf37482707a5570fd388d` + 기존 변경 및 이번 변경이 있는 작업 트리 |
| 재현 binding | [implementation-binding.json](../../../../09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/implementation-binding.json), SHA-256 `5b2a961e5809bf86568e51c8f65c8e48b9a37ff4ec926a17490831d36c071874`. v4 엔진 의존 파일·schema·profile·테스트·service·workflow 해시 및 dirty 목록 |
| 실제 진입점 | FastAPI TestClient `POST /v1/rag/ask` → Pipeline → 기존 StageRunner/Coordinator → TiersSession → prepare/export → Result. `legal-agent-tools-v4` / `legal-agent-rag-v4` |
| source/index/glossary | 각 테스트가 구축한 **모의 원문 세대**, scope `d`. 각 시나리오의 manifest·journal binding과 [대표 실행](../../../../09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/representative-run.json)에 실제 generation/hash 저장 |
| domain/profile/schema | domain-v4 / profile-tools-v4 / source-tiers-v4. 해시는 implementation-binding 및 journal의 binding에 결속 |
| 모델 | provider `fixture`, model `synthetic-contract`, endpoint `no-network`, trust_zone `internal`. 실제 Qwen 응답 아님 |
| ADR/arm/run/gold | 적용 없음. 결정론적 계약·회귀 검사이며 모델 실험·regrade·품질 비교를 수행하지 않음 |
| 기본 한도 | CORE 5 / SUPPLEMENTAL 5 / 카드 발췌 1,600자 / 원문 페이지 4 / 관계 메뉴 12 / wire byte 상한은 model binding. 기본 모델 14회·종료 예약 3·짧은 선택 최대 2·도구 56·세션 300초 |
| 모의 검사 한도 | 통상 모델 16회, 테스트별 READ·페이지·tier 한도 축소. 500,000-byte 모의 deployment binding |
| 대표 compose 실패 실행 | 물리 모델 시도 6/16, 도구 8/56. 실제 전송 JSON bytes: 34,442 / 36,003 / 41,387 / 12,063 / 19,668 / 20,034. 마지막 두 호출은 compose/schema repair 실패이며 출처 1개 보존 |
| 현행 engine binding | [검사 결과](../../../../09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/engine-check.json): stale engine 0, stale schema 0, 검사 대상 데이터 pin 일치 |

모의 전송량·호출 수를 실제 Qwen 비용·지연·선택 능력으로 해석하지 않는다. 초기화 후 시작하는 기존 세션 deadline을 사용하므로 전체 E2E 300초를 보장하지 않는다.

## 2. 실제 구현과 소비자

- [tiers_protocol.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tiers_protocol.py): 별도 SourceSelectionDecision / FinalSourceBundle. 질문 전체 goal과 revision, view, 제시 span ID, tier, 관련성 이유, 독립 해석 상태.
- [tiers_session.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tiers_session.py): 명시 선택 검증·version 저장·재선택·무진전 판단·짧은 최종 선택·claim과 독립 bundle. 선택 이력이 없는 자료는 최종 출처에 추가하지 않음.
- [tiers_views.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tiers_views.py), [tiers_tools.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tiers_tools.py): 제한된 현재 뷰, exact source 범위, 의미 label을 보존한 관계 메뉴, 큰 관계의 lossless JSON 상세 페이지. 상세 fragment를 canonical relation으로 저장하지 않음.
- [tiers_repository.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tiers_repository.py), journal-v4.sql: 기존 원장에 독립 source_selection/source_bundle version과 상세 제시 기록 추가. 기존 v3 journal은 유지.
- [source_bundle.py](../../../../02_BACKEND/semantic_runtime/legal_agent/source_bundle.py), publication.py: 선택 revision·bundle·outbox hash 대조, 현재 Store/범위/문서/원문 검증. 현재 검증 callback 없는 v4 복구를 차단.
- [app.py](../../../../02_BACKEND/semantic_runtime/app.py), [source_tiers_ui.py](../../../../02_BACKEND/semantic_runtime/legal_agent/source_tiers_ui.py), [GENOS renderer](../../../../08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py): source bundle 표시, 빈 answer에서도 카드 유지, 서버가 만든 원문 열기, 미열람·미채택 후보 메뉴.

v4는 기존 v3 법적 평가·claim review를 그대로 추가 조건으로 사용한다. source 선택만으로 ADOPT/SUPPORT나 법률 해석 승인을 생성하지 않는다. 모델이 REVIEWED를 제안하면 독립 검토 기록을 요구한다. 구현 선택은 개별 evidence/span 배열이며 evidence_group_id 자동 확장은 없다. 같은 결정에서 원칙·예외를 각각 CORE로 선택할 수 있다.

## 3. 실행 결과와 시나리오

최종 [contract-run-05 결과](../../../../09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/contract-run-05/pytest.txt): **24 passed**. [JUnit](../../../../09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/contract-run-05/pytest.xml), [테스트 코드](../../../../05_TESTS/CONTRACTS/test_source_tiers_v4.py). 앞선 contract-run-01~04는 개발 중간 검증 이력이며 덮어쓰지 않았다.

공통 명령:

```bash
SOURCE_TIERS_EVIDENCE_DIR="$PWD/09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/contract-run-05" \
PYTHONPATH=02_BACKEND .venv/bin/python -m pytest \
  05_TESTS/CONTRACTS/test_source_tiers_v4.py -q --disable-warnings --tb=short
```

재실행 시 기존 증거 디렉터리를 덮어쓰지 말고 새 run 디렉터리를 지정한다.

| 시나리오 | 실제 실행·결과 | 증거 위치: contract-run-05 아래 테스트 이름 |
|---|---|---|
| T01 | UNCERTAIN CORE, claims=[] 상태에서도 API·outbox·원문 열기·renderer 출처 유지 | `test_T01_T06_T10_http_bundle_outbox_renderer[normal]` |
| T02 | 모의 원칙·직접 연결 예외 두 원문을 같은 모델 결정에서 CORE 선택. 둘 다 bundle 보존 | `test_T02_principle_exception_both_core`; 실제 Qwen CM003 선택 아님 |
| T03 | CORE 한도 초과 거부, 일부만 선택, 미채택 자동 추가 없음, 동일 범위 중복 tier 거부, 빈 후속 결정에서 기존 선택 유지 | `test_T03_limits_no_automatic_sources`, `test_T03_duplicate_tier_rejected_and_existing_survives_empty`, `test_T03_unread_discoveries_in_tier3_not_sources` |
| T04 | 미제시 span·다른 ID·성공 응답 없는 READ·독립 검토 없는 REVIEWED 거부 | `test_T04_unpresented_span_and_reviewed_rejected`, `test_T04_read_without_successful_presentation_cannot_select`, family 메뉴 반례 |
| T05 | 반복 READ 뒤 예약된 짧은 선택 단계 실행, 총 모델 한도 안에서 종료 | `test_T05_T09_bounded_recovery_and_no_selection[repeat]` |
| T06 | compose 및 형식 수정 실패 후에도 기존 모델 선택 유지, 미검토 claim 발행 없음 | `test_T01_T06_T10_http_bundle_outbox_renderer[compose_failure]` |
| T07 | 긴 READ 페이지 연결 결과가 원문과 일치. 큰 관계 상세 fragment 합계가 canonical relation JSON과 일치. 메뉴를 원문으로 채택할 수 없음 | `test_T07_exact_read_pages_and_unseen_selection`, `test_T07_oversized_relation_lossless_detail_pages`, 6 family parameterized 검사 |
| T08 | 선택 revision 변경 시 이전 bundle 거부. COMMIT_READY 복구의 현재 권한 callback 필수·중복 export 동일 결과. RUNNING 중단은 선택 이력 보존. manifest 범위 변경 뒤 원문 열기 차단 | `test_T08_*` 4개. 범위 변경 시 카드별 재발행은 미완료 |
| T09 | 반복 빈 선택·모든 원문 rejected에서 NO_SELECTION, 회수 자료 자동 채택 없음 | `test_T05_T09_bounded_recovery_and_no_selection[empty]`, `test_T09_rejected_sources_not_filled_automatically` |
| T10 | 신규 opt-in 실제 HTTP 진입·StageRunner·journal v4·outbox·renderer 연결. use_llm=false 목록은 추가 모델 호출 0 | `test_T01_T06_T10_http_bundle_outbox_renderer` 2개 |

각 테스트 디렉터리에 실제 SQLite journal과 생성 manifest를 보존했다. HTTP 시나리오는 `contract-wire.json`, `contract-result.json`, `contract-genos.md`, `contract-screen.html`도 보존한다. [대표 trace](../../../../09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/trace.json)는 기존 trace 도구로 읽은 COMPLETED 원장의 이벤트·모델 선택 version이다.

로컬 화면 증거는 [브라우저 DOM](../../../../09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/contract-run-05/local-renderer.dom.html)과 [스크린샷](../../../../09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/contract-run-05/local-renderer.png)이다. 실제 API 응답을 동일 제품 DOM renderer에 넣어 Chromium headless에서 렌더했다. 서버가 저장한 bundle_hash와 DOM의 data-bundle-hash를 연결한다. GENOS 현장 캡처가 아니며, 원문 열기 HTTP 응답은 별도 TestClient 검사다.

## 4. 요구별 판정

‘충족’은 아래 명시된 **로컬 모의 계약 환경**의 코드·실행 검증에 한정한다. 아래 표는 최초 모의 검증 시점의 판정이다. 후속 실제 Qwen 결과는 6절에서 갱신하며 GENOS 현장 품질은 계속 미검증이다.

| 요구 ID | 시나리오 | 코드·계약 증거 | 실행·저장·화면 증거 | 판정 | 미확인/제약 |
|---|---|---|---|---|---|
| D01 | T01·T06 | 별도 선택·bundle, 기존 claim review | HTTP 정상/compose_failure의 wire·journal·Result·DOM | 충족 | 실제 모델 해석 능력 별도 |
| D02 | T01·T03·T04·T09 | 제시 span·goal/view/revision 검증, 자동 채택 없음 | 선택 event → bundle ID, 잘못된 span·빈 선택 반례 | 충족 | 모델이 관련 원문을 잘 고르는지는 미검증 |
| D03 | T02 | tier와 interpretation_status 독립 | 두 CORE/UNCERTAIN 및 SUPPLEMENTAL 변경 기록 | 충족 | 모델 confidence 점수로 tier를 계산하지 않음 |
| D04 | T02 | 동일 결정에서 원칙·예외 개별 선택 가능 | 두 원문 명시 선택과 bundle 2개 | 부분 충족 | CM003 실제 Qwen의 공동 선택·최종 품질은 미실행 |
| D05 | T05·T09 | pending/rejected, 짧은 최종 선택, 해석 배열 비우기 | 반복/빈 선택/모두 rejected 실행 | 부분 충족 | 실제 Qwen 성공·실패 기록은 없음; pending/rejected는 READ evidence 단위 |
| S01 | T03·T07 | 제한된 현재 뷰·원문/관계 cursor·wire byte 검사 | 실제 request JSON과 이어보기 원문 일치 | 충족 | 전체 E2E 시간·실제 모델 토큰 비용 미측정 |
| S02 | T02·T07 | 6 family 이름/좌표/이유 메뉴, 큰 관계 별도 상세 | 6 family 모의 fixture, 상세 fragment 완전 재구성 | 부분 충족 | 실제 전체 glossary/source 지형에서 모든 label·관계 소비자 확인은 미실행 |
| S03 | T05·T09 | 정보 변화 hash·탐색 종료·예약 선택 | 반복 action/모델 시도·선택 상태·NO_SELECTION | 충족 | 성공 선택을 보장하지 않음 |
| S04 | T01·T04·T07 | 서버 문서명·조항 surface/title·판본·span/hash·열기 | 실제 저장 원문 대조·원문 API·좌표·미제시 거부 | 충족 | 범위는 실제 READ span 단위; 호 단위 의미 관련성은 별도 평가 |
| S05 | T01·T06·T10 | 독립 FinalSourceBundle + publication validation | 동일 선택 version·bundle_hash를 outbox/Result/DOM에 연결 | 충족 | 요약 없음이 출처 없음의 조건이 아님 |
| S06 | T03·T09 | tier/발췌 한도·미채택/rejected 기본 제외·발견/READ 후보 메뉴 | 한도 거부·선택 부분집합·미열람 후보·NO_SELECTION | 충족 | 후보 메뉴와 기본 채택 출처를 분리 |
| S07 | T08·T10 | v4 journal·선택 revision·bundle hash·현재 Store guard | 중단/멱등 복구/선택 변경/범위 변경 차단 | 부분 충족 | 사용자별 ACL 제공자 미연결. scope 변경 시 전체 outbox 차단; 카드별 정제·재발행 미완료. RUNNING 자동 모델 재개 없음 |
| S08 | T01·T06·T10 | 로컬 DOM·GENOS workflow renderer 분기 | 실제 로컬 DOM/스크린샷·모의 GENOS render 문자열 | 부분 충족 | GENOS 원문 링크 인증·라우팅·최종 화면과 내부 모델은 미검증 |

따라서 “v4 주요 실행 경로를 로컬에서 구현·계약 검증했다”까지 보고한다. 현재 상태를 “전체 요구를 모든 환경에서 충족했다”로 표시하지 않는다.

## 5. 회귀와 남은 작업

[확장 회귀 결과](../../../../09_ARTIFACTS/AUDITS/20260921-source-tiers-v4/regression.txt): v1/v2/v3 하네스·paging·실패·엔진 재해시 검사 **94 passed, 2 failed**. 실패는 아래 기존 계약 불일치이며 통과로 숨기지 않는다.

- `test_trailing_parenthetical_context_stays_with_the_question`: 질문 뒤 괄호 문맥을 단일 Q1으로 기대하지만 기존 question_pieces는 Q1/Q2로 분할한다.
- `test_initial_source_trigger_aliases_matching_unassessed_question_issue`: v1의 질문 issue와 source-trigger issue의 ID 통합을 기대하지만 현재 구현은 분리한다.

관련 `context.py`와 `updates.py`는 수정하지 않았으며 각각 설계 BASELINE.json의 `c24e1a3e…34375`, `475dfaa1…0d8d`와 전체 SHA-256이 일치한다. 이 불일치를 고치려고 기존 v3 동작을 함께 변경하지 않았다. v4 source 선택 goal은 질문 원문 전체에 결속한다.

남은 구현·연결 범위는 현재 권한 제공자 연결 및 카드별 stale 처리/재발행, 실제 데이터의 관계 메뉴 확인이다. GENOS 반입에서는 내부 모델 binding·브라우저 접근 가능한 원문 URL·권한을 연결하고 동일 시나리오를 현장 실행해야 한다.

최초 모의 검증 시점에는 수정 설계서 6절의 단일 ADR 통합 Qwen 비교가 미실행이었다. 아래 6절의 후속 배치에서 실행했다. 당시 남겼던 실행 조건은 다음과 같다. v3/v4 동일 K·공개 승인 범위·질문·세대·FP8/thinking off·총예산으로 사전 동결한 뒤 별도 배치를 수행해야 한다. 기존 실험을 재채점하거나 CM003 결정 조항을 제품 입력에 주입하지 않았다. 설계 구현, 출처 recall/precision·관련성·무결성, 법적 정답률, MAIN 승격, GENOS 배포는 각각 별도 판정이다.

## 6. 후속 실제 Qwen 검증

[Qwen 결과](QWEN_VERIFICATION_20260921.md) · [ADR-0488](../../../../04_EXPERIMENTS/ADR/ADR-0488-qwen-source-tiers-v4-paired/README.md). 같은 공개세대·Qwen·총예산으로 v3/v4 각6회 실제 실행했다. 기준답 일치 양쪽0/6, v4 내부 카드가 남은 실행2/6, 실제 게시0/6. 모의24개 통과가 실제 품질 개선을 입증하지 않았다.

D04 실제 원칙·예외 선택 품질은 미충족이다. S03은 CM018 후보 발견 직후 조기 종료와 복구 실패가 드러나 실제 환경 기준 부분 충족으로 낮춘다. D01/D02/S04/S05의 내부 명시 선택·정확 보존은2건에서 확인했지만 S07/S08의 외부 실험 게시 경로는 반출 binding 충돌로 미충족이다. 이전 모의 계약 이력은 위에 보존한다. 실제 GENOS는 여전히 미검증이다.
