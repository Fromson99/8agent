# Agent Legal 더블하네스 최종 통합 설계서

- 문서 버전: FINAL-DESIGN v1.0, 2026-09-19.
- 상태: **구현 기준으로 정리한 최종 통합안. 제품 구현·성능 검증·배포 승인을 뜻하지 않는다.**
- 목적: 에이전트가 내부 자료를 탐색하고, 잠정 판단을 재검토·철회·수정하며, 근거와 일치하는 답변에 도달하는 실행 구조를 만든다.
- 기준 코드: Git a3ac254cc8fba708e39cf37482707a5570fd388d 및 출처 목록의 작업 코드·동결 후보. 파일별 SHA-256은 sources.json에 보존한다.
- 관측 상태: 로컬 활성 포인터 document-navigation-rag-20260917-v2, 포인터 generation 16, quality_certified=false. 완료 rev3과 진행 rev4를 구분한다. GENOS 현장 실행은 확인하지 않았다.
- 작성·검토: implementation-design-report / design-reality-review 스킬에 따른 자체 검토. 신규 모델 호출·재채점·품질 실험 없음.
- 문서 관계: 선행 DESIGN.md와 AGENTIC_EXPLORATION_IMPLEMENTATION.md의 결정 사항을 통합한다. 향후 구현 기준은 이 문서다. 선행 문서는 관측 당시 기록으로 보존한다.
- 바로 보기: [설계 필요성 표](DESIGN_RATIONALE.md), [결정 목록 JSON](decisions.json), [제어 계약](control.schema.json), [검증 시나리오](acceptance-scenarios.json), [자체 검토](SELF_REVIEW.md).

## 1. 최종 결정과 범위

더블하네스의 두 축은 다음과 같다.

1. **DomainSpec**: 질문에 필요한 법률상 확인 사항, 근거의 자격, 미확인·충돌·사실 부족의 의미, 답변 범위를 정한다.
2. **AgentProfile**: 모델·도구·문맥·읽기 순서·형식 처리·호출 예산·검토 강도를 정한다.

두 설정을 서버 Coordinator가 집행한다. 조사/반례 검토/작성은 실행 역할이고, 요청 안의 반복/요청 사이 개선은 반복의 시간 범위다. 이들을 더블하네스의 두 축과 혼동하지 않는다.

최초 구현 범위는 한 번의 요청 안에서 다음을 완성하는 것이다.

> 질문 해석 → 문서·원문 탐색 → 잠정 주장 → 반례 확인 → 필요 시 재탐색/재작성 → 일관된 최종 답변과 기록.

첫 후보의 문서 범위는 배포가 승인한 공유 코퍼스의 저장 판본이다. 실제 내부 자료는 GENOS 내부 모델에서 처리한다. 사용자별 ACL, 사건 기준일별 법령 적용, 사용자 후속 발화로 의미 재개, 검토된 피드백의 자동 반영은 후속 계약으로 확장한다.

목록·원문 조회는 코드 경로로 간단히 종료할 수 있다. 모든 질문에 복수 agent 호출·전면 체크리스트·별도 계획 호출을 강제하지 않는다. 기존 원문·용어·정의·명시 참조 색인을 재사용하고, 코퍼스 전체를 Rule/SemanticClause로 다시 생성하지 않는다.

성공의 의미는 매 턴 자신감 상승이 아니다. 새 원문, 구체적인 재해석, 사실 정정, 잘못된 인용 수정에 따라 답을 갱신하고, 끝내 해결하지 못한 것을 숨기지 않는 것이다. 정확도가 매 턴 증가한다는 보장은 없다.

## 2. 핵심 설계가 필요한 이유

근거 구분: **관측**은 저장된 실험·실행 기록, **코드**는 구현 조건·배선, **모의**는 합성 입력 재현, **설계상 위험**은 실제 발생을 주장하지 않는 구조적 위험이다. 숫자는 §12의 환경·분모·한계를 함께 적용한다.

