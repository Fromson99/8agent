# 근거 결속 실패 진단과 개선 검증

2026-10-05 작업 코드에 EvoOntology에서 착안한 오프라인 개선 흐름을 추가했다.
입력은 기존 native v5/v6 요청 journal이며, 별도 온라인 조사 엔진은 만들지 않는다.
기존 `action-memory` CLI에서 진단·후보·비교 계획·판정을 실행한다.
서빙 코드·활성 릴리스·MAIN 포인터·GENOS 배포는 변경하지 않았다.
후보 JSON은 실행 코드나 승인된 온톨로지가 아니다.

| 단계 | 입력 → 출력 | 연결된 소비자 | 현재 상태 |
|---|---|---|---|
| 진단 | terminal journal → hash 결속 trace·diagnosis | `action-memory propose`, v6 golden adapter | 구현·모의 계약·로컬 v5 로그 확인 |
| 수정 제안 | 확인된 partial/truncated/empty_selection → 단일 Tool 층 proposal | 후속 ADR 설계·사람 검토 | 구현; 실행 실패의 미확인 원인은 제안하지 않음 |
| 평가 연결 | frozen golden·저장 v6 답변·명시 journal → 단계별 score | 기존 golden review/report 및 batch scorer | 구현·모의 v6 요청 확인; 답변 품질은 미검토 |
| 독립 비교 | 동결 split·동일 조건·검토한 Parent/Candidate 결과 → paired gate | 후속 ADR 결과·별도 MAIN 승격 절차 | 형식·회귀·품질·비용 판정 구현; 실제 품질 비교 미실행 |
| 제품 적용 | 검증한 코드 snapshot → 명시 배포·원복 | MAIN·GENOS | 이 구축의 대상 밖; 자동 적용 경로 없음 |

## 실제 호출 경로와 계약

`06_TOOLS/pipeline.py action-memory` → `lawrag.pipeline.action_memory.main`
→ `failure_improvement.main` → `native_trace.read_trace`.
`golden score-native` → `golden.score` → `native_result_stages`는 같은 projector를 쓴다.
온라인 Pipeline/Coordinator는 새 모듈을 import하지 않는다.
기존 `action-memory build/status/wiki-*`와 legacy golden scorer는 유지한다.

`native-failure-trace-v1`은 journal 버전, run·세대·scope binding, 논리 snapshot hash,
원문 span 좌표·해시, 성공한 호출의 presentation, 단계·사건 refs, 사용량을 담는다.
`failure-diagnosis-v1`은 trace hash와 issue refs에 결속하고,
`failure-improvement-proposal-v1`은 진단·trace·binding 및 변경할 층 하나에 결속한다.
각 artifact는 `content_sha256`으로 확인하고 원자적 no-replace 저장을 사용한다.
동일 입력의 재실행은 기존 bytes를 보존한다. 새 feedback이나 변경된 journal은 새 진단이다.
제안 직전 source snapshot을 다시 읽어 진단 이후 변경은 거부한다.
후속 회귀 검사에서 진단의 confirmed issue를 trace 원본 관찰과 대조하도록 보완했다.
stage payload는 CASE_JUDGMENT_ACCEPTED 사건의 stage·payload hash와 일치해야 하고,
observation은 원 요청·binding key·result status·생성 사건과 일치해야 한다.
진단 projector를 갱신해 같은 journal의 해석이 달라진 경우에도 재진단을 요구한다.

읽기는 SQLite read-only transaction 하나에서 수행한다. WAL에 남은 committed 행도 논리
snapshot에 포함한다. `RUNNING`·`COMMIT_READY`는 보류한다. 해시·세대·scope 불일치,
빠진 evidence/presentation target, 지원하지 않는 버전은 수집하지 않는다.
순간적 읽기 잠금·파일 오류는 PARTIAL과 error type으로 남긴다.
원문·질문·모델 입출력·feedback 이유·인증키는 새 진단 JSON에 복사하지 않는다.
다만 문서 ID·주체 정보·로컬 경로와 해시도 내부 메타데이터일 수 있으므로 디렉터리는
0700, 파일은 0600으로 저장하며 이 산출물 자체가 외부 반출 승인을 부여하지 않는다.

