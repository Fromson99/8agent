# 8-AGENT

법령·규정 문서를 수집→구조화→연결→질의응답으로 잇는 시스템. 전체 그림은
[07_DOCS/LEGACY_DOCS/ARCHITECTURE.md](07_DOCS/LEGACY_DOCS/ARCHITECTURE.md), 반영 경로는 `06_TOOLS/serve.sh` (uvicorn) 재시작 하나 —
컨테이너는 쓰지 않는다(2026-08-18 컨테이너 파일·레거시 앱 삭제).

## 4축 시스템 계약

새 데이터·코드·실험·배포 구조는
[`00_SYSTEM/ARCHITECTURE.md`](00_SYSTEM/ARCHITECTURE.md)와
[`00_SYSTEM/WORKSPACE.json`](00_SYSTEM/WORKSPACE.json)을 정본으로 삼는다. 모든 변경은
`구축 가능성 → 수정 가능성 → 검색·판단 효용성 → 피드백 자가개선`
네 축과 원문 근거·버전·감사·롤백·접근권한 불변조건을 만족해야 한다.

- 새 최상위 폴더는 `NN_UPPERCASE` 형식으로만 만든다.
- 경로는 `lawrag.platform.workspace`의 논리 root ID로 해결한다.
- 외부 생성·GENOS 내부 생성 데이터는 같은 `DatasetPackage`로 표현하고
  `SourceSet`이 여러 패키지를 명시적으로 선택·조합한다.
- 단서 유무·span·명시 참조 표면형만 규칙 hint이고, 조건·결과·효과·
  연결 대상은 LLM observation과 검증·승인을 거친다.
- 피드백 숏컷은 답을 저장하지 않고, 세대가 고정된 검증 검색 경로만 저장한다.
- 레이아웃 전환의 정본은 `00_SYSTEM/WORKSPACE.json`의 lifecycle receipt다.
  v2-only 전환 뒤 lowercase source가 없어도 retirement receipt와 canonical target
  지문을 모두 검증하며, 운영 코드는 receipt-bound generation만 읽는다.

## 지식 위키 — 세션 간 기억

`01_DATA/wiki/` 는 법령해석 도메인 지식의 llm-wiki(raw 불변층 + LLM 컴파일층)다.
**법령해석·규정 적용을 다루는 작업 전에 `01_DATA/wiki/wiki/index.md` 를 먼저
읽어 라우팅하라** — 세션은 리셋되지만 위키는 남는다. 역할 구도:

- 법령 원문("무엇이라 쓰였나") → 구조 스토어·RAG (`01_DATA/structure`, receipt-bound backend)
- 해석 지식("어떻게 읽는가") → 위키 (`01_DATA/wiki`)

위키를 소유한 것은 LLM 세션(너)이다. 의무 (정본 절차: `07_DOCS/LEGACY_DOCS/expc.md` §위키):

- `01_DATA/wiki/wiki/log.md` 의 "컴파일 대기"(triage·rule 항목)를 보면 병합하라
  — 아티클 수정 → index.md Updated 갱신 → log.md 한 줄 → 검사 통과.
- 수치·인용은 쓰기 전에 Raw 원문에서 확인하고 **원문 표기 그대로** 쓴다
  (grounding — "20%"가 아니라 "100분의 20").
- 검증: `.venv/bin/python 06_TOOLS/run_tool.py expc_wiki_check.py` (grounding·충실도·미참조 재고).
- raw/ 는 절대 고치지 않는다. 낡은 주장은 삭제 대신 Status: Outdated/Disputed.

## 진화 루프

- 사람 승인 합본: `$RAG_LOG_DIR/approval_receipts.jsonl` (`lawrag/core/rag/approvals`) —
  기존 정본을 대체하지 않는 append-only 계보. `/v1/rag/approvals/evolution`은
  대상별 최신 판정만 세어 실패×효과별 닫힌 mutation target 후보를 낸다.