| ID | 핵심 설계 | 없거나 불완전했을 때의 문제 | 근거 수준 | 최종 결정·기대 범위 | 검증 |
|---|---|---|---|---|---|
| D01 | 도메인 기준과 모델 프로파일 분리 | 같은 조립 v3가 Gemini 38→36, Qwen 30→34로 반대로 작동했다. 현재 문구는 부재 판단 규칙까지 바꾼다. [S05](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0469-legal-agent-loop-rev2/artifacts/metrics.json) [S11](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/composer.py) | 관측·코드 | 법률상 확인 기준은 공통으로 고정하고, 읽기·문맥·형식·표현만 모델별 조정한다. 프로파일 변경으로 법률 기준이 달라지는 것을 제한한다. 어느 프로파일이 더 정확한지는 별도 평가. | T01 |
| D02 | 질문의 문서 범위·개념·사실 구분 | ADR-0440에서 문서명을 목표 개념처럼 처리해 후보 상한에 걸렸고 원문 읽기·설명 답변이 각각 0/6이었다. [S03](/home/jin/8-AGENT/07_DOCS/REFERENCE/OPERATIONS/TASK_HARNESS.md) | 관측 | 질문 구간을 문서/폴더/용어/조문/사실로 구별하고 해석 후보를 작업 상태에 보존한다. 엉뚱한 검색 범위로 빠지는 경로를 줄인다. 모호한 의도는 확인이 필요. | T02 |
| D03 | 질문에 필요한 최소 장부와 부분 답변 | 전체 항목을 채우는 조립 확인표는 정답 수를 개선하지 못했고 수리 후에도 누락 항목이 남았다. [S04](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0466-legal-agent-composer-audit/artifacts/metrics.json) [S02](/home/jin/8-AGENT/07_DOCS/REFERENCE/ARCHITECTURE/LEGAL_AGENT_SYSTEM.md) | 관측 | 관련 쟁점만 활성화하고, 모든 후보 판정 대신 확인 범위에 맞춰 READY/BOUNDED/CLARIFY를 결정한다. 절차 때문에 유효한 답변까지 막히는 것을 줄인다. 탐색 장부의 품질 효과는 미검증. | T03 |
| D04 | 문서 구조 탐색과 직접 조문 열기 | FTS 9~40위에 놓친 결정 조문 6개가 있었고, 조문명을 명시한 재검색도 다른 법 조문으로 흘렀다. [S06](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0472-legal-agent-loop-rev3/README.md) [S14](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/folder_navigation.py) | 관측·코드 | 폴더→문서→목차→항 읽기, 직접 조문 locator, 하위 검색을 같은 도구 표면에 연결한다. 검색 상위 결과 밖의 경로를 연다. 구조 도구의 존재와 새 루프 연결 완료는 다르다. | T04 |
| D05 | 발견·입력 전달·채택·조립·인용 분리 | 생성 카드 963/903쌍 중 실제 요청 입력은 906/849쌍이었다. 생성됐지만 전달되지 않은 것이 57/54쌍이다. [S08](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/existing-run-diagnostics.json) | 관측 | 실제 호출 payload에 대한 전달 영수증과 근거 단계별 계보를 기록한다. 실패 위치를 구분할 수 있다. 입력 전달은 모델의 이해를 증명하지 않는다. | T05 |
| D06 | 서버가 부여한 원문 구간·핸들 보존 | 모델 문자 위치 오류로 ADR-0438 읽기·설명 0/6. 긴 조문 모의 검사에서는 읽은 뒷부분이 조립 앞 6,000자에서 빠졌다. [S03](/home/jin/8-AGENT/07_DOCS/REFERENCE/OPERATIONS/TASK_HARNESS.md) [S09](/mnt/c/Users/Jin/.codex/visualizations/2026/09/19/01a0b8bb-63c3-7c20-a211-df3661760a5d/legal-agent-review-checks.json) [S08](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/existing-run-diagnostics.json) | 관측·모의 | 모델은 핸들을 선택하고 서버가 정확한 blocks/spans/hash를 보존한다. 긴 단위는 분할·페이지 처리한다. 좌표 오류와 전달 손실을 직접 검사할 수 있다. 잘림이 현재 CM 오답 원인인지는 미확인. | T06 |
| D07 | 근거 평가 철회와 의존 주장 무효화 | 완료 rev3의 drop은 not adopted 카드에만 적용되어, 한 번 채택한 근거의 철회를 표현하지 못한다. [S10](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/loop.py) | 코드 | 원문은 불변으로 두고 쟁점별 평가를 수정한다. 의존 주장·리뷰·초안은 stale로 전환한다. 추가 탐색에 따라 판단을 바꿀 수 있다. 수정이 의미적으로 옳은지는 별도 검토. | T07 |
| D08 | 명시적으로 버린 근거의 자동 부활 금지 | 모의 실행에서 dropped=true·채택 목록 빈 상태인데 상위 카드 fallback이 같은 자료를 최종 근거로 넣었다. [S09](/mnt/c/Users/Jin/.codex/visualizations/2026/09/19/01a0b8bb-63c3-7c20-a211-df3661760a5d/legal-agent-review-checks.json) [S10](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/loop.py) | 모의·코드 | 채택 0이면 미확인을 보존한다. 버린 근거 재채택에는 명시적인 재검토와 이유를 요구한다. 철회와 최종 답변이 어긋나는 경로를 차단한다. | T08 |
| D09 | 미확인·비적용·사실 부족·충돌 분리 | 현재 장부의 ‘근거 있음/원문에 없음’과 조립 문구만으로는 검색 실패·사실 부족·부재를 구분하기 어렵다. [S31](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/harness.py) [S11](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/composer.py) | 코드·설계상 위험 | 쟁점의 근거 상태와 사실 상태를 분리한다. 검색 기록 없이 부재로 종결하지 않는다. 못 찾은 것을 없다고 단정하는 경로를 줄인다. 전체 규정의 의미상 부재는 별도 근거 필요. | T09 |
| D10 | 구체적 반례를 다루는 선택적 재검토 | ADR-0466 집계 호출은 Gemini 91→274, Qwen 92→282였지만 확인표의 정답 이득이 없었다. [S04](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0466-legal-agent-composer-audit/artifacts/metrics.json) | 관측 | 특정 주장·원문·누락 조건을 지목하는 challenge를 필요할 때 실행하고 다음 읽기나 재작성으로 연결한다. 반복 점검의 낭비를 제한한다. 같은 모델의 비판은 독립된 정답 판정이 아니며 효과는 미검증. | T10 |
| D11 | 참조 출처 보존·오연결 무효화·자동 채택 제한 | 다른 문서의 조문이 없으면 옛 오연결을 유지하는 모의 실패가 있었다. 위임 짝 자동 추가도 중간 관문을 통과하지 못했다. [S08](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/existing-run-diagnostics.json) [S13](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/references.py) [S07](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0473-legal-agent-loop-rev4/artifacts/s1-gate.json) | 모의·관측 | source mention·대상·판본·해소 사유를 저장하고 잘못된 관계는 미해소로 바꾼다. 탐색 후보와 채택 근거를 구분한다. 관계 오염과 불필요한 근거 추가를 줄인다. 역참조만으로 위임 효과를 확정하지 않는다. | T11 |
| D12 | 재탐색 제어와 단계 산출물 재생성 | 현재 파이프라인은 한 번 순회하고 assemble/answer가 고정 연결되어 있다. 재진입 기능은 없다. [S16](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/pipeline.py) [S17](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/stages.py) | 코드·설계상 위험 | RESEARCH/RECOMPOSE/FINAL 제어 포트와 같은 요청 coordinator를 추가한다. 재탐색 시 이후 산출물을 무효화한다. 최종 답변과 선택·조립 기록을 일치시킨다. 현재 재탐색 혼합 사고가 관측됐다는 뜻은 아니다. | T12 |
| D13 | 인용 유효성과 주장 의미를 별도 검증 | 모의 검사에서 없는 핸들만 제거되고 주장은 남았다. 유효한 핸들을 단 부정 반전에는 경고가 없었다. [S09](/mnt/c/Users/Jin/.codex/visualizations/2026/09/19/01a0b8bb-63c3-7c20-a211-df3661760a5d/legal-agent-review-checks.json) [S12](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/citations.py) [S32](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/checker.py) | 모의 | 출처 없는 법률 주장 문단을 수리·보류하고, 의미상 지지는 별도 challenge/품질 평가로 확인한다. 인용 오류를 직접 줄일 수 있다. 올바른 출처를 달았다고 법률 해석까지 보증하지 않는다. | T13 |
| D14 | 통합 실행 예산과 정확한 계측 | rest[-0:] 모의 조건에서 카드 상한 2가 3이 됐다. 금액 누락을 0으로 집계했고 기존 시간 지표는 E2E가 아니었다. [S09](/mnt/c/Users/Jin/.codex/visualizations/2026/09/19/01a0b8bb-63c3-7c20-a211-df3661760a5d/legal-agent-review-checks.json) [S08](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/existing-run-diagnostics.json) [S10](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/loop.py) | 모의·관측 | 모든 물리적 호출·수리·재시도·도구·문맥·deadline을 한 예산으로 관리하고 종료 출력을 예약한다. 무제한 반복과 비용 오판을 제한한다. 카드 수와 토큰 수, 호출 지연과 E2E를 분리한다. | T14 |
| D15 | 저장 판본과 법적 적용 시점 구분 | 기존 store는 세대·해시를 검증하지만 후보 근거 단위에는 법적 효력 기간이 없다. [S15](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/storage.py) [S23](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/DESIGN.md) | 코드·설계상 위험 | 실행 binding에 판본을 고정하고 temporal_status를 별도 보존한다. 역사적 적용은 후속 시점 계약으로 확장한다. 다른 세대 혼합을 방지한다. 저장 최신판을 사건 당시 적용법으로 확정하지 않는다. | T15 |
| D16 | 탐색 필터와 접근 권한 구분 | 현재 HTTP Request에는 인증된 사용자 주체가 없다. document_ids와 workflow user_id는 권한 증명이 아니다. [S18](/home/jin/8-AGENT/00_SYSTEM/SCHEMAS/term-runtime-v1.schema.json) [S20](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/app.py) [S28](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/document_agent.py) [S30](/home/jin/8-AGENT/GENOS.md) | 코드·설계상 위험 | 서버의 허용 범위와 요청 필터를 교차 적용하고 모든 탐색·인용에 동일 경계를 집행한다. 내부 탐색의 권한 경계를 구현한다. 실제 정보 유출이 관측됐다는 주장은 하지 않는다. | T16 |
| D17 | 실제 API·단계 계약·화면 소비자 연결 | 모의 정규화 요청의 metadata는 현 Request에서 거부됐다. 브릿지는 evidence_ids, 현 답변은 source_ids를 사용한다. [S08](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/existing-run-diagnostics.json) [S18](/home/jin/8-AGENT/00_SYSTEM/SCHEMAS/term-runtime-v1.schema.json) [S19](/home/jin/8-AGENT/service.py) [S21](/home/jin/8-AGENT/08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py) | 모의·코드 | metadata와 본문 분리, 명시 adapter dispatch, 필수 응답 필드 매핑, 브릿지와 fixture 동시 정합화. 실험 코드가 서비스에서 호출·표시될 수 있게 한다. 현장 장애 발생 여부는 미확인. | T17 |
| D18 | 요청별 checkpoint·revision과 재개 경계 | 현재 app는 성공한 run을 최종 저장하고, HTTP에는 명시적인 의미 재개 필드가 없다. [S20](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/app.py) [S18](/home/jin/8-AGENT/00_SYSTEM/SCHEMAS/term-runtime-v1.schema.json) [S28](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/document_agent.py) | 코드·설계상 위험 | 호출 전후 이벤트·원자적 checkpoint·중복/늦은 응답 제어를 둔다. 최초판은 interrupted 보존, 의미 재개는 v2 계약. 중단 원인을 보존하고 오래된 응답 덮어쓰기를 방지한다. 현재 자동 재개가 있다고 설명하지 않는다. | T18 |
| D19 | 근거·판본에 묶인 검토된 피드백 | 현재 feedback은 PROPOSED를 저장할 뿐, 다음 검색을 자동 수정하지 않는다. [S22](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/feedback.py) [S01](/home/jin/8-AGENT/00_SYSTEM/ARCHITECTURE.md) | 코드·기능 공백 | 실패 위치에서 검색/별칭/코드 수정 후보를 만들고 검증 후 다음 버전에 적용한다. 과거 답을 정답으로 자동 저장하지 않는다. 오류를 재사용하는 위험을 줄이면서 장기 개선 경로를 만든다. 자동 학습 효과는 미검증. | T19 |
| D20 | 회복·회귀·독립 평가를 함께 관리 | Qwen rev3은 34→35였지만 신규 정답 5·회귀 4로 채택 기준을 못 넘었다. 전체 후보는 같은 CM 51 인샘플이다. [S06](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0472-legal-agent-loop-rev3/README.md) [S07](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0473-legal-agent-loop-rev4/artifacts/s1-gate.json) | 관측 | 변경 효과를 분리하고 회복·회귀·미답변·비용을 비교한다. 기준답변은 제품 입력과 분리하고 새 표본에서 검증한다. 자가 점수나 총점만으로 개선을 선언하지 않는다. 전체 더블하네스 품질은 아직 미검증. | T20 |