검색 ID의 존재, 원문 acquisition, 모델 delivery, 최종 citation은 서로 다르다.
stage receipt가 없는 최초·첫 열람·선택은 null로 유지한다. 기록에 없는 토큰·비용도 null이다.
`CURRENT` stage의 origin이 있으면 `stage_refs.*.inherited=true`로 표시한다.
successful model attempt에 연결된 presentation만 전달 근거로 집계한다.
read의 같은 target·extent에서 이후 coverage.complete=true인 OK receipt가 있으면
앞선 PARTIAL/TRUNCATED 관찰을 resolved로 표시하고 수정 후보에서 제외한다.
정상적인 페이지 나누기 자체를 미해결 실패로 처리하지 않는다.
span을 확보했다는 사실이 완독·의미 지지·법률 정답을 인증하지 않는다.
diagnosis의 `legal_quality`는 항상 UNKNOWN이다.

## 로컬 실행

WSL `/home/jin/8-AGENT`에서 실행한다. 출력 경로는 workspace 논리 root
`runtime`에서 해결되며 현재 로컬 매핑이 `90_RUNTIME`이다. 다른 환경에서는
`--runtime`과 `--output`을 해당 환경의 명시 경로로 지정한다.
새 LLM 호출이 없으므로 기존 야간 `build`의 시간 제한은 이 명령에 적용하지 않는다.
기존 예약 작업은 `build`를 실행하며, 새 `diagnose` 자동 예약은 추가하지 않았다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py action-memory diagnose \
  --root /home/jin/8-AGENT --limit 100 \
  --output /home/jin/8-AGENT/90_RUNTIME/semantic/action-memory/failure-improvement

.venv/bin/python 06_TOOLS/pipeline.py action-memory propose \
  --diagnosis /절대경로/diagnoses/선택한진단.json \
  --output /home/jin/8-AGENT/90_RUNTIME/semantic/action-memory/failure-improvement/proposals

.venv/bin/python 06_TOOLS/pipeline.py golden score-native \
  --suite /절대경로/frozen-suite.json --case-id 선택한문항ID \
  --response /절대경로/저장된응답.json --journal /절대경로/journal.sqlite \
  --output /절대경로/score.json
```

진단은 기본적으로 정렬한 journal 목록의 앞 `limit`개를 선택한다.
특정 기간이나 실패만 필요하면 `--journal`을 반복해 입력 집합을 명시한다.
명시 입력도 limit를 초과하면 거부한다. 원래 요청 디렉터리 안에는 출력을 쓰지 않는다.
진단 출력의 reports JSON은 records/errors/deferred와 각 diagnosis 경로를 담는다.
CLI 종료코드는 정상·보류만 있으면 0, 읽기·형식 실패는 1이다.

v6 평가에서는 frozen golden의 문항·세대와 답변의 run·scope·질문·publication answer hash,
선택·인용 ID를 대조한다. 완료한 journal을 명시하지 않으면 채점하지 않는다.
정정·표시 변경 요청은 원 입력과 실행 query가 다를 수 있으므로 저장된 publication의
query 및 전체 response hash를 대조한다. 새 SELECT를 실행하지 않은 후속 답변의 선택은
publication assembly에서 복원하고 selection_basis=PUBLISHED_ASSEMBLY를 남긴다.
이때 최초 검색/첫 열람의 미측정 상태는 유지하고 선택 source의 현재 확보 evidence를 확인한다.
native score는 `answer_quality=PENDING_HUMAN_REVIEW`를 남긴다.
기존 `golden_run.run_cases(..., native_journal_resolver=...)`에서도 동일 adapter를 쓸 수 있다.
자동으로 다른 날짜·run의 journal을 추측해 연결하지 않는다.
이 변경은 GENOS batch 실행 기본 구현을 v6로 바꾸지 않는다.

## 비교 계획과 판정 형식

후속 후보 구현·실험 호출 전 새 ADR을 선점하고 기준 전체 파이프라인과 완료 Parent arm,
candidate snapshot·register·freeze, 모델·데이터·평가 조건을 표준대로 동결한다.
이번 ADR-0637은 오프라인 구축 audit이며 제품 Parent 정답 기준으로 재사용하지 않는다.

`failure-comparison-design-v1` 필수 필드:

| 필드 | 계약 |
|---|---|
| experiment_id, parent_arm, candidate_arm | 새 ADR과 그 arm 식별자. Parent와 Candidate는 다름 |
| generation_id, store_sha256, model | 정확한 데이터 세대·store hash·모델 ID |
| decoding_hash, budget_hash, evaluator_hash | 고정한 디코딩·자원 제한·채점 정책 SHA-256 |
| parent_code_hash, candidate_code_hash | 각각 동결한 전체 파이프라인 코드 hash |
| splits | construction/validation/holdout 각각 비어 있지 않은 `[{case_id,family_id}]` |
| criteria | min_net_wins 정수 ≥1, max_regressions 정수 ≥0, max_p95_ratio/max_cost_ratio 양수 |

case ID는 모든 split에서 중복할 수 없고 같은 family는 서로 다른 split에 들어갈 수 없다.
같은 계열 질문의 표현만 바꾼 사례를 독립 holdout으로 계산하지 않는다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py action-memory comparison-plan \
  --design /절대경로/design.json --output /절대경로/plan.json
.venv/bin/python 06_TOOLS/pipeline.py action-memory compare \
  --plan /절대경로/plan.json --parent /절대경로/parent-results.json \
  --candidate /절대경로/candidate-results.json --output /절대경로/gate.json
```

