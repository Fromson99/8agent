# 저장소 전역 실험 실행 프롬프트

## 신규 실험 모델 정책 — 2026-09-14 사용자 변경

ADR-0383 이후 신규 외부 실험의 모델 정본은 `00_SYSTEM/EXPERIMENT_MODEL_POLICY.json`이다.
현재 provider는 **Gemini**, 모델은 **gemini-3.1-flash-lite**, 키는 `.env`의 `GEMINI_API_KEY`다.
제품·중간 처리·VLM·오프라인 평가 모두 이 기본값을 사용한다. 다른 provider/고가 모델로 자동
전환하지 않는다. 모델 변경은 새 설계에 명시한다. `.env`나 키 값을 로그·프롬프트에 넣지 않는다.

공통 호출은 `lawrag.research.experiment_client.GeminiExperimentClient`를 사용한다.
2.5 Flash-Lite는 모델 목록에 있지만 신규 키에서404로 거절되어3.1을 선택했다.
Qwen3.5와 성능 동등성을 확인한 선택은 아니다. 공개·합성 실험용이며 내부 GENOS 모델 정책은 별도다.

아래 Haiku 고정·기존 evaluator allowlist 지침은 **ADR-0382까지의 동결 기록을 검증하는 역사적 정책**이다.
신규 실험에는 이 절의 Gemini 정책이 우선한다. 완료된 이전 ADR의 모델명·출력·해시는 바꾸지 않고,
예전 실험을 Gemini로 재실행할 때는 새 ADR을 만든다. 생성·검증 CLI는 새 정책과 과거 정책을 구분한다.


이 문서는 8-AGENT 저장소에서 실험을 수행하는 모든 agent의 의무 지침이다. 요약본이 아니라
이 파일과 `docs/adr/STANDARD.md`를 실행 전에 끝까지 읽는다.

## 1. 적용되는 요청

다음 중 하나라도 해당하면 이 절차를 적용한다.

- 실험, 평가, 성능 확인, 가설 검증
- A/B/C, ablation, control, probe, holdout
- replay, repeat, regrade, 재채점
- prompt, router, compiler, verifier, repair, judge 비교
- RAG 회수·필터·가지치기·정의·Wiki·관계·온톨로지 변경의 효과 비교
- 정확도, recall, selectivity, 토큰, 비용, 지연의 전후 비교

단순 코드 수정 후의 일반 단위 테스트, 읽기 전용 진단, 기존 결과의 요약은 새 실험이 아니다.
그러나 둘 이상의 동작을 비교하거나 성능 결론을 내리면 실험이다.

## 2. 작업 선점 — 첫 쓰기 전에 할 일

1. `docs/adr/STANDARD.md`, `docs/adr/README.md`, `docs/adr/EXPERIMENT_GRAPH.md`를 읽는다.
2. `docs/adr`의 진행 중인 v3 `reservation`을 확인해 같은 `scope_key`·제목·작업 범위가
   이미 선점됐는지 확인한다. 있으면 새 ADR을 만들지 말고 기존 ADR의 owner와 조율한다.
3. 사용하지 않은 다음 ADR 번호와 고유한 kebab-case `scope_key`를 선택한다. 완료된 ADR은
   수정해 재사용하지 않는다.
4. **소스·설정·데이터·프롬프트를 수정하기 전에** `scripts/adr_structure.py new`를 이 작업의
   첫 쓰기로 실행한다. 이 명령이 lock 안에서 immutable `claim.json`을 먼저 쓰고
   번호·scope를 원자적으로 선점하며 owner, Codex
   task/session ID, `created_at`, `work_started_at`, `updated_at`, 작업 상태와 append-only
   `reservation.events`를 기록한다. ADR 폴더를 손으로 복사하거나 나중에 소급 생성하지 않는다.
5. 부모가 있으면 결과가 `complete`인 정확한 `experiment_id/arm_id`를 선택한다.
6. 다음 항목을 결과 확인 전에 고정한다.
   - 검증할 가설과 반증 가능한 예상
   - primary metric, 성공 기준, 허용 회귀, 비용·지연 한계
   - 데이터셋, 표본 선택 규칙, 법령·기준답변 버전, SHA-256
   - baseline과 candidate/ablation/control에서 바뀐 것과 고정한 것
   - run ID, 반복 수, judge와 arm 순서 편향 통제
7. 첫 제품·중간·judge 호출보다 ADR 생성이 먼저여야 하며, 위 설계 동결까지 모두 끝난 뒤
   호출을 실행한다.

### 2.1 새 실험 후보 코드 격리(ADR-0138 이후)