각 T 항목은 앞으로 제품 구현이 통과해야 할 시나리오다. 현재 통과한 제품 테스트를 뜻하지 않는다.

## 3. 아키텍처와 책임

~~~mermaid
flowchart TD
    Q["요청·질문·문서 범위"] --> C["기존 Pipeline 안의 요청별 Coordinator"]
    D["DomainSpec<br/>확인 기준·근거 의미·답변 범위"] --> C
    P["AgentProfile<br/>모델·도구·문맥·예산"] --> C
    C <--> W["WorkState + Journal"]
    C --> I["Investigator"]
    I --> T["ToolBroker"]
    T --> S["기존 원문 Store·FTS·목차·정의·명시 참조"]
    S --> O["정확한 원문 Observation"]
    O --> W
    W --> B["선택·근거 묶음"]
    B --> A["Composer"]
    A --> V["코드 검사 + 필요한 Targeted Review"]
    V -->|"RESEARCH"| C
    V -->|"RECOMPOSE"| A
    V -->|"FINAL"| F["답변·출처·미해결 사항·실행 기록"]
    F --> M["검토된 개선 후보"]
~~~

| 구성 요소 | 입력·출력 | 최종 책임 |
|---|---|---|
| DomainSpec | 질문 유형·쟁점 규칙·근거 역할·관문 의미 | 모델 교체에도 유지되는 확인 기준 |
| AgentProfile | 모델 설정·도구 정책·문맥·예산·형식 | 동일 기준을 해당 모델이 수행하는 방법 |
| Coordinator | 단계 산출물과 control | 재진입·무효화·종료·일관된 결과 commit |
| Investigator | 현재 쟁점·원문·탐색 후보 → 행동·평가 제안 | 조사 경로와 잠정 판단 |
| Challenger | 특정 주장·원문·사실 → 구체적인 결함/다음 확인 | 반례와 누락 발견. 정답 판정 권한 없음 |
| Composer | 유효 근거·주장·한계 → 서술 | 사용자 답변 구성 |
| ToolBroker | 허용된 읽기 요청 → Observation | 범위·판본·원문 좌표·호출 기록 |
| Reducer | 검증된 모델/서버 제안 → 새 state revision | 채택/철회/쟁점 상태/의존 산출물 무효화 |
| Journal | 사건·호출·checkpoint | 재현·중단 추적·중복 방지 |
| ServingAdapter | 내부 상태 ↔ 현재 runtime 포트 | 외부 API와 출처 소비자 호환 |

기존 상속 사슬에 새 계층을 얹는 대신 자원·도구를 composition으로 주입한다. 제품 실행기는 연구 snapshot 경로를 직접 import하지 않는다. 완료 후보를 새 후보로 분기해 정식 모듈과 manifest를 만든다.

모델이 통제하는 범위는 허용 도구 선택, 근거 평가 제안, 잠정 주장, 추가 확인 요청이다. 모델이 원문·접근 범위·평가 기준·운영 코드를 직접 변경하는 경로는 두지 않는다.

## 4. 상태·근거·주장 계약

### 4.1 실행 결속과 revision