- 대화→위키 유입 판정: `python -m lawrag.pipeline.wiki_triage` (오답·감사 지문 우선)
- 아티클 실적: 적중 원장 `01_DATA/wiki/ledger.jsonl` (backend `core/rag/wikiledger`) —
  생애 보고서(lawrag/core/rag/wikilife)가 4기준·권고로 접는다 (/expc/ 위키 판 배지)
- 규칙 정착·강등은 rules.set_status 가 위키 연대기에 자동 기록 — 정착 규칙은
  아티클로 컴파일하고 본문에 `rule:<id>` 로 인용하라 (강등 시 재심이 걸린다)

## ADR·LLM 실험 기록

- 실험·평가·A/B·ablation·probe·holdout·replay·regrade를 실행하기 전에
  `04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md`와
  `04_EXPERIMENTS/LEGACY_ADR/STANDARD.md`를 끝까지 읽고 따른다.
- 첫 실험 호출 전에 ADR과 가설·기준·데이터셋·arm·run을 생성·동결한다.
- 구현 파일 수정이나 실험 호출보다 먼저 `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py new --adr-root 04_EXPERIMENTS/ADR`를 실행해 ADR 번호와
  `scope_key`를 원자적으로 선점한다. 생성기가 기록한 owner, Codex task/session ID,
  `created_at`, `work_started_at`, `updated_at`, 작업 상태와 append-only 이벤트를 보존한다.
  진행 중인 같은 scope를 다른 ADR로 중복 생성하지 않는다.
- 여러 ADR 결과를 합치면 새 ADR에 모든 정확한 부모 `experiment_id/arm_id`를
  `merged_from`으로 연결하고 부모별 채택·제외 항목, 충돌·해결, 공통 불변조건과 rollback
  부모를 기록한다. 단순 참조·의존·충돌은 계보 부모가 아니라 hash된 `relationships`로 남긴다.
- ADR merge만으로 MAIN은 바뀌지 않는다. Accepted·분리평가·`decision_eligible=true`·complete
  arm만 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py`의 hash 고정 plan과 명시 승인으로 승격한다. 승격 코드는
  rollback switch 뒤에 두고 MAIN generation과 apply/rollback receipt를 append-only로 보존한다.
- ADR-0043 이후 새 ADR은 `04_EXPERIMENTS/LEGACY_ADR/STANDARD.md`를 따른다.
- stable tool runner로 표준 디렉터리를 만들고, 완료 전 `adr_structure.py validate --final`을 통과시킨다.
- ADR-0044 이후 후속 실험은 부모 `experiment_id/arm_id`를 지정한다. 같은 조건의
  A/B/C는 한 ADR의 arm으로, 결과를 본 뒤 만든 B1/B2는 새 ADR로 기록한다.
- `adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR`로 v2 실험 DAG의 부모 hash와
  cycle을 검사한다. 완료된 run과 탈락 분기를 덮어쓰거나 삭제하지 않는다.
- 결과가 complete인 arm만 후속 ADR의 부모로 쓴다. 완료 후 반복 실행·재채점도 부모
  manifest를 수정하지 않고 새 ADR로 기록한다.
- 질문 단위 LLM 평가가 있으면 `실험/질문-NNN-case-id.md`에 실제 제품·중간·채점
  prompt와 output을 보존한다. 요약 JSON만 남기지 않는다.
- 제품 답변과 이를 변경하는 모든 중간 역할은 `claude-haiku-4-5-20251001`을 사용한다.
  제품과 격리된 오프라인 채점은 manifest에 `class=offline_evaluator`로 선언한 경우에만
  Haiku·Sonnet 5·Opus 5를 사용할 수 있다.
- ADR-0054의 `role-separated-v2` 격리 계약을 따르는 답변 모델 성능 비교만
  `class=offline_benchmark_candidate`로 동결된 외부 모델을 사용할 수 있다. 그 출력은
  제품 답변을 선택·수정하거나 제품 context에 들어갈 수 없다.
- 인샘플 probe는 `decision_eligible=false`이며 메인 배선 채택 근거로 사용하지 않는다.