제품 답변·제품 context·retrieval 후보 집합을 바꿀 수 있는 새 후보는 운영 구현에 직접 쓰지
않고 다음 순서를 모두 지킨다. 문서·구조 감사처럼 제품 영향 코드 후보가 없을 때만 사유를 적어 예외로 둔다.

1. ADR 선점과 설계 동결 뒤 `scripts/adr_candidate.py snapshot`으로 필요한 기존 파일을
   `lawrag/research/candidates/adr_NNNN/<candidate-id>/`에 복사한다. production에 없는
   신규 파일은 최종 `snapshot/<target_path>`에 만든 뒤
   `adr_candidate.py register --upstream-state absent`로 등록한다. absent upstream에 기존
   파일의 hash를 꾸며 넣지 않는다.
2. snapshot에 exact `experiment_id`, candidate `arm_id`, 사전 동결 `run_id`를 연결한다.
3. 복사본만 수정하고 `freeze`로 revision을 고정한 뒤 `validate`를 통과시킨다. freeze는
   present upstream drift, absent target 출현, manifest 밖 snapshot 파일을 거부한다. 이 전에는
   제품·router·compiler·verifier·repair·judge 호출과 후보 효과 측정을 실행하지 않는다.
4. 실험 runner는 hash가 맞는 frozen revision을 명시적으로 import하고 객체로 주입한다.
   운영 API·runtime registry·switch·환경변수·문자열 profile은 연구 후보를 발견하거나 선택하지 않는다.
5. `실험/manifest.json#design.code_isolation`에 candidate manifest·revision·runner hash와
   exact arm/run을 기록한다. 위임 agent도 같은 revision만 사용한다.
6. 결정 전에는 운영 component, registry, API, 기본 prompt·router·retrieval 구현을 후보 코드로
   수정하지 않는다. 공통 계측기·validator 변경은 제품 동작을 바꾸지 않음을 별도로 증명한다.
7. Accepted·out-of-sample·decision-eligible·complete 결과만 검토본을 production component로
   옮길 수 있으며, 실제 선택은 별도 MAIN promotion과 명시 승인으로만 수행한다.

권장 생성 예시는 다음과 같다.

```bash
.venv/bin/python scripts/adr_structure.py new \
  --number NNNN --slug short-slug --title "작업 제목" --phase probe \
  --owner "작업자 또는 agent" --session-id "Codex task ID" \
  --scope "겹치지 않는 작업 범위" \
  --scope-key stable-scope-key --branch-id A --candidate-arms B \
  --questions case-001
```

생성 충돌은 번호나 범위가 이미 선점됐다는 뜻이다. 번호만 바꿔 우회하지 않는다.
기존 선점이 실제 진행 중인지 확인하고, 같은 작업이면 기존 ADR을 이어서 사용한다.

## 3. 분기 규칙

- 결과를 보기 전에 같은 frozen set과 판정 기준으로 비교하는 A/B/C는 한 ADR의 arm이다.
- B 결과를 본 뒤 만든 B1/B2는 새 ADR이며 부모는 B의 정확한 arm이다.
- 부모 결과가 complete가 아니면 자식 분기를 실행하지 않는다.
- ADR이 열린 동안 사전 계획된 반복은 `run-002`로 추가할 수 있다.
- ADR 완료 후 반복·재채점·새 가설은 새 ADR로 만든다.
- 실패·회귀·탈락 arm도 삭제하지 않는다. manifest, 질문 원문, run 결과를 덮어쓰지 않는다.
- 위임된 agent도 같은 작업에 별도 ADR을 만들지 않는다. 주 agent가 선점한 ADR과 run/arm을
  사용하고 정확한 산출물 경로를 돌려준다.

## 3.1 ADR merge와 다른 ADR 관계

- 둘 이상의 완료 분기를 합치면 새 ADR을 선점하고 `--merge-parent MANIFEST ARM merged_from`을
  부모 수만큼 반복한다. 부모는 모두 `complete`여야 한다.
- `integration`에 부모별 채택·제외 항목, 공통 불변조건, 충돌과 해결 근거, 결과 arm과
  rollback parent를 결과 확인 전에 적는다. 충돌이 없으면 그 근거를 적는다.
- 단순 참조, 의존, 충돌, 중복, 차단, supersede는 `--related-adr ADR_PATH RELATION NOTE`로
  기록한다. 이를 merge 부모나 `derived_from`으로 가장하지 않는다.
- 전역 graph에서 모든 `merged_from` edge와 별도 ADR 관계 표를 확인한다.

## 3.2 MAIN RAG 승격

- ADR merge만으로 MAIN은 바뀌지 않는다. 여러 결과를 올릴 때는 merge ADR의 결과 arm 하나를
  source로 사용한다.
- source는 Accepted·분리평가·decision-eligible·complete이고
  `main_wiring: promotion-candidate`여야 한다.