ExecutionBinding은 query ID, source generation/store hash, navigation/FTS/reference 지문, domain/profile/controller 지문, 실제 model/backend, 허용 범위 지문을 가진다. 원문의 저장 판본과 법적 시행일은 구별한다.

WorkState는 다음을 보존한다.

| 객체 | 필수 의미 |
|---|---|
| Intent | 원질문 구간·문서/폴더/용어/조문 구분·해석 후보·선택 이유 |
| Fact | 사용자 진술/확인됨/미상, 출처와 revision |
| Issue | 필요한 확인 항목, required, origin, evidence_state, fact_state |
| Frontier | 다음 검색/읽기 후보, 대상 쟁점, 확인 목적, 시도 이력 |
| Observation | 도구 요청·반환·실제 읽기 범위·판본·페이지 상태 |
| EvidenceSpan | 원문 블록·구간·해시·immutable handle |
| Assessment | issue↔evidence의 supports/qualifies/contradicts/irrelevant/uncertain 평가 |
| Claim | 잠정 주장, 의존 facts/issues/assessments/spans, revision, 유효성 |
| Challenge | 대상 claim revision, 구체적 결함, 원문 anchor 또는 미확인 질문, 처리 상태 |
| Budget | 모든 물리적 모델 시도·문맥·도구·deadline·출력 예약 |
| Journal | 사건 ID·state revision·변경 사유·payload/receipt hash |

세 가지 버전을 구별한다.
- state_revision: 상태 변경마다 증가. 호출·관찰 기록 때문에 단계별 값이 달라도 정상이다.
- evidence_revision: 채택 근거 묶음 또는 관련 평가 변경 시 증가.
- claim_revision: 해당 주장이 수정될 때 증가.

최종 일관성은 모든 stage의 state_revision을 동일하게 맞추는 조건이 아니다. 동일 query/binding, 현재 evidence_revision, 각 주장·리뷰의 dependency hash가 유효한지 확인하는 조건이다. 각 stage가 읽은 입력 revision과 출력 의존 지문을 기록한다.

### 4.2 쟁점 상태와 관문

evidence_state는 OPEN / EVIDENCE_LINKED / SEARCHED_UNRESOLVED / CONFLICTED / NOT_APPLICABLE을 사용한다. fact_state는 not_needed / stated / unknown을 별도로 둔다. 기존 객체 버전과 호환되지 않는 새 상태 필드는 내부 스키마 버전을 명시한다.

- EVIDENCE_LINKED는 원문이 연결됐다는 뜻이며 의미상 정답 인증이 아니다.
- SEARCHED_UNRESOLVED에는 검색·참조 확인 기록과 범위·이유가 필요하다.
- NOT_APPLICABLE에는 비적용 근거·이유가 필요하며 단순 검색 실패로 설정하지 않는다.
- 원문 부재는 특정 판본·특정 구조 구간의 부재와 전체 의미상 규정 부재를 구별한다.
- 모델 제안으로 생성한 쟁점도 출처와 질문 관련성을 기록한다. 모든 유형·모든 검색 후보의 전수 판정을 요구하지 않는다.

세 가지 상태 축을 구별한다.

| 축 | 값 | 의미 |
|---|---|---|
| 실행 상태 | running / interrupted / completed / failed | 요청이 기술적으로 진행·종료되었는가 |
| 제어 결과 | RESEARCH / RECOMPOSE / FINAL | 다음에 어떤 단계를 실행하는가 |
| 최종 답변 범위 | READY / BOUNDED / CLARIFY | 확인된 범위와 남은 공백 |

FAILED를 법률적 부재나 정상 FINAL의 관문으로 포장하지 않는다. 기술 실패는 오류 응답과 journal에 남긴다. 예산 소진 후에도 일관된 부분 결과를 만들 수 있으면 FINAL+BOUNDED로 반환한다.

### 4.3 원문 구간과 전달 계보

EvidenceSpan은 generation_id, store_sha256, document_id, source_artifact_sha256, source_id, unit_id, block_id, start/end, text_sha256, role, temporal_status를 가진다. start/end는 원문 블록의 Unicode codepoint 기준이며 FTS 정규화 문자열 좌표를 쓰지 않는다. 서버가 좌표와 해시를 만든다.

역할은 normative / interpretive / reference를 구별한다. valid_from/valid_to/as_of는 확인되지 않으면 비워 두고 temporal_status=unknown으로 남긴다.

원문 단계는 다음과 같이 기록한다.

발견 → 원문 확보 → 특정 모델 입력에 전달 → 채택 제안 → 서버 반영 → 조립 입력 → 인용.

전달 영수증은 어떤 호출에 어떤 span이 들어갔는지 증명한다. 모델이 실제로 이해했다는 증명은 아니다. 제목 목록은 본문 전달로 세지 않는다. 모델이 현재 검토할 원문을 받지 않은 상태에서 제목만으로 채택을 완료하지 않는다.

긴 조문은 필요한 항·호와 예외/정의 의존 구간을 묶는다. 범위를 나눠 읽을 수 없거나 예산에 담지 못한 부분은 omission으로 기록한다. 하나의 handle이 가리키는 텍스트를 나중에 조용히 교체하지 않는다.

### 4.4 철회·충돌·파생 상태 무효화

근거 원문은 삭제하지 않고 쟁점별 Assessment를 수정한다. 한 쟁점에 부적합해도 다른 쟁점에는 필요한 원문일 수 있다.

철회/재평가 제안에는 대상 relation revision과 구체적인 원문 anchor 또는 재해석 이유를 요구한다. 서버는 ID·버전·권한을 확인하고 의미 판단은 contested/needs_review 상태로 보존할 수 있다.

영향 관계는 다음 순서로 무효화한다.

평가/사실/질문 해석 변경 → 의존 Claim stale → 해당 Claim의 Review stale → 선택·조립·답변 파생본 무효화.

과거 초안은 감사 기록으로 남긴다. 이미 반박된 초안을 예전 점수가 높았다는 이유로 복구하지 않는다. 복구 후보도 현재 사실·근거·공백과 양립해야 한다.

## 5. 내부 탐색과 agent 행동

### 5.1 도구 API

아래 이름은 제안 API다. 실제 하위 도구를 재사용하는 adapter가 필요하다.

| 제안 도구 | 현재 연결 지점 | 반환과 제한 |
|---|---|---|
| list_documents | FolderNavigator.catalogue | 문서·폴더·판본·cursor. 제목 목록은 근거가 아님 |
| list_structure | FolderNavigator.outline | 저장 source_unit 계층. 인쇄 목차라고 확정하지 않음 |
| read_node | FolderNavigator.read_unit, Store.section/source | 정확한 원문 blocks와 spans |
| search_text | 기존 FTS / 후보 Search / TermIndex | 검색어·범위·순위·다음 페이지·구간 후보 |
| search_subtree | folder_navigation.search_structure | 선택한 실제 하위 범위의 제목/본문 탐색 |
| locate_provision | 완료 후보 locator | 문서명+조문 좌표를 직접 열기, 모호함/판본 한계 유지 |
| lookup_definition | TermTools/TermIndex | 정의 원문과 적용 문맥 |
| follow_reference | 명시 참조·해소기·역참조 | source mention, target, provenance, resolution |
| inspect_work | 신규 WorkState view | 현재 주장·반대 근거·미확인·시도 이력 |