양 arm 결과는 `failure-comparison-results-v1` + `content_sha256`으로 seal한다.
plan_sha256/arm_id/code_hash와 공통 generation_id/store_sha256/model/decoding_hash/
budget_hash/evaluator_hash가 plan과 같아야 한다. `cases`는 holdout 전부를 정확히 한 번 포함한다.
각 row는 case_id, answer_quality(PASS/FAIL), critical_error(bool), reviewer,
answer_sha256(64 hex), duration_seconds, cost_usd(유한한 0 이상 측정값)가 필요하다.
이 형식의 사람이 작성한 결과는 스스로 봉인한 입력일 뿐, 평가 실행·검토 provenance를
인증하지 않는다. 기존 golden의 answer hash 결속 review와 원시 입출력/receipt를
ADR에 함께 보존하고 모델·schema·latency provenance를 별도 확인해야 한다.
기록이 없는 비용을 0으로 채워서는 안 된다.

판정은 paired wins/regressions, Candidate critical errors, nearest-rank p95 비율과
총 비용 비율을 사전 기준에 대조한다. 불충분한 검토·누락·binding 오류는 1,
유효한 결과가 기준에 미달하면 gate를 저장하고 2, 사전 기준을 만족하면 0이다.
`statistical_significance=NOT_ESTABLISHED`이며 통계적 유의성을 인증하지 않는다.
`main_promotion_automatic=false`이고 Accepted/out-of-sample/decision_eligible/complete
및 별도 명시 MAIN 승격 절차를 대신하지 않는다.

## 확인 범위와 이행

모의 API 요청으로 v6 근거·전달·답변 hash 결속과 오류 거부를 확인했다.
보관한 로컬 v5 terminal 로그 10건도 진단했고 재실행 중복은 0이었다.
1건의 실행 실패는 원인 UNKNOWN이어서 실제 로그에서 proposal은 0개였다.
따라서 도구 후보가 법률 답변 품질을 높였다는 결과는 없다.
관련 검증과 실제 선택 목록은 [ADR-0637](../../../04_EXPERIMENTS/ADR/ADR-0637-evidence-bound-failure-improvement/README.md)에 보존한다.

계약 버전은 기존 journal과 원문 세대를 변경하지 않는다. 하위 단계 재구축은 필요 없다.
진단·후보는 온라인 registry에 등록하지 않는다. 제거/원복 시 이 CLI 연결과
golden의 optional adapter만 원복하고 기존 로그·불변 artifact는 보존한다.
실제 후속 구현은 먼저 READ/SELECT 도구 층의 작은 후보 한 개를 격리해 검증한다.
Content·Schema 층의 의미 변경, 법률 개념 승인, 온라인 recipe 소비, GENOS 성능 확인은 별도다.

원 논문: [EvoOntology](https://arxiv.org/abs/2609.15779),
[공개 구현](https://github.com/ruc-datalab/EvoOntology).