- `scripts/rag_main_promotion.py prepare`로 source/code/validation receipt와 현재 MAIN
  generation을 hash 동결하고 `check`한다. 모든 코드는 plan의 guard switch 뒤에 둔다.
- 사용자 또는 명시적 승인권자가 승인 이유와 `--confirm-main`을 준 경우에만 `apply`한다.
  실험 성공을 근거로 agent가 자동 승격하지 않는다.
- 적용 후 API의 MAIN generation·promotion source를 확인한다. 회귀 trigger가 발생하면 최신
  promotion부터 `rollback --confirm-main`하고 receipt를 보존한다.

## 4. 모델과 실행 기록

- 제품 답변, router, compiler, verifier, repair 등 사용자에게 보일 답을 생성하거나
  변경하는 모든 호출은 `claude-haiku-4-5-20251001`만 사용한다.
- 제품 경로와 격리된 오프라인 judge는 manifest에 `class=offline_evaluator`로 선언하고
  `claude-haiku-4-5-20251001`, `claude-sonnet-5`, `claude-opus-5` 중 하나를 사용할 수 있다.
  오프라인 judge 출력은 제품 답변을 고치거나 운영 응답에 포함하지 않는다.
- ADR-0054 이후 모델 자체의 답변 상한을 비교할 때만 `role-separated-v2`와
  `class=offline_benchmark_candidate`를 사용할 수 있다. 비교 모델은 첫 호출 전에 닫힌
  목록으로 동결하고, 기준답변을 볼 수 없으며, 출력은 제품 context·사용자 답변·운영
  배선에 들어가지 않는다. 점수 전용 offline evaluator만 이 출력을 읽는다.
- 질문마다 `실험/질문-NNN-case-id.md` 하나를 두고 모든 run과 arm을 같은 파일에서
  비교 가능하게 기록한다.
- system, user, schema/tool, provider 원응답, structured output, usage, latency를 생략하지
  않는다. 저장하지 않은 payload를 `exact`라고 부르지 않는다.
- 기준답변은 judge 입력에만 넣고 제품 입력과 물리적으로 분리한다.
- router/compiler/verifier/repair의 중간 입력과 출력도 제품 출력과 함께 보존한다.
- 원시 JSON·로그는 `artifacts/manifest.json`에 경로, byte, SHA-256을 기록한다.

## 5. 결과 보고

- arm별 정답/전체와 비율, 사전 지정 비교쌍의 delta를 보고한다.
- candidate만 정답, baseline만 정답인 회귀, 둘 다 정답, 둘 다 오답을 분리한다.
- 질문별 맞음·틀림과 직접 원인을 공통 실패 taxonomy로 기록한다.
- judge 불일치, 재채점 규칙, 입력·출력 토큰, 호출 수, p50/p95 지연을 보고한다.
- 평가 모델·prompt가 다른 점수는 같은 리더보드 값처럼 직접 비교하지 않는다. 사람 확정
  calibration set에 대한 false pass·false fail과 모델별 지연을 먼저 기록한다.
- 회수를 건드렸다면 corpus 전체 수, 필터 전·후, 실제 제시 수, 평균·p50·p95,
  golden recall, `제시 수 / corpus` selectivity를 반드시 계산한다.
- 인샘플 probe는 `decision_eligible=false`이며 일반화 또는 메인 승격 근거로 표현하지 않는다.
- 성공 기준을 충족하지 못한 실험도 Rejected 또는 Proposed로 완결하고 삭제하지 않는다.

## 6. 종료 조건

실험 결과를 사용자에게 보고하기 전에 다음을 모두 수행한다.

```bash
.venv/bin/python scripts/adr_structure.py hash --path docs/adr/ADR-NNNN-slug
.venv/bin/python scripts/adr_structure.py validate --path docs/adr/ADR-NNNN-slug --final
.venv/bin/python scripts/adr_structure.py graph --adr-root docs/adr
```

- `validate --final`과 graph 검사가 통과하지 않으면 완료라고 보고하지 않는다.
- `docs/adr/README.md`에 새 ADR 링크를 추가한다.
- `scripts/adr_structure.py status --path docs/adr/ADR-NNNN-slug --status completed`로
  완료 시각과 이벤트를 추가한다. 실행하지 않은 선점은 `--status abandoned`와 사유를 남기며
  폴더를 삭제하지 않는다.
- 최종 사용자 보고에는 결과, 한계, 메인 배선 여부와 ADR·질문 인덱스 링크를 포함한다.
- 사용자가 명시적으로 운영 변경을 요청하지 않았거나 분리 평가의 채택 기준을 충족하지
  않았다면 메인 배선은 `unchanged`로 둔다.