큰 장이나 전체 문서는 현재 read_unit의 단일 source article 제한을 고려하여 leaf/구간으로 분할한다. 빠진 표·별표·첨부는 DATA_GAP이며 모델이 내용을 보충해 원문으로 등록하지 않는다.

유효 범위는 trusted_allowed ∩ requested_scope ∩ binding에 포함된 판본 ∩ 전송 허용 범위다. 좁혀진 navigation context와 원래 요청의 허용 범위를 구별한다. 다른 문서 참조는 허용 범위 안에서 새 탐색 context를 만들 수 있지만 사용자의 문서 한정 지시는 유지한다.

### 5.2 탐색 선택·반례 검토

Investigator는 현재 중요한 미해결 쟁점과 Frontier를 보고 행동을 제안한다. 질문이 명시한 조문은 바로 열고, 문서가 불명확하면 목록·목차로 진입한다. “무조건 검색→상위 N개”나 “무조건 전체 목차” 순서를 강제하지 않는다.

Challenger는 질문·대상 주장·관련 원문·사용자 사실·미확인을 받아 구체적인 문제를 제시한다.
- UNSUPPORTED_CLAIM
- MISSED_QUALIFIER
- CONFLICTING_SOURCE
- MISSING_FACT
- WRONG_SCOPE_OR_VERSION
- CITATION_FORMAT_ERROR
- DATA_GAP

비판에는 대상 claim revision과 확인할 내용이 있어야 한다. Investigator의 장황한 설명을 그대로 복사하지 않으며 다른 원문 탐색을 제안할 수 있다. 같은 모델의 별도 호출을 독립된 정답 판정자로 간주하지 않는다.

원문이 새로 추가되지 않아도 기존 문구의 적용 주체·부정·조건을 잘못 읽었다는 구체적 지적은 유효한 수정 후보다. 반면 근거 없는 “더 검토하라” 반복은 무한 재시작 사유가 아니다.

원문 조회·목록 조회는 코드 검사로 종료할 수 있다. 확정적 적용 판단, 예외·위임 의존, 상충 근거 등 domain trigger가 있으면 targeted review를 수행한다. 실행 강도는 profile에 두고, 필요한 검토를 생략했다면 READY 대신 답변 범위를 제한한다.

## 6. 실행 순서와 파이프라인 재진입

### 6.1 정상 요청

1. Request 검증 → 질문·저장 판본·허용 범위 결속 → Query 한 번 생성.
2. 문서 목록/직독 요청인지, 법률 판단이 필요한지 분류.
3. 필요한 Issue와 Frontier 생성. 초기 조사 호출과 계획을 합칠 수 있다.
4. 모델의 탐색/평가 제안 검증 → 도구 실행 → Observation 저장.
5. 새로운 원문은 후속 모델 입력에 제시 → Assessment/Claim 갱신.
6. 중요한 반례·미해결을 검토 → 필요하면 조사 계속.
7. 현재 근거를 select/assemble → 자유 서술 compose.
8. 인용·계약 검사와 필요한 targeted review.
9. RESEARCH / RECOMPOSE / FINAL 결정.
10. 최종 의존성·권한·계약 검사 → checkpoint → 응답.

모델 호출 중 DB 쓰기 transaction을 오래 유지하지 않는다. 호출 전 snapshot과 expected revision을 고정하고, 돌아온 제안은 잠금/CAS로 적용한다. 같은 호출이 아직 읽지 못한 새 도구 결과를 그 호출의 평가 제안이 채택할 수는 없다.

### 6.2 재진입 제어

~~~text
retrieve → select → assemble → answer (+ 필요 시 review)
    ↑                             │
    └──────── RESEARCH ───────────┤
                      answer ← RECOMPOSE
                                  │
                                FINAL
~~~

- RESEARCH: retrieve부터 다시 실행. 현재 WorkState의 원문·시도 이력은 보존하고 select/assemble/answer 파생 산출물은 무효화한다.
- RECOMPOSE: 이미 검증된 assembly의 동일 근거만으로 표현·인용을 고친다. 출처 추가/제거 또는 평가 변경이면 RESEARCH로 처리한다.
- FINAL: 현재 유효한 결과와 READY/BOUNDED/CLARIFY 관문을 결합해 공개한다.

새 내부 control 포트를 engine manifest에 선언한다. 기존 result 외부 포트는 유지한다. control은 모델의 자유 서술에서 추출하지 않고, 검증된 review/state에 근거하여 서버가 생성한다.

제안 control.schema.json은 kind, event_id, run_id, query_id, binding_hash, expected_state_revision, evidence_revision, answer_revision, issue_ids, challenge_ids, reason_code 및 FINAL의 gate를 명시한다. 구조 검증은 revision의 실제 일치나 의미 정당성을 보장하지 않으며 Reducer/Coordinator가 따로 확인한다.

현재 Pipeline.run은 각 출력을 term-runtime-v1로 고정 검증한다. 계약 선언에 schema_id를 명시적으로 추가하고, 기존 항목에는 현행 URI를 적용하는 호환 분기를 둔다. 출력 포트 집합·manifest/code/schema hash 검사는 계속 유지한다.

두 포트 출력 후 observability는 사전 첫 value를 쓰지 않고 result/control을 명시적으로 선택해야 한다. result가 스키마에 맞더라도 control=FINAL 전에는 사용자 결과로 공개하지 않는다.

### 6.3 예산 종료와 무진전

예산에는 조사·반례·작성·형식 수리·전송 재시도를 모두 포함한다. provider timeout도 남은 deadline에 맞춘다. 물리적 취소가 불가능한 늦은 응답은 상태에 반영하지 않는다. 다른 provider로 숨은 fallback은 두지 않는다.

정확한 횟수·토큰·시간은 profile의 필수 동결 값이다. 실행 전 값이 없거나 예약된 종료 출력을 감당할 수 없으면 설정 오류로 처리한다. 검증되지 않은 횟수를 최적값으로 고정하지 않는다.

진전은 원문 전달, 구체적인 평가 변경, 유효 반례, 사실 정정, 범위를 갖춘 미확인 검색 결과로 나눠 기록한다. 동일 tool/args/scope/binding/cursor와 결과의 반복은 진전으로 세지 않는다. 새 페이지·새 사실·구체적 재해석 때문에 같은 자료를 읽는 것은 허용한다.

중요한 미확인이 남으면 READY로 종료하지 않는다. 작성 호출 여유가 없으면 이미 유효성이 확인된 문단과 미해결 표시를 결정론적으로 조립할 수 있다. 유효한 법률 주장이 없으면 claims를 비우고 확인하지 못한 범위를 설명한다.

## 7. 답변·인용 계약

자유 서술을 유지하되 주장 문단과 원문 handle을 연결한다. 모델이 원문 인용문을 새로 만들지 않도록 원문 표시는 서버의 exact span에서 가져온다.

- 없는 핸들은 해당 법률 주장 문단의 수리/보류 대상으로 삼는다. 핸들만 지우고 주장을 그대로 남기지 않는다.
- 유효한 핸들만으로 의미 지지가 검증된 것은 아니다.
- 수치·날짜·계산의 결정론 검사는 가능한 범위에 한정한다. 부정·예외·적용 주체 전체를 코드가 판단한다고 주장하지 않는다.
- 문단 단위로 claims를 만들고 소수점·날짜가 있는 문장을 마침표만으로 나누지 않는다.
- 모델이 새 법률 결론을 추가하면 검토 대상 Claim으로 등록한다. 기존 승인된 내용이라는 이유로 검토를 생략하지 않는다.
- clarification과 시스템 한계는 법률 주장과 구분한다.

외부 매핑:
- retrieval.candidates: 실제 원문을 읽은 article/source identity와 blocks. 제목 목록은 내부 state.catalogue.
- retrieval.term_agent: 내부 버전·binding·issues·selected_ids·전달/조사 요약.
- selection.method: 현 계약의 term-agent 상수 유지. 실제 구현 식별자는 내부 metadata.
- assembly.context: 채택 근거에 필요한 정확한 blocks, 기존 source ID와 출처.
- answer.claims.source_ids: 실제 context의 ID만 참조. span별 세부 연결은 journal/internal state.
- answer.unresolved: 사용자에게 이해되는 미해결 이유.
- answer.provider_receipt: 현행 필수 계약에 맞는 실제 호출 기록 연결. 자격정보·민감한 경로 제외.

API 응답 본문에 control·ledger를 최상위 임의 필드로 추가하지 않는다. app의 기존 run_id/release 외피와 Pipeline의 runtime.result 계약도 구별한다. GENOS 브릿지는 claims.source_ids를 정본으로 사용하고 미사용 context를 실제 출처처럼 표시하지 않는다.

## 8. 실패·권한·버전·재개

| 상황 | 처리 | 남는 결과 |
|---|---|---|
| 질문의 문서와 개념이 모호 | 해석 후보·분리된 scope 기록, 필요한 질문 | CLARIFY 또는 범위 제한 답변 |
| 유효 반례 발견 | Claim/Review stale, 재탐색 | 수정 계보와 새 답변 |
| 반례가 다른 주체 규정 | 적용 조건 확인 후 challenge 기각 가능 | 기존 주장 유지 이유 |
| 참조 대상이 없고 옛 연결은 틀림 | 옛 연결 무효화, UNRESOLVED_TARGET | 근거 공백 |
| 일부 항/별표가 없음 | DATA_GAP, 구조화 수정 후보 | 존재하지 않는 내용을 채우지 않음 |
| 모델 형식 오류 | error path를 포함한 제한 수리 | 실패 시 부분 결과/실패 기록 |
| timeout/429/응답 불명 | 실제 시도별 기록, 남은 예산 안에서 재시도 | 중복 과금 가능성은 별도 표시 |
| 늦은 응답/중복 control | event ID와 expected revision 검증 | 상태 중복 반영 없음 |
| 서버 재시작 | 원자적 checkpoint, running→interrupted | 자동 의미 재개는 최초판 범위 밖 |
| 데이터 세대 교체 | 기존 binding 유지 또는 새 요청 | 서로 다른 판본 혼합 금지 |
| 권한 취소 | 원문·파생 주장 재검토, 결과 전달 전 재검사 | 더 이상 허용되지 않는 내용 비공개 |
| 재탐색 예산 소진 | 유효 문단만 제한적으로 종합 | FINAL+BOUNDED |
| 무효화된 과거 답만 남음 | 해당 초안을 최종으로 복구하지 않음 | 미확인 설명 |
| 최종 checkpoint 실패 | 완료로 공개하지 않음 | 재시도/실패 상태 |
| 피드백 수집만 실패 | 이미 완료된 답은 유지, 후처리 실패 기록 | 답변과 학습 상태 분리 |

현재 HTTP는 trusted principal과 의미 재개 계약이 없다. 초기 배포는 승인된 공유 코퍼스 범위다. 팀별 ACL은 trusted gateway principal과 ACL resolver가 도입된 환경에서만 사용한다.

재개 v2는 run_id, base_revision, facts patch, idempotency, trusted identity를 포함하는 새 요청 계약과 소비자 갱신이 필요하다. 같은 binding에서 새 사실에 의존한 쟁점만 다시 열 수 있다. 판본·권한이 달라지면 새 scope/binding으로 재검증하고 과거 handle을 그대로 신뢰하지 않는다.

Journal은 run/event/call/checkpoint를 요청별로 저장한다. event ID 중복 방지, revision CAS, 원자적 write를 사용한다. write(open('x'))는 최초 파일 생성용이며 checkpoint 덮어쓰기 API로 재사용하지 않는다.

## 9. 실제 변경 지도와 이행

아래 신규 경로와 이름은 제안이다. 현재 제품에 구현됐다는 뜻이 아니다.

| 변경 지점 | 변경 내용 | 소비자·이행 |
|---|---|---|
| service.py._normalize/_call | 질문 본문과 전송 metadata 분리 | app Request allowlist·브릿지 fixture |
| semantic_runtime.pipeline.Pipeline | legal-agent-v1 adapter 선택, request-local Coordinator, 명시 control 전이 | 기존 implementation 선형 경로 유지 |
| semantic_runtime.stages | 같은 Query 재사용, 명시 adapter dispatch, result/control 포트 | 엔진 출력 계약·관찰 로그 |
| semantic_runtime.contracts | 선언된 schema_id/definition 처리 | 내부 제어 스키마 registry와 hash |
| semantic_runtime/legal_agent_adapter.py | 내부 state↔현행 runtime 포트 변환 | retrieve/select/assemble/answer |
| legal_agent/state.py, reducer.py | Issue/Assessment/Claim/Challenge·revision·stale 전파 | 조사·반례·작성 |
| legal_agent/tools.py | 기존 FolderNavigator/Store/FTS/TermIndex adapters | 원문/목록/참조의 공통 Observation |
| legal_agent/loop.py | investigate 분리, Frontier·전달·재평가 | Coordinator |
| legal_agent/challenger.py | 특정 주장 검토와 다음 확인 요청 | domain trigger + profile budget |
| legal_agent/composer.py, citations.py, checker.py | 유효 근거 묶음·문단 검사·의미 경계 | Answer 생성 |
| legal_agent/coordinator.py, journal.py | 단계 무효화·원자적 상태·최종 commit | Pipeline.run 내부; 새 standalone API 아님 |
| app.ask | 요청 ID 연결·실패 checkpoint·최종 일관성 | 기존 응답 외피, 후속 resume v2 |
| genos_rag_chat._used_source_ids/_sources | source_ids 소비, 실제 사용 출처 표시 | 사용자 답변 |
| PIPELINE.json, 엔진 manifest, release 묶음 | 내부 control 포트·허용 전이·새 코드/스키마 hash | 명시적 후보 선택·검증·rollback |
| feedback/개선 도구 | 근거 결속 제안·검토·검증 | 다음 후보 버전 |

재구축 범위:
- 원문 변경 없음: source store 재생성 불필요. 기존 blocks/IDs를 보존한다.
- 참조 출처·해소 방식 변경: 파생 navigation/reference 색인을 새 지문으로 구축하고 필요한 하위 세대를 갱신한다.
- 원문 구조·표·별표 수정: 새 source generation과 의존 색인을 생성한다.
- 코드·profile만 변경: 해당 manifest와 릴리스 지문을 갱신한다.
- 의미 재개/API 확장: 요청 스키마·app·workflow·runner·fixture를 함께 이행한다.

완료 ADR의 frozen snapshot과 기존 활성 릴리스는 덮어쓰지 않는다. 후보 실행·Git 병합·MAIN 승격·GENOS 배포를 별도 상태로 기록한다.

## 10. 요청 사이의 개선 루프

실행 기록/사람 정정 → 실패 위치 분류 → 수정 후보 → 계약 검사 → 품질 비교 → 채택/기각 → 다음 버전.

개선 대상은 검색어/별칭, 원문 참조 해소, 읽기 절차, 모델 profile, reducer/adapter 코드, 구조화 데이터 등이다. 개선 agent는 관련 코드·로그·계약을 읽고 격리된 후보를 수정할 수 있다. 답변 서비스의 ToolBroker와 개발용 코드 쓰기 권한은 구별한다.

재사용하는 기억은 과거 답문 자체보다 “어떤 질문 조건에서 어떤 정의·예외·원문을 확인했는지”다. 현재 판본을 다시 읽고 stale feedback을 검토한다. 잘못된 근거도 전역 삭제하지 않고 해당 오류 맥락을 보존한다.

평가용 기준답변은 제품 context에 들어가지 않는다. 모델의 자기 평가 점수나 사람의 근거 없는 단일 피드백을 정본으로 자동 승격하지 않는다. 현재 PROPOSED 기록 이후의 검토·검색 반영은 새 구현 범위이며 완료된 기능이 아니다.

## 11. 검증·도입·담당 책임

T01~T20의 상세 입력·기대 전이는 acceptance-scenarios.json에 있다. 모두 계획된 검증이며 제품 구현 통과 여부는 pending이다.

| 단계 | 산출물 | 종료 조건 | 책임 역할 |
|---|---|---|---|
| P0 기준·계약 | 정확한 부모 arm, binding, control/state 계약, 평가 계획 | scope/성공 기준/허용 회귀/예산을 결과 전에 동결 | 설계·실험 담당 |
| P1 상태·원문 | reducer, span 보존, 철회, journal | T05~T09/T13/T18의 모델 없는 검사 | runtime 담당 |
| P2 탐색·역할 | 기존 구조 도구와 Investigator/Challenger 연결 | T01~T04/T10~T11, 모의 관찰로 탐색→수정 흐름 확인 | 도메인·agent 담당 |
| P3 API 수직 연결 | Coordinator/control/adapter/브릿지 | T12/T14~T17, 실제 단계 계약과 최종 일관성 | runtime·서빙 담당 |
| P4 품질 실험 | 기준/후보의 고정 입력·로그·평가 | T20, 회복·회귀·미답변·자원 비교 및 독립 표본 검증 | 평가·도메인 담당 |
| P5 현장·개선 | GENOS 기록·검토된 피드백·재개 v2 | T19 및 해당 후속 계약·현장 증거 | 현장 운영·도메인 담당 |

실제 담당자 이름·달력 일정은 배정 전이다. 역할을 지정했다고 구현 인력이 확보되었다고 보지 않는다.

첫 수직 완료 기준은 “초기 채택을 추가 탐색으로 재평가하고, 의존 주장을 수정한 뒤, 같은 판본의 새 근거와 일치하는 답변을 반환”하는 것이다.

품질 실험에서는 근거 보존/상태 수정, 내부 탐색, targeted review, 피드백 기억의 효과를 분리한다. 서로 다른 모델·다른 입력으로 얻은 차이를 특정 부품의 인과 효과로 단정하지 않는다.

eval plan의 필수값은 평가 사례와 판본, 기준 arm, 후보 hash, primary metric, 허용 회귀, 비열등 기준, 비용/지연 상한, 독립 표본 분할, judge/human adjudication 정책이다. 값이 없으면 비교를 시작하지 않는다. 아직 측정하지 않은 품질 임계값을 검증된 가능치로 쓰지 않는다.

원문/인용/권한/스키마의 결정론 계약 위반은 관문에서 허용하지 않는 목표다. 의미 정확도는 별도 기준으로 평가한다. 의역·반복 실행을 독립 사례로 과대 계산하지 않는다.

활성화는 저장소의 후보 동결·검증·MAIN 승격 절차를 따른다. rollback은 검증된 기존 implementation/release와 대응 데이터 세대로 되돌리는 방식이며 후보 원장과 실패 이력은 보존한다.

## 12. 근거 수치와 기대효과의 한계

| ID | 종류 | 값·단위·분모 | 근거·해석 |
|---|---|---|---|
| N01 | 관측 | ADR-0438 읽기/설명 각각 0/6, ADR-0440도 각각 0/6 | S03. 실패 원인은 각각 모델 좌표/재시도, 문서 범위·개념 혼동. 일반 전체 정답률로 확대 안 함 |
| N02 | 관측 | ADR-0469 Gemini v2 38/51→v3 36/51; Qwen 30/51→34/51 | S05. 동일 규칙판 효과가 모델별로 달랐음 |
| N03 | 관측 | ADR-0466 저장 집계 호출 Gemini 91→274, Qwen 92→282 | S04 compose.calls. 두 실행을 묶은 해당 집계이며 실패 호출의 과금 전체를 새로 확인한 값은 아님 |
| N04 | 관측 | ADR-0466 Gemini plain/audit 각각 30·30/51; Qwen plain 27·28/51, audit 27·27/51 | S04 by_arm.per_run. 전면 확인표의 품질 이득 없음 |
| N05 | 관측 | 생성/입력 카드 Gemini 963/906, Qwen 903/849 | S08. 문항×조문 쌍, 차이 57/54. 결정 조문 생성/입력은 68/68, 65/64 |
| N06 | 관측·모의 | 실제 조립 6,000자 절단 각 arm 1건; 모의에서는 필요한 뒷부분 손실 | S08/S09. 실제 CM 오답의 절단 인과는 미확인. 기존 카드 긴 조각 손실 검사에서는 0건 |
| N07 | 관측 | rev3 Gemini 40/51, Qwen 35/51. Qwen rev2 34 대비 회복 5·회귀 4 | S06. in_sample=true, decision_eligible=false. Qwen rev3 미채택 |
| N08 | 관측 | rev4 중간 짝 추가 Gemini 15/20→15/20, Qwen 14/22→13/22 | S07. subset/중간 결과. 전체 rev4 완료 성능 아님 |
| N09 | 관측 | rev3 모델 요청 176/51, 180/51 | S08. 평균 3.451/3.529회. E2E 지연과 별개 |
| N10 | 계산·가정 | 추가 0.5회/질문이면 Gemini 기준 호출 수 약 +14.5% | 0.5 ÷ (176/51). 설명 시나리오이며 실제 증가 예측·비용 증가율 아님 |
| N11 | 미확인 | 최종 설계 정확도·p95·동시 처리량·현장 비용·개발 일정 | 새로운 후보·독립 평가·현장·작업 시간 자료 필요 |

N03은 이전 문서의 “92→274~282” 합산 표현을 원시 집계에 맞춰 모델별로 정정한 값이다. 기존 실험 기록은 변경하지 않았다.

자원 식:
- 추가 호출/질문 = p_review×c_review + p_research×c_research + p_recompose×c_recompose - c_saved.
- 설명 가정 p_review=0.3, c_review=1, p_research=0.1, c_research=2, 나머지 0이면 +0.5회/질문.
- 같은 가정에서 p_research=0.2로 바꾸면 +0.7회/질문. 호출 증가율은 약 20.3%이며 역시 비용·지연 증가율이 아니다.
- 비용 = 실제 입출력 토큰별 비용 + 색인/저장/평가/운영 비용. 누락된 금액을 0으로 기록하지 않는다.
- 경제적 손익분기 = 줄어든 사람 재검토·오류 처리 비용 ≥ 추가 모델·구축·평가·운영 비용. 현재 입력이 없어 금액 미산정.

개발 일정은 P0~P5 작업 분해로 관리하고 실제 담당·의존성과 첫 연결 작업의 소요를 측정한 뒤 추정한다. 근거 없는 인일이나 성공 확률은 제시하지 않는다.

## 13. 자체 검토와 미해결 사항

문서 연결 가능성은 필요한 구현을 명시한 조건부 타당으로 판단한다. 성능 예측은 미검증이다. 자체 검토 기록은 SELF_REVIEW.md에 별도로 보존한다.

이번 문서의 정합성 검사는 결정↔근거↔시나리오 연결, 출처 파일 hash, 링크, 숫자 재계산, 제안 control의 JSON 구조를 확인한다. 실제 Reducer/Coordinator·모델·서빙 통합 테스트가 아니다.

남은 구현·검증:
- 근거 의미 평가와 잘못된 challenge가 일으키는 회귀.
- 최소 장부가 필요한 쟁점을 충분히 포착하는지.
- 정확한 구간 묶음·참조 해소의 실제 코퍼스 품질.
- 반복 조사 종료 상한·문맥·지연의 적정 설정.
- GENOS 내부 데이터·모델·권한·저장 경로.
- 사용자 재개 및 장기 피드백 루프.

선행 설계의 JSON 예제는 당시 스키마 설명용이다. 새 제어의 문서 정본은 이 폴더 control.schema.json이다. 전체 WorkState의 생산용 스키마·마이그레이션과 의미 전이 검사는 P0~P3에서 구현해야 한다.

## 14. 직접 확인한 원자료

- [S01 MAIN 아키텍처](/home/jin/8-AGENT/00_SYSTEM/ARCHITECTURE.md)
- [S02 법률 에이전트 구조·실험 경과](/home/jin/8-AGENT/07_DOCS/REFERENCE/ARCHITECTURE/LEGAL_AGENT_SYSTEM.md)
- [S03 이전 작업 하네스 실패 기록](/home/jin/8-AGENT/07_DOCS/REFERENCE/OPERATIONS/TASK_HARNESS.md)
- [S04 ADR-0466 원시 집계](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0466-legal-agent-composer-audit/artifacts/metrics.json)
- [S05 ADR-0469 모델별 규칙 비교](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0469-legal-agent-loop-rev2/artifacts/metrics.json)
- [S06 ADR-0472 완료 실험](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0472-legal-agent-loop-rev3/README.md)
- [S07 ADR-0473 중간 위임 짝 관문](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0473-legal-agent-loop-rev4/artifacts/s1-gate.json)
- [S08 기존 요청 payload·연결 진단](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/existing-run-diagnostics.json)
- [S09 이전 모의 코드 재현 결과](/mnt/c/Users/Jin/.codex/visualizations/2026/09/19/01a0b8bb-63c3-7c20-a211-df3661760a5d/legal-agent-review-checks.json)
- [S10 완료 rev3 탐색 루프](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/loop.py)
- [S11 완료 rev3 조립기](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/composer.py)
- [S12 완료 rev3 인용 렌더러](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/citations.py)
- [S13 완료 rev3 참조 해소기](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/references.py)
- [S14 기존 폴더·목차·구간 탐색](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/folder_navigation.py)
- [S15 원문 Store](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/storage.py)
- [S16 현재 파이프라인 실행기](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/pipeline.py)
- [S17 현재 단계 포트](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/stages.py)
- [S18 현재 외부 RAG 계약](/home/jin/8-AGENT/00_SYSTEM/SCHEMAS/term-runtime-v1.schema.json)
- [S19 GENOS 요청 정규화](/home/jin/8-AGENT/service.py)
- [S20 HTTP 요청·최종 저장](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/app.py)
- [S21 GENOS 답변·출처 소비자](/home/jin/8-AGENT/08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py)
- [S22 현재 피드백 제안](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/feedback.py)
- [S23 선행 상세 설계](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/DESIGN.md)
- [S24 선행 반복 탐색 설계](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/AGENTIC_EXPLORATION_IMPLEMENTATION.md)
- [S25 로컬 활성 포인터](/home/jin/8-AGENT/01_DATA/ACTIVE/local/ACTIVE_RELEASE.json)
- [S26 ADR-0473 진행 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0473-legal-agent-loop-rev4/README.md)
- [S27 계약 registry/validator](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/contracts.py)
- [S28 현재 문서 agent 자원·요청 격리](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/document_agent.py)
- [S29 현재 파이프라인 선언](/home/jin/8-AGENT/00_SYSTEM/PIPELINE.json)
- [S30 GENOS 접근·실행 경계](/home/jin/8-AGENT/GENOS.md)
- [S31 현재 도메인 초기 규칙](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/harness.py)
- [S32 현재 조립 의미·수치 검사](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND/legal_agent/checker.py)

