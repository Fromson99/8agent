# FDE AX·RAG Delivery Manual

> 기업 현장에서 데이터를 발견하고, 검증 가능한 실험셋을 만들고, 온프레미스에서
> 재현 가능한 실험·튜닝·배포·운영 루프를 고객 조직에 이식하기 위한 실무 표준안.

## 0. 이 매뉴얼의 계약

### 0.1 목적

이 문서는 FDE(Forward Deployed Engineer)가 고객사에 투입되어 다음 상태를 만드는
과정을 표준화한다.

1. 업무 문제를 RAG가 풀 수 있는 검증 가능한 문제로 바꾼다.
2. 고객 데이터를 정본화하고 데이터 계보를 만든다.
3. 실제 업무를 대표하는 골든셋과 실패 분류체계를 만든다.
4. 동일 조건에서 baseline과 candidate를 비교할 수 있는 실험환경을 구축한다.
5. 데이터·검색·컨텍스트·프롬프트·모델을 순서대로 튜닝한다.
6. 이 전 과정을 고객사의 온프레미스 환경에서 반복 가능하게 만든다.
7. FDE가 철수한 뒤에도 고객팀이 스스로 골든 추가, 실험, 릴리스, 롤백을 수행한다.

### 0.2 AX의 완료 정의

PoC가 동작하거나 답변 예시 몇 개가 좋아진 것은 AX 완료가 아니다. 다음 네 가지가
동시에 만족되어야 한다.

| 축 | 완료 상태 |
|---|---|
| Business | 대상 업무의 시간·오류·처리량·위험 지표가 사전에 합의한 폭만큼 개선된다. |
| Evidence | 개선이 고정된 골든셋과 재현 가능한 실험 결과로 입증된다. |
| System | 고객 온프레미스에서 데이터 반입부터 평가·배포·롤백까지 자동 또는 문서화되어 있다. |
| Organization | 고객 담당자가 FDE 없이 신규 데이터와 실패 사례를 다음 버전에 반영할 수 있다. |

가장 강한 종료 기준은 다음 한 문장이다.

> 고객팀이 FDE 없이 같은 baseline을 재현하고, 신규 골든 케이스를 추가하고,
> candidate를 검증하여 배포하거나 롤백할 수 있다.

### 0.3 대상 독자

- 고객 현장에 투입되는 FDE와 Solution Architect
- 고객사의 AX/AI CoE, 플랫폼, 보안, 데이터, 현업 SME
- RAG 제품 Owner, QA/Evaluation Engineer, MLOps/LLMOps Engineer
- 프로젝트를 승인하는 업무 책임자와 위험관리·준법·감사 담당자

### 0.4 비목표

- 특정 벡터DB·LLM·클라우드 제품의 사용법만 설명하지 않는다.
- 프롬프트 모음집을 만들지 않는다.
- 모든 문제에 RAG를 적용하도록 유도하지 않는다.
- LLM 평가 점수 하나로 출시를 자동 결정하지 않는다.
- FDE의 개인 경험과 수동 작업에 운영이 영구 의존하도록 만들지 않는다.

## 1. FDE Delivery의 핵심 원칙

### 1.1 세 개의 계약을 먼저 만든다

모든 프로젝트는 코드보다 먼저 다음 세 계약을 만든다.

| 계약 | 질문 | 필수 산출물 |
|---|---|---|
| 업무 계약 | 무엇을 얼마나 개선하면 성공인가? | Use-case charter, KPI, 오류 비용, 범위·비범위 |
| 평가 계약 | 어떤 데이터와 기준으로 더 좋아졌다고 말할 것인가? | Golden set, metric dictionary, 실험·통계 protocol |
| 운영 계약 | 누가 어떤 환경에서 데이터·모델·릴리스를 관리하는가? | On-prem architecture, RACI, SLO, 배포·롤백 runbook |

세 계약 중 하나가 비어 있으면 프로젝트는 각각 다음 형태로 실패한다.

- 업무 계약 부재: 기술 데모는 성공하지만 현업이 쓰지 않는다.
- 평가 계약 부재: 회의 때마다 “좋아 보인다”와 “아니다”가 반복된다.
- 운영 계약 부재: PoC는 끝났지만 고객 환경에 들어가지 못한다.

### 1.2 기술보다 업무 표본을 먼저 고정한다

FDE의 첫 산출물은 모델 선택표가 아니라 다음이어야 한다.

- 실제 사용자와 승인된 업무 흐름
- 실제 질문·문서·답변·수정·거절 사례
- 잘못된 답변이 만드는 비용과 위험
- 답변이 없거나 모호할 때 기대되는 행동
- 현재 업무의 처리시간과 품질 baseline

### 1.3 RAG는 하나의 모델이 아니라 데이터 시스템이다

RAG 결과는 대략 다음 함수로 본다.

```text
Outcome = f(
  source quality,
  corpus coverage,
  parsing,
  structure/metadata,
  access control,
  query understanding,
  retrieval,
  reranking,
  context assembly,
  generation,
  evaluation,
  operations
)
```

따라서 답이 나쁠 때 곧바로 LLM을 교체하거나 fine-tuning하지 않는다. 먼저 어느
단계에서 필요한 정보가 소실되었는지 trace로 확인한다.

### 1.4 골든셋은 정답집이 아니라 제품 사양이다

좋은 골든 케이스는 질문과 한 줄 답만 갖지 않는다. 최소한 다음을 갖는다.

- 어떤 사용자가 어떤 업무 상황에서 묻는지
- corpus 기준시점과 답변 가능 여부
- 반드시 포함해야 할 claim
- 각 claim을 지지하는 정확한 문서·구간·좌표
- 허용 가능한 다른 답변
- 포함하면 안 되는 주장과 오염 근거
- 거절·추가질문·human handoff 조건
- 업무 위험도와 오류 비용

### 1.5 부품 점수와 제품 점수를 분리한다

- Retrieval Recall이 높아도 최종 답이 틀릴 수 있다.
- 최종 답이 맞아도 citation이 틀릴 수 있다.
- 평균 점수가 좋아도 고위험 질문이 회귀할 수 있다.
- 호출 수가 줄어도 answerability 판단이 나빠질 수 있다.

따라서 component test, E2E test, operational test를 모두 유지하되 서로 대체하지 않는다.

### 1.6 한 번에 한 인과 질문을 묻는다

초기 진단과 release 직전 확인은 가능한 한 한 변수 paired A/B로 수행한다. 탐색 단계에서
여러 변수를 스크리닝할 수 있지만, 운영 기본값을 바꾸는 최종 근거는 동일 suite,
동일 case 순서, 동일 corpus, 동일 평가기에서 만든다.

### 1.7 코드·데이터·모델·평가기의 판을 모두 기록한다

Git commit만으로 RAG 실행을 재현할 수 없다. corpus, parser, chunker, index,
embedding model, prompt, LLM, judge, 실행 seed와 설정 fingerprint를 함께 남긴다.

### 1.8 온프레미스에서는 운반과 재생이 제품 기능이다

망분리 환경에서는 다음이 부가기능이 아니다.

- 검증 가능한 데이터 package와 checksum
- 내부 artifact/model/container registry
- target 환경에서의 재색인
- snapshot, outbox, replay
- 승인·감사 로그
- offline dependency와 rollback package

### 1.9 고객 소유권을 매 단계 늘린다

FDE가 모든 실험을 대신 수행하면 단기 속도는 빠르지만 AX는 실패한다. 각 단계는
고객 공동 Owner를 두고, 마지막 두 번의 반복은 고객 담당자가 실행하도록 한다.

### 1.10 “더 복잡함”은 개선 근거가 아니다

새 검색 채널, agent, LLM 호출, knowledge graph, fine-tuning은 각각 다음 중 하나를
골든에서 입증해야 유지한다.

- 정답 evidence의 순증가
- 명확한 오염·위험 차단
- 업무상 필수 완전성 보장
- 비용·지연 감소

## 2. 전체 Delivery Lifecycle과 Gate

### 2.1 단계 요약

| 단계 | 목적 | 핵심 산출물 | 통과 Gate |
|---|---|---|---|
| 0. Qualify | RAG/AX 문제인지 판별 | Opportunity brief | Sponsor와 측정 가능한 문제 합의 |
| 1. Discover | 업무·보안·시스템 경계 파악 | Discovery pack | 데이터 접근과 책임자 확정 |
| 2. Frame | 업무가치를 평가 가능한 use case로 변환 | AX charter | KPI·MDE·위험 기준 승인 |
| 3. Survey | 데이터 현황과 온프레미스 제약 조사 | Data/site survey | source·권한·운반 경로 확인 |
| 4. Prepare | 정본 corpus와 lineage 구축 | Versioned corpus | coverage·freshness·ACL 기준 통과 |
| 5. Golden | 대표 실험셋과 rubric 구축 | Golden v1 | 품질검수·분할·동결 완료 |
| 6. Baseline | 현재 성능과 비용을 측정 | Baseline report | 재현 가능한 기준선 확보 |
| 7. Experiment | 가설별 candidate 비교 | Experiment manifests | 인과·통계·guardrail 조건 충족 |
| 8. Tune | 가장 큰 오류군부터 개선 | Tuned candidate | locked test에서 비열등/개선 |
| 9. Industrialize | 온프레미스 운영환경 구축 | RAGOps platform | rebuild·deploy·observe 가능 |
| 10. Release | 보안·부하·회귀 검증 후 전환 | Release evidence | 승인·canary·rollback 완료 |
| 11. Operate | drift와 신규 실패를 학습 루프로 전환 | Golden vNext | 정기 재평가와 ownership 작동 |
| 12. Transfer | 고객 자립과 FDE 철수 | Handover pack | 고객 단독 dry-run 통과 |

### 2.2 기본 RACI

| 활동 | FDE | Product Owner | Domain SME | Data Owner | Platform/MLOps | Security | QA/Eval |
|---|---|---|---|---|---|---|---|
| Use case와 KPI | R | A | C | I | I | C | C |
| 데이터 반입·정본 | C | I | C | A/R | C | C | I |
| 골든 설계·라벨 | R | A | A/R | C | I | I | R |
| 실험 runner | A/R | I | C | C | R | I | R |
| 온프레미스 배포 | C | I | I | C | A/R | A/C | C |
| Release gate | C | A | A/C | C | R | A/C | R |
| 운영·drift | C→I | A | C | C | R | C | R |

`A`는 한 활동에 원칙적으로 한 명 또는 한 조직만 둔다. “모두가 책임자”는 실제로
책임자가 없는 상태다.

## 3. 단계별 실행 매뉴얼

## Phase 0. Opportunity Qualification

### 목표

RAG가 실제 병목을 해결할 수 있는지, 해결 가치와 데이터 기반이 있는지 빠르게 판별한다.

### 확인 질문

1. 사용자는 누구이며 어떤 결정을 내리는가?
2. 현재 입력, 처리, 산출, 검토, 승인 흐름은 무엇인가?
3. 현재 평균·p95 처리시간과 재작업률은 얼마인가?
4. 정답의 근거가 조직 내부 데이터에 존재하는가?
5. 근거가 없을 때 시스템이 거절할 수 있는가?
6. 오류가 나면 금전·법률·안전·평판 비용은 얼마인가?
7. 8~12주 안에 대표 표본과 Owner를 확보할 수 있는가?
8. 데이터의 외부 반출·모델 전송이 허용되는가?

### RAG 적합성 판정

| 신호 | 판정 |
|---|---|
| 답이 문서와 데이터에 있고 출처 제시가 중요 | RAG 적합 |
| 정형 DB 계산과 정확한 숫자 집계가 중심 | SQL/규칙/도구 호출을 우선하고 RAG는 설명 계층으로 제한 |
| 답이 corpus에 없고 사람의 창의적 판단이 핵심 | 의사결정 보조 또는 workflow redesign 검토 |
| 최신 데이터와 강한 권한 통제가 필요 | RAG 가능하나 metadata/ACL/freshness가 핵심 기능 |
| 대량 분류·추출이 중심이고 출력 schema가 안정 | 작은 모델/규칙/추출 pipeline부터 검토 |

### 산출물

- 2쪽 이내 Opportunity brief
- 현재 업무 baseline과 목표 KPI
- 주요 위험과 비범위
- 첫 번째 20~30개 대표 사례 후보
- 고객 Sponsor, Product Owner, Domain SME, Data Owner

### Gate 0

- 측정 가능한 결과가 없다면 중단하거나 discovery 범위만 승인한다.
- 업무 Owner 또는 데이터 접근 경로가 없으면 PoC 일정을 확정하지 않는다.

## Phase 1. Discovery와 업무 관찰

### 목표

회의에서 설명된 표준 절차가 아니라 실제 업무가 수행되는 방식을 관찰한다.

### 실행 순서

1. 업무 담당자 3종 이상을 인터뷰한다: 고성과자, 평균 사용자, 신규 사용자.
2. 최근 성공 사례와 실패·재작업 사례를 화면 공유로 재생한다.
3. 질문이 발생한 원인, 찾은 자료, 제외한 자료, 최종 판단, 승인자를 기록한다.
4. 사용자 표현과 공식 문서 표현의 차이를 수집한다.
5. “답을 모름”, “자료 부족”, “권한 없음”, “질문 모호”를 별도 상태로 기록한다.
6. 업무의 전후 시스템, 파일, 메일, DB, 포털, 수동 Excel을 연결한다.
7. 개인정보·기밀·영업비밀·규제정보의 경계를 표시한다.

### 인터뷰 결과를 다음 형태로 정리한다

```yaml
job_to_be_done: "담당자가 신규 계약의 규정 위반 가능성을 검토한다"
actor: "준법 담당자"
trigger: "계약 검토 요청 접수"
inputs: [계약서, 내부 규정, 관련 법령, 이전 검토]
decisions: [적용 규정, 예외, 추가 자료 필요, 승인/반려]
outputs: [검토 의견, 근거, 후속 조치]
current_time_minutes: {p50: 90, p95: 240}
failure_modes: [근거 누락, 옛 규정 사용, 다른 법인 규정 혼입]
human_approval_required: true
```

### 산출물

- As-is process map
- User/query taxonomy 초안
- Source inventory 초안
- 실패·위험 taxonomy 초안
- 보안·권한·망 경계도

### Gate 1

- 실제 사례를 최소 한 번 end-to-end로 재생했다.
- 업무팀과 IT팀이 같은 문제 정의에 서명했다.
- 데이터 제공자와 승인자가 이름으로 지정됐다.

## Phase 2. AX Charter와 평가 계약

### 목표

“RAG를 잘 만들자”를 검증 가능한 제품 목표로 바꾼다.

### Charter 필수 항목

```yaml
use_case_id: AX-RAG-001
business_owner:
users:
in_scope:
out_of_scope:
baseline_process:
business_kpi:
primary_quality_metric:
minimum_detectable_effect:
guardrails:
  - high_risk_unsupported_claim_rate
  - p95_latency
  - cost_per_case
  - access_control_violation
human_in_the_loop:
release_rule:
stop_rule:
```

### Metric 선정 원칙

- Primary metric은 한두 개로 제한한다.
- 높은 평균이 심각한 오류를 숨기지 않도록 risk guardrail을 별도로 둔다.
- 품질, 지연, 비용, 운영 안정성을 한 숫자로 섞지 말고 함께 판정한다.
- 점수 차이보다 업무적으로 의미 있는 최소 개선폭(MDE)을 먼저 정한다.

### Gate 2

- 변경 전에 metric, MDE, guardrail, release rule이 문서화됐다.
- 현업과 기술팀이 “어떤 결과면 실패인가”에 합의했다.

## Phase 3. Data와 On-prem Site Survey

### 목표

데이터와 인프라의 실제 경계를 확인하여 뒤늦은 반입·보안·성능 문제를 막는다.

### 3.1 Data source card

각 source에 다음 카드를 만든다.

```yaml
source_id:
business_owner:
technical_owner:
system:
location:
formats: [pdf, docx, hwp, html, db]
volume:
change_rate:
effective_date_field:
retention:
classification:
acl_model:
extraction_method:
incremental_key:
quality_issues:
legal_basis_for_use:
```

### 3.2 반드시 실측할 항목

- 문서 개수·크기·페이지 수·언어·스캔 비율
- 표, 이미지, 각주, 병합셀, 목차, 첨부, 링크 비율
- 중복, 개정판, 폐기 문서, 제목 충돌
- 접근권한 상속과 사용자/부서별 제한
- 생성일, 시행일, 폐기일, 최신판 판정 규칙
- 수집 API, export, 파일 전달, DB read replica 가능 여부
- 망간 운반 경로와 최대 파일 크기
- 내부 Git, container registry, package mirror, model registry
- GPU/CPU 종류·수량·VRAM, storage IOPS, network 대역폭
- 외부 DNS/인터넷 차단, 프록시, 인증서, 시간 동기화
- 로그에 남겨도 되는 정보와 마스킹 규칙
- 백업, DR, 취약점 점검, 반입 승인 lead time

### 3.3 On-prem feasibility test

본 개발 전에 다음을 작은 패키지로 검증한다.

1. 코드 artifact 반입과 내부 Git push
2. container build 또는 내부 Python package 설치
3. 1개 문서 parse
4. 100개 chunk embedding
5. LLM과 embedding endpoint 호출
6. 결과 로그와 artifact 저장
7. snapshot 반출 또는 승인된 리포트 반출
8. 이전 version rollback

### 산출물

- Data inventory와 source card
- Site survey와 dependency gap
- Security data-flow diagram
- 반입·반출·승인 runbook 초안
- 용량·성능 sizing 가정

### Gate 3

- 목표 환경에서 최소 end-to-end smoke test가 실행됐다.
- target 환경에서 사용할 embedding/LLM의 정확한 ID와 호출 계약이 확인됐다.
- 영속 볼륨, secrets, logs, backup Owner가 확정됐다.

## Phase 4. Corpus Preparation과 Data Lineage

### 목표

“파일이 있다”를 “어떤 원문에서 어떤 변환을 거쳐 어떤 index에 들어갔는지 설명할 수
있다”로 바꾼다.

### 권장 계층

```text
raw/source
  → normalized document
    → parsed structure
      → chunks/passages
        → enrichment/metadata
          → lexical index + vector index + graph/relations
```

### 각 단계 필수 기록

| 단계 | 필수 기록 |
|---|---|
| 수집 | source URI/ID, 수집시각, 원문 sha256, 상태, 오류 |
| 변환 | parser와 version, 입력 sha, 출력 sha, 손실 경고 |
| 구조화 | 문서/section ID, heading path, page/offset, table relation |
| Chunk | chunker version, parent/child, 길이, overlap, ACL, 유효시점 |
| Enrichment | 생성 모델·prompt·version, confidence, human approval |
| Index | embedding model ID, dimension, normalization, index config, build ID |

### 정본 원칙

- 파일명이나 제목을 계보 join key로 사용하지 않는다.
- 가능한 경우 원문 body sha256과 안정적인 source ID를 함께 쓴다.
- parser 결과와 LLM enrichment를 원문과 분리한다.
- LLM이 생성한 요약·태그·관계는 evidence가 아니라 파생 데이터로 표시한다.
- 최신 문서만 남기지 말고 개정 계보와 유효시점을 보존한다.
- 권한 metadata는 생성 단계부터 chunk와 index까지 전달한다.

### Parser QA

문서 유형별로 대표·최악 사례를 정해 다음을 검사한다.

- 제목과 본문 순서
- 표 행·열과 병합셀
- 각주·단서·예외
- 페이지와 원문 좌표
- OCR 문자 오류와 누락
- 문서 끝 잘림
- 첨부와 본문의 연결

Parser 품질은 검색 결과를 보기 전 별도 골든으로 측정한다. 잘못 파싱된 근거는 검색과
LLM 튜닝으로 복구하려 하지 않는다.

### Gate 4

- corpus coverage, parse success, ACL coverage, freshness 수치가 나온다.
- 임의 답변에서 원문까지 역추적 가능하다.
- index와 query가 동일 embedding model 계약을 사용한다.

## Phase 5. Golden Set 구축

### 5.1 네 종류의 세트를 분리한다

| 세트 | 용도 | 공개 범위 | 갱신 원칙 |
|---|---|---|---|
| Dev | 오류 분석과 튜닝 | 개발팀 공개 | 자주 갱신 가능 |
| Locked test | release 비교 | 제한 공개 | 결과를 보고 튜닝하면 새 version 필요 |
| Challenge | 노이즈·오염·고위험 | 제한 공개 | 실패 taxonomy 확대 |
| Rolling shadow | 최신 실사용 분포 | Eval Owner 제한 | 주기적으로 라벨 후 다음 locked set 후보 |

### 5.2 표본 설계

단순 무작위보다 다음 층을 교차한다.

- 업무 유형과 사용자 유형
- 질의 빈도와 비즈니스 가치
- 오류 위험도
- answerable / partially answerable / unanswerable
- single-hop / multi-hop
- point fact / comparison / procedure / synthesis
- 최신성·시점 의존
- 모호한 질문과 추가질문 필요
- 동의어·약어·오타·구어체
- 표·이미지·첨부·스캔 문서
- 관련 있지만 답이 없는 distractor
- 상충하거나 오래된 evidence
- 접근권한이 다른 문서

빈도만 따르면 드문 고위험 사례가 사라지고, 전문가가 만든 어려운 문제만 모으면 실제
사용 분포가 사라진다. 따라서 traffic-weighted core와 risk-weighted challenge를 함께 둔다.

### 5.3 Golden case schema

```yaml
case_id:
source: production_log | SME | incident | synthetic
query:
conversation_context:
user_segment:
business_task:
query_type:
difficulty:
risk_level:
corpus_version:
as_of_time:
answerability: answerable | partial | unanswerable | ambiguous
required_claims:
  - claim_id:
    text:
    weight:
    evidence:
      - document_id:
        passage_id:
        quote:
        valid_from:
        valid_to:
acceptable_variants:
forbidden_claims:
expected_action: answer | clarify | abstain | handoff
retrieval_qrels:
  - passage_id:
    relevance: 0 | 1 | 2 | 3
annotation:
  guideline_version:
  annotators:
  adjudicator:
  status:
```

### 5.4 Annotation workflow

1. FDE와 SME가 20~30건으로 guideline v0를 만든다.
2. 두 annotator가 같은 calibration set을 독립 판정한다.
3. 불일치 이유를 `정의 불명확`, `근거 부족`, `업무 판단 차이`, `오표기`로 분류한다.
4. guideline을 수정하고 calibration을 반복한다.
5. 본 라벨은 고위험·모호 케이스를 이중 라벨한다.
6. adjudicator가 최종 판정과 이유를 남긴다.
7. 골든 자체의 오류도 defect로 기록하고 version을 올린다.

### 5.5 Synthetic data 사용 규칙

Synthetic question은 coverage 확대와 stress test에 유용하지만 core gold를 대체하지 않는다.

- 먼저 실제 query taxonomy를 만든 뒤 빈 셀만 보완한다.
- source passage에서 질문을 생성한 모델이 정답 판정까지 독점하지 않게 한다.
- 질문이 passage 문구를 그대로 복사해 retrieval을 쉽게 만들지 검사한다.
- 현실적 표현, answerability, 중복, leakage를 human review한다.
- synthetic과 real traffic 점수를 분리 보고한다.

### Gate 5

- schema, guideline, split, version, corpus hash가 고정됐다.
- high-risk와 unanswerable 케이스가 포함됐다.
- locked test는 tuning 경로와 분리됐다.
- 질문·답·근거를 사람이 다시 읽을 수 있다.

## Phase 6. Baseline 확립

### 목표

좋아 보이는 데모가 아니라 이후 모든 변경의 비교 기준을 만든다.

### Baseline 후보

1. No-RAG LLM 또는 현업의 현재 방식
2. BM25 lexical retrieval
3. 기본 dense retrieval
4. 단순 hybrid
5. 현재 운영 RAG

최소한 lexical baseline을 남긴다. 복잡한 candidate가 단순 baseline을 이기는지 확인할 수
있어야 한다.

### Baseline manifest

```yaml
run_id:
label: baseline-v1
suite_id:
suite_sha256:
case_order_sha256:
corpus_id:
corpus_sha256:
code_commit:
container_digest:
parser_version:
chunker_config:
embedding_model_id:
index_build_id:
retrieval_config:
reranker_model_id:
prompt_id:
llm_model_id:
judge_id:
temperature:
seeds:
started_at:
hardware:
```

### 반드시 저장할 trace

- 원 질문과 query rewrite
- 단계별 후보와 점수·순위
- ACL·metadata filter 전후
- rerank 전후
- 최종 context와 잘린 위치
- 실제 prompt와 system answer
- citation과 source coordinate
- 호출 수, tokens, TTFT, total latency, cost
- 예외, retry, timeout, fallback

### Gate 6

- 다른 담당자가 같은 manifest로 같은 판을 재생할 수 있다.
- 품질·비용·지연·오류 taxonomy별 기준선이 있다.
- baseline의 known limitation이 case ID와 함께 기록됐다.

## Phase 7. Experiment 운영

### 7.1 Experiment card

```yaml
experiment_id:
hypothesis:
observed_failure_cluster:
causal_component:
baseline_run:
candidate_change:
expected_primary_delta:
acceptable_guardrail_delta:
suite:
repetitions:
statistical_method:
decision_rule:
owner:
reviewer:
```

좋은 가설의 예:

> 상충 문서가 있는 temporal 질의에서 effective-date filter를 retrieval 이전에 적용하면
> Evidence Recall@10을 유지하면서 stale-evidence rate를 5%p 이상 낮춘다.

나쁜 가설의 예:

> RAG를 개선한다. 더 좋은 embedding과 prompt와 reranker를 적용한다.

### 7.2 실험 순서

1. 실패 케이스를 trace로 재생한다.
2. 최초 소실 단계가 corpus, parse, retrieval, rerank, context, generation 중 어디인지 정한다.
3. 변경할 knob 하나와 예상 trade-off를 쓴다.
4. baseline과 candidate를 같은 case에 paired 실행한다.
5. 확률적 단계는 trial을 반복하고 평균과 최악 trial을 본다.
6. 전체 평균과 사전 정의 segment를 함께 본다.
7. 개선, 회귀, 비용 변화와 신규 실패를 case ID로 읽는다.
8. 유지·재실험·폐기 결정을 ADR 또는 experiment report에 남긴다.

### 7.3 통계 원칙

- 질문별 `candidate - baseline` 차이를 기본 관측값으로 사용한다.
- 같은 사용자·문서·세션에서 파생된 질문은 cluster로 묶어 bootstrap한다.
- 평균 차이와 95% CI, absolute delta, relative delta를 함께 보고한다.
- 여러 candidate를 반복 비교하면 다중검정과 test overfitting을 관리한다.
- 유의성만 보지 말고 사전에 정한 MDE와 위험 guardrail을 적용한다.
- 표본 수는 고정 관행보다 pilot의 분산과 탐지하려는 최소 효과로 정한다.

### 7.4 LLM Judge 운영

LLM judge는 gold가 아니라 측정기다.

1. human calibration set에서 confusion matrix를 구한다.
2. 위치 swap, 모델명 blind, 답변 길이 차이를 시험한다.
3. judge model·prompt·temperature를 versioning한다.
4. 숫자·날짜·ID·citation은 가능한 한 결정론 검사와 병행한다.
5. 낮은 신뢰·고위험·judge 불일치는 human review queue로 보낸다.
6. candidate를 만든 동일 모델이 단독 judge가 되지 않게 한다.

### Gate 7

- suite SHA와 case 순서가 같다.
- candidate change와 예상 효과가 명확하다.
- component 개선이 E2E에서 재현된다.
- 회귀와 비용까지 포함한 결정이 기록됐다.

## Phase 8. Tuning Playbook

### 8.1 오류를 먼저 분류한다

| 오류군 | 대표 증상 | 먼저 볼 곳 |
|---|---|---|
| Source gap | 정답 자료가 corpus에 없음 | 수집·업무 범위 |
| Freshness | 폐기·구버전 근거 사용 | 유효시점·index 갱신 |
| Parse loss | 표·단서·문단이 사라짐 | parser·OCR·구조화 |
| Query understanding | 약어·주체·조건을 잘못 해석 | taxonomy·rewrite·router |
| Retrieval miss | gold evidence가 top-k에 없음 | lexical/dense/filter/chunk |
| Ranking error | evidence는 있으나 뒤에 있음 | reranker·hard negatives |
| Context pollution | 관련 없는/상충 근거 과다 | cutoff·dedup·diversity·budget |
| Context truncation | 예외·후반 조건이 잘림 | chunk/parent expansion/token budget |
| Grounding error | context와 다른 주장 생성 | prompt·claim verification·model |
| Reasoning error | evidence는 맞지만 결론이 틀림 | 구조화·tool·SFT 검토 |
| Abstention error | 자료가 없는데 답함 | answerability classifier·policy |
| Citation error | 답은 맞지만 근거 좌표가 틀림 | citation binding·output schema |
| ACL leakage | 권한 밖 문서가 검색됨 | identity propagation·pre-filter |
| Operational | timeout·retry·OOM·비용 폭증 | serving·queue·limits·observability |

### 8.2 튜닝 우선순위

다음 순서로 올라간다. 앞 단계의 defect를 뒤 단계 모델로 가리지 않는다.

1. 업무 범위와 answerability 정의
2. source coverage·freshness·ACL
3. parser/OCR/structure
4. chunk와 metadata
5. lexical/dense/hybrid retrieval
6. query routing/rewrite
7. reranking과 hard-negative 제어
8. context dedup·ordering·budget·citation binding
9. generation prompt·schema·abstention
10. 작은 분류기·embedding·reranker fine-tuning
11. generator SFT/선호 튜닝
12. 모델 교체 또는 구조 변경

### 8.3 Retrieval 튜닝

#### Chunking

- 문서 구조를 무시한 고정 길이를 유일한 전략으로 두지 않는다.
- heading, 조/항, 표, 절차 단위를 parent-child로 보존한다.
- embedding 단위와 답변에 보낼 단위를 분리할 수 있다.
- overlap 확대는 recall과 index/중복 비용을 함께 증가시킨다.
- chunk 변경 시 index build ID와 골든 qrels 좌표를 함께 versioning한다.

#### Hybrid

- 고유명사·코드·조문·수치는 lexical이 강할 수 있다.
- 패러프레이즈·자연어 질의는 dense가 기여할 수 있다.
- 단순 score 합산 전에 각 채널의 독립 기여와 중복을 측정한다.
- 채널이 실제 product flow에 연결되는지 trace에서 검증한다.

#### Metadata filter

- 법인, 국가, 제품, 문서종류, 시행일, 권한은 retrieval 이전 filter가 필요한지 검토한다.
- filter가 과도하면 recall이 사라지므로 unknown/missing metadata를 별도 측정한다.
- ACL은 post-filter만으로 처리하지 않는다. 권한 밖 문서의 존재 자체가 누출될 수 있다.

#### Reranking

- gold positive와 실제 retriever가 올린 hard negative로 dataset을 만든다.
- 쉬운 random negative만 사용하지 않는다.
- top-k 확대와 reranker 비용·p95를 함께 측정한다.
- single relevance뿐 아니라 필요한 evidence bundle coverage를 본다.

### 8.4 Context tuning

- 중복 문단과 parent-child 중복을 제거한다.
- 출처, 유효시점, 권한, 관련도와 문서 다양성을 함께 정렬한다.
- 관련 근거를 앞쪽에 두되 상충 근거를 숨기지 않는다.
- claim을 뒷받침할 최소 bundle과 최대 context budget을 별도 관리한다.
- 문서별·채널별 예산과 전체 예산을 구분한다.
- 잘림이 발생하면 어느 evidence가 잘렸는지 trace에 남긴다.

### 8.5 Prompt와 Generation tuning

- 모델에게 없는 근거를 추측하게 하지 않는다.
- answerability, citation, uncertainty, handoff schema를 명시한다.
- 답변 format보다 required claims와 forbidden claims를 우선 평가한다.
- 긴 general instruction을 모든 질문에 넣기보다 query class별 최소 policy를 사용한다.
- 같은 정보를 여러 LLM 단계가 연속 재해석하면 오류 증폭과 비용을 측정한다.
- output JSON schema를 쓰더라도 의미 정확성이 보장된다고 가정하지 않는다.

### 8.6 Fine-tuning 진입 조건

다음 조건을 충족하기 전에는 fine-tuning을 기본 해법으로 선택하지 않는다.

- 오류가 안정적인 taxonomy로 반복된다.
- source/parse/retrieval defect가 아님을 trace로 확인했다.
- 충분한 고품질 label과 독립 holdout이 있다.
- base model/prompt만으로 해결되지 않는 일관된 행동 목표가 있다.
- 고객 온프레미스에 학습·평가·model registry·rollback 경로가 있다.
- 개인정보·저작권·데이터 사용 근거가 확인됐다.

#### Embedding fine-tuning

```text
(query, positive passage, hard negative passages[])
```

- positive는 정확한 근거 좌표에서 만든다.
- hard negative는 같은 문서·주제지만 답을 지지하지 않는 문단을 포함한다.
- 문서·template leakage를 막도록 split한다.
- Recall@k뿐 아니라 domain별·query type별 일반화를 본다.

#### Reranker fine-tuning

```text
(query, candidate passages[], relevance grades[])
```

- 실제 first-stage retriever 후보 분포로 학습한다.
- graded relevance와 evidence bundle을 반영한다.
- 새 retriever로 바꾸면 후보 분포가 변하므로 재검증한다.

#### Generator SFT

```text
(policy, query, authorized context, grounded answer, citations, action)
```

- context 없이 정답을 외우게 하는 dataset을 피한다.
- 답변뿐 아니라 abstain·clarify·handoff 사례를 포함한다.
- citation 좌표와 required claims를 검증한다.
- memorization을 막기 위해 문서·업무 사건 단위 holdout을 둔다.

#### Judge fine-tuning

- 충분한 human disagreement와 adjudicated label이 있을 때만 고려한다.
- candidate 모델과 독립된 calibration/holdout을 둔다.
- judge accuracy 자체에 CI와 segment 분석을 적용한다.

### Gate 8

- 변경이 목표 오류군에서 효과를 보인다.
- locked test와 고위험 segment가 비열등하다.
- 비용·latency·운영 복잡성 증가가 정당화된다.
- 학습 dataset과 model artifact의 lineage가 존재한다.

## Phase 9. On-prem Experiment·RAGOps Architecture

### 9.1 논리 구성

```text
[사용자/업무 시스템]
        │ identity, query, feedback
        ▼
[API Gateway / AuthN-Z / Rate Limit]
        ▼
[RAG Application & Orchestrator]
   ├─ Query router / policy
   ├─ Retrieval / reranker / context builder
   ├─ LLM & embedding serving clients
   └─ Citation / abstention / output guard
        │
        ├──────────────► [Lexical / Vector / Metadata Index]
        ├──────────────► [LLM / Embedding / Reranker Serving]
        └──────────────► [Trace / Metrics / Audit]

[Source connectors]
        ▼
[Raw immutable store] → [Parse/Normalize] → [Canonical corpus]
        → [Chunk/Enrich] → [Index build] → [Index registry/promotion]

[Golden registry] → [Experiment runner] → [Evaluation/statistics]
        → [Decision report] → [Release gate]

[Git + Container registry + Model registry + Artifact store]
        → dev → test → staging → production
```

### 9.2 필수 플랫폼 구성요소

| 영역 | 구성요소 | 운영 계약 |
|---|---|---|
| Source | connector, batch/CDC, raw store | 원문 불변, checksum, 재수집 가능 |
| Processing | parser/OCR/chunker/enrichment workers | versioned image, retry, DLQ, lineage |
| Corpus | canonical document/chunk metadata store | ACL·시점·source 좌표 보존 |
| Index | lexical/vector/graph index | atomic build, alias promotion, rollback |
| Models | LLM/embedding/reranker serving | model digest, concurrency, quota, health |
| Application | RAG API/orchestrator | stateless 우선, config 외부화, trace ID |
| Evaluation | golden registry/runner/judge/stats | production과 동일 artifact 사용 |
| Registry | Git/container/model/index/prompt | immutable version, 승인 promotion |
| Observability | logs/metrics/traces/audit | query-level 연계, PII masking, retention |
| Security | IAM/secrets/KMS/network policy | least privilege, rotation, egress control |
| Operations | scheduler/queue/backup/DR | 재시도, snapshot, RPO/RTO, runbook |

### 9.3 환경 분리

| 환경 | 데이터 | 목적 | 금지 |
|---|---|---|---|
| Dev | 비식별/부분 표본 | 빠른 분석·개발 | production secrets·전체 민감 데이터 |
| Eval/Test | versioned corpus + locked set | 재현 실험 | 임의 수동 config 변경 |
| Staging | production-like | 보안·부하·canary rehearsal | 승인 없는 외부 모델 호출 |
| Production | 승인 corpus | 사용자 서비스 | dev artifact 직접 반영 |

완전 분리가 어렵다면 최소한 namespace, credentials, storage path, index alias,
audit trail을 분리한다.

### 9.4 Artifact promotion 단위

RAG release는 코드 한 개가 아니라 다음 bundle이다.

```yaml
release_bundle:
  code_commit:
  container_digest:
  config_fingerprint:
  prompt_bundle_id:
  parser_image:
  corpus_snapshot:
  index_build_ids:
  embedding_model_digest:
  reranker_model_digest:
  llm_model_id:
  golden_suite_id:
  evaluation_report_id:
  migration_plan:
  rollback_bundle:
```

### 9.5 Index build와 promotion

1. 새 corpus snapshot을 읽어 새 index build ID를 만든다.
2. production index에 in-place로 덮어쓰지 않는다.
3. completeness, document count, ACL, vector dimension, smoke query를 검사한다.
4. eval에서 application candidate와 함께 검증한다.
5. 승인 후 alias를 새 index로 원자적으로 전환한다.
6. 직전 index는 rollback 기간 동안 보존한다.

### 9.6 Target 환경 재색인 원칙

망 밖에서 만든 vector를 무조건 반입하지 않는다. index embedding과 query embedding은
정확히 같은 model artifact와 preprocessing을 사용해야 한다. target 온프레미스의
승인된 embedding serving을 사용한다면 target에서 index를 다시 만드는 것이 기본이다.

### 9.7 망분리 운반

모든 package는 다음을 포함한다.

- package manifest와 생성 도구 version
- 개별 파일 sha256, 전체 package sha256
- source environment와 destination
- schema/version compatibility
- 민감도와 승인번호
- dry-run 목록
- 적용 report와 실패 시 복구 방법

대용량 상태는 snapshot으로 반출하고, 작은 변경·피드백은 outbox로 누적하여 재생할 수
있게 한다. 파일을 적용한 결과도 report artifact로 남긴다.

### 9.8 보안 체크

- 사용자 identity와 ACL filter가 retrieval 전부터 전달되는가?
- prompt/log/trace에 원문과 개인정보가 얼마나 남는가?
- 관리자와 annotator가 볼 수 있는 데이터가 분리되는가?
- model endpoint에 보낸 payload가 외부에 저장되는가?
- secret이 Git, image, command line, notebook output에 남지 않는가?
- model/container/package의 SBOM과 취약점 검사가 가능한가?
- 승인되지 않은 egress가 차단되는가?
- 삭제·보존 정책이 raw, index, trace, backup에 일관되게 적용되는가?
- prompt injection 문서가 tool 또는 data access를 확대할 수 없는가?

### 9.9 Observability 최소 규격

각 요청을 하나의 trace ID로 연결한다.

```text
request
  → identity/policy
  → query parse/rewrite
  → retrieval channel candidates
  → filters/rerank
  → selected context/token budget
  → model calls/retries
  → answer/claims/citations/action
  → user feedback/human correction
```

운영 dashboard에는 최소한 다음을 둔다.

- request volume, success/error/timeout
- p50/p95/p99 end-to-end와 단계별 latency
- model call/token/GPU/queue usage
- retrieval empty rate와 context size
- answer/abstain/handoff 비율
- citation/unsupported claim 표본감사
- corpus/index freshness와 build health
- query·failure taxonomy drift
- high-risk incident와 rollback 상태

### Gate 9

- target 환경에서 corpus rebuild부터 평가까지 재생된다.
- artifact bundle과 rollback bundle이 존재한다.
- observability와 audit이 case ID까지 연결된다.
- 보안·백업·DR·SLO Owner가 지정됐다.

## Phase 10. Release와 Production 전환

### 10.1 Release gate

| Gate | 질문 |
|---|---|
| Quality | Primary metric이 MDE와 CI 조건을 통과했는가? |
| Risk | 고위험 segment, unanswerable, ACL이 회귀하지 않았는가? |
| Data | corpus/index freshness와 completeness가 기준을 통과했는가? |
| Performance | 목표 동시성과 p95/p99를 만족하는가? |
| Reliability | timeout, retry storm, dependency failure가 통제되는가? |
| Security | 위협모델·취약점·권한·로그 검토가 승인됐는가? |
| Operability | dashboard, alert, on-call, rollback이 준비됐는가? |
| Evidence | release bundle과 decision report가 immutable하게 보존됐는가? |

### 10.2 Canary 순서

1. ping/version/config fingerprint
2. dependency와 model/index health
3. 고정 smoke retrieval
4. 고정 smoke answer와 citation
5. 내부 사용자 shadow
6. 제한된 사용자·업무 canary
7. 지표·incident review
8. 점진 확대 또는 rollback

### 10.3 Rollback

코드만 되돌리면 안 될 수 있다. 다음 호환성을 확인한다.

- code ↔ config
- code ↔ corpus schema
- code ↔ index build
- application ↔ model version
- prompt ↔ output parser
- evaluation ↔ release bundle

rollback은 직전 code, config, prompt, index alias, model ID를 한 번에 되돌릴 수 있어야 한다.

## Phase 11. 운영 학습 루프

### 11.1 Feedback를 label로 바꾸는 과정

```text
사용자 feedback/수정/incident
  → 자동 PII 제거·중복 묶기
  → query/failure taxonomy 분류
  → 영향도 × 빈도 × 위험도 우선순위
  → SME annotation/adjudication
  → rolling shadow
  → 다음 golden version 후보
  → 실험 backlog
```

단순 thumbs up/down만으로 학습하지 않는다. 가능하면 다음을 수집한다.

- 무엇이 틀렸는지: 근거, 결론, 누락, 표현, 최신성, 권한
- 사용자가 선택한 올바른 문서
- 수정한 claim과 삭제한 claim
- 답변하지 말았어야 하는지
- 실제 업무 결과와 human 승인 여부

### 11.2 Drift

- Query drift: 새로운 표현·업무·사용자군
- Corpus drift: 문서 개정·폐기·추가
- Label drift: 정책·업무 판단 기준 변경
- Model drift: serving model 교체·양자화·runtime 변화
- System drift: parser, chunker, index, prompt 변경

각 drift에 감지 지표, Owner, 재평가 조건을 둔다.

### 11.3 운영 주기

| 주기 | 활동 |
|---|---|
| 매일 | 장애·고위험 답변·index freshness 확인 |
| 매주 | 실패 cluster triage, 신규 golden 후보, 비용·지연 review |
| 격주/월간 | candidate 실험과 locked release review |
| 분기 | taxonomy·rubric·보안·DR·capacity 재검토 |
| 주요 문서/모델 변경 시 | 전체 regression과 judge calibration |

## Phase 12. Knowledge Transfer와 철수

### Handover pack

- 업무·평가·운영 charter
- Architecture와 data flow
- Source inventory와 lineage
- Golden schema, guideline, current versions
- Metric dictionary와 통계 protocol
- Experiment registry와 주요 ADR
- Build/deploy/canary/rollback runbook
- Security, secrets, backup, DR runbook
- Dashboard와 alert catalog
- Known limitations와 risk acceptance
- 90일 backlog와 ownership

### 고객 단독 졸업시험

고객 담당자가 FDE 관찰하에 다음을 수행한다.

1. 신규 문서 version을 반입한다.
2. lineage와 parser QA를 확인한다.
3. 새 index를 만들고 smoke test한다.
4. 신규 실패 사례를 골든 schema로 라벨한다.
5. baseline과 candidate를 paired 실행한다.
6. report를 읽고 release/reject 결정을 작성한다.
7. staging에 배포하고 canary를 실행한다.
8. 의도적으로 직전 version으로 rollback한다.

두 번 연속 성공하면 FDE는 Owner가 아니라 advisor로 전환한다.

## 4. FDE 현장 운영 방식

### 4.1 첫 10영업일 권장 계획

| 일자 | FDE 활동 | 고객 공동 활동 | 산출물 |
|---|---|---|---|
| D1 | Sponsor·Owner alignment | 성공/실패 정의 | Opportunity brief |
| D2 | 업무 shadowing | 실제 사례 재생 | As-is map |
| D3 | source·권한 조사 | Data owner 인터뷰 | Source inventory |
| D4 | on-prem connectivity test | Platform·Security | Site survey |
| D5 | query·failure taxonomy | SME workshop | Taxonomy v0 |
| D6 | golden schema·guideline | SME calibration | Golden pilot |
| D7 | corpus sample ingest | Data/Platform | Lineage pilot |
| D8 | baseline runner 연결 | QA/Eval | Baseline smoke |
| D9 | trace 기반 오류 분석 | 전체 workshop | Error backlog |
| D10 | 6~12주 계획·Gate 확정 | Steering review | Delivery charter |

### 4.2 주간 리듬

- 월요일: 이전 주 failure cluster와 이번 주 가설 1~3개 확정
- 화~수요일: 데이터 수정·실험 구현·paired run
- 목요일: SME case review와 guardrail 분석
- 금요일: decision review, ADR, 다음 golden 후보와 platform blocker 정리

### 4.3 회의보다 artifact

각 회의는 다음 중 하나를 업데이트해야 한다.

- charter
- source/data card
- golden guideline/case
- experiment card/manifest
- decision ADR
- release/operation runbook

업데이트할 artifact가 없는 회의는 목적을 재검토한다.

## 5. 재사용 템플릿

### 5.1 Data readiness scorecard

| 항목 | Red | Yellow | Green |
|---|---|---|---|
| Coverage | 핵심 source 부재 | 일부 업무/기간 누락 | 목표 population 충족 |
| Freshness | 최신판 판별 불가 | 수동 갱신 | 유효시점·증분 갱신 자동 |
| Parsing | 표/본문 대량 손실 | 일부 유형 취약 | 유형별 QA 통과 |
| ACL | 문서권한 미연결 | 부분 metadata | retrieval 전 강제 |
| Lineage | 원문 추적 불가 | 일부 단계 기록 | answer→source 재현 |
| Owner | 불명확 | 조직만 지정 | named owner+SLA |

### 5.2 Experiment decision template

```markdown
# EXP-XXXX: 제목

## 관측 실패
- case IDs:
- 최초 소실 단계:

## 가설

## 변경
- 유일한 config/code 차이:

## 실험 계약
- suite/hash:
- corpus/index:
- baseline/candidate:
- trials:
- primary/MDE/guardrails:

## 결과
- 전체:
- segment:
- worst trial:
- latency/cost:
- 신규 회귀 case:

## 결정
- adopt / repeat / reject
- 이유:
- 후속:
```

### 5.3 Release evidence index

```yaml
release_id:
business_approval:
security_approval:
quality_report:
load_test_report:
artifact_bundle:
corpus_snapshot:
index_build:
model_ids:
known_risks:
rollback_test:
canary_owner:
on_call:
```

## 6. 대표 Anti-pattern과 FDE 대응

| Anti-pattern | 위험 | FDE 대응 |
|---|---|---|
| “일단 챗봇부터” | 업무와 평가 기준 부재 | 실제 job과 KPI를 charter로 고정 |
| 데모 질문만 반복 | 과적합·대표성 없음 | traffic/risk 층화와 locked set 생성 |
| LLM이 질문·정답·채점 모두 생성 | 상관된 오류 | human core와 독립 calibration |
| Retrieval 점수만 보고 출시 | 최종 추론·citation 오류 | 제품 E2E gate 유지 |
| Prompt와 모델과 chunk를 동시에 변경 | 원인 불명 | 탐색 후 한 변수 확인 실험 |
| 모든 문서를 vectorDB에 넣음 | ACL·버전·중복 오염 | corpus contract와 metadata gate |
| 큰 context가 안전하다고 가정 | 잡음·잘림·비용 | evidence bundle과 예산 A/B |
| 외부에서 만든 vector를 온프레미스 반입 | embedding 불일치 | target model로 재색인 |
| Git commit만 기록 | 실행 재현 불가 | release/experiment bundle 도입 |
| fine-tuning을 첫 처방으로 선택 | 데이터 결함 은폐 | tuning ladder와 진입 조건 적용 |
| FDE만 운영 가능 | AX 지속성 실패 | 고객 공동 Owner와 졸업시험 |
| 평균만 보고 출시 | 고위험 tail 회귀 | risk segment와 worst trial gate |

## 7. 성숙도 모델

| Level | 상태 | 다음 단계 조건 |
|---|---|---|
| L0 Demo | 선택 예시에서 답변 생성 | 실제 업무·Owner·KPI 확보 |
| L1 Measured | Golden과 baseline 존재 | lineage·trace·paired runner 구축 |
| L2 Repeatable | 실험 재현과 component/E2E 진단 가능 | locked test·release gate·artifact registry |
| L3 Deployable | 온프레미스 배포·canary·rollback 가능 | 운영 feedback·drift·golden vNext |
| L4 Operated | SLO와 정기 개선 루프 작동 | 고객 단독 운영·튜닝 |
| L5 Transformed | 업무 프로세스·조직 KPI가 지속 개선 | 지속적 portfolio 확장 |

## 8. 권장 프로젝트 일정

고객 준비도에 따라 달라지며, 아래는 12~16주 기준의 예시다.

| 기간 | 중심 작업 | Exit |
|---|---|---|
| 1~2주 | discovery, charter, site survey | Gate 0~3 |
| 3~5주 | corpus, lineage, parser QA | Gate 4 |
| 4~6주 | golden pilot→v1, baseline | Gate 5~6 |
| 6~10주 | 오류 cluster와 실험·튜닝 | Gate 7~8 |
| 8~12주 | on-prem RAGOps와 보안·부하 | Gate 9 |
| 11~14주 | staging, canary, production | Gate 10 |
| 13~16주 | 운영 루프, 교육, 고객 dry-run | Gate 11~12 |

데이터 승인과 인프라 lead time은 기술 개발과 별도 critical path로 관리한다.

## 9. 이 저장소에 적용하는 기준

현재 8-AGENT 저장소는 이 매뉴얼의 여러 구성요소를 이미 갖고 있다. 범용 매뉴얼과
프로젝트 구현의 연결은 다음과 같다.

| 표준 요소 | 현재 구현·문서 | 적용 포인트 |
|---|---|---|
| Data lineage | `docs/LINEAGE.md` | body sha256으로 수집→구조화 계보 연결 |
| RAG 성능 계약 | `docs/RAG_FLOW.md` | top-k·문턱·예산과 config fingerprint 관리 |
| 한 변수 A/B | `docs/RAG_OCCAM.md` | 동일 suite/case와 product E2E 비교 |
| 실제 업무 골든 | `data/review/cm_core_e2e_v1.json` | 실제 질의·답변·기대 조문·slice 보존 |
| Experiment runner | `scripts/ask_e2e_golden.py` 등 | raw→manifest→compare 흐름 |
| Portfolio gate | `scripts/rag_e2e_portfolio.py` | 서로 다른 제품 흐름의 준비·품질 분리 |
| On-prem deploy | `docs/GENOS_DEPLOY.md` | 코드·환경·모델·볼륨·canary·rollback |
| 망분리 transport | `docs/OPS_TRANSPORT.md` | package verify, snapshot, outbox, replay |
| 실험 ADR | `docs/adr/` | 가설·관측·채택/기각의 영속 기록 |

### 현재 구현에서 일반 표준으로 승격할 좋은 관행

1. suite SHA와 case 순서가 다르면 A/B를 무효화한다.
2. 실행 당시 설정 snapshot을 raw 결과에 직접 남긴다.
3. 부품검사를 전체 RAG 통과로 보고하지 않는다.
4. 실제 product wiring에 닿지 않는 switch 실험을 무효로 판정한다.
5. 평균뿐 아니라 worst trial, p50/p95, 과잉 근거를 함께 본다.
6. target 환경에서 동일 embedding model로 index를 다시 만든다.
7. 코드와 정본 데이터를 다른 운반·승인 경로로 관리한다.
8. 데이터 계보는 중복 원장이 아니라 각 단계 ground truth의 파생 view로 만든다.

### 다음 구현 우선순위

1. 이 문서의 charter, golden case, experiment card를 machine-readable schema로 만든다.
2. `var/eval` 실행물을 experiment registry에서 검색할 수 있게 한다.
3. corpus/index/model/prompt/judge를 하나의 release bundle로 묶는다.
4. locked test 접근과 결과 열람 권한을 분리한다.
5. production failure를 rolling shadow 후보로 만드는 triage queue를 추가한다.
6. GenOS target에서 `ingest → index build → eval → promote`를 하나의 승인 pipeline으로 만든다.
7. 고객 운영자가 실행하는 졸업시험 runbook을 실제 명령과 화면 기준으로 작성한다.

## 10. 연구 기반과 추가 읽을거리

이 매뉴얼은 전통적인 IR test collection, 통계적 비교, 최신 RAG 평가 방법을 함께
사용한다. 각 문헌은 다음 부분에 직접 대응한다.

| 문헌 | 매뉴얼 적용 포인트 |
|---|---|
| [TREC 평가 방법](https://trec.nist.gov/howto.html) | qrels, pooling, 공유 test collection |
| [Voorhees & Buckley, Topic Set Size](https://www.nist.gov/publications/effect-topic-set-size-retrieval-experiment-error) | 적은 질문에서 결론이 뒤집히는 위험과 표본 설계 |
| [Smucker et al., Statistical Significance Tests](https://doi.org/10.1145/1321440.1321528) | paired test, bootstrap, randomization 비교 |
| [KILT](https://aclanthology.org/2021.naacl-main.200/) | corpus snapshot과 provenance를 포함한 평가 |
| [BEIR](https://openreview.net/forum?id=wCu6T5xFjeJ) | 이질적 도메인에서 retriever 일반화 평가 |
| [RAGAS](https://aclanthology.org/2024.eacl-demo.16/) | 빠른 reference-free RAG 평가와 그 사용 경계 |
| [ARES](https://aclanthology.org/2024.naacl-long.20/) | 소량 human label로 자동평가 보정과 신뢰구간 구성 |
| [RAGChecker](https://proceedings.neurips.cc/paper_files/paper/2024/hash/27245589131d17368cccdfa990cbf16e-Abstract-Datasets_and_Benchmarks_Track.html) | claim 단위 retrieval/generation 진단 |
| [BERGEN](https://aclanthology.org/2024.findings-emnlp.449/) | 재현 가능한 RAG component benchmarking |
| [RAGTruth](https://aclanthology.org/2024.acl-long.585/) | RAG hallucination의 세밀한 human annotation |
| [CRAG](https://arxiv.org/abs/2406.04744) | 실제성, 시간 변화, long-tail 질문 benchmark |
| [Lost in the Middle](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00638/119630/) | context 길이와 evidence 위치 robustness |
| [UAEval4RAG](https://aclanthology.org/2025.acl-long.415/) | unanswerable query와 적절한 거절 평가 |

문헌의 metric을 그대로 복사하기보다 고객 업무의 population, 오류 비용, corpus 구조에
맞춰 평가 계약을 다시 작성한다.

## 11. 최종 Checklist

### 업무

- [ ] named Product Owner와 Domain Owner가 있다.
- [ ] 현재 업무 baseline과 목표 MDE가 있다.
- [ ] in/out of scope와 human approval 지점이 정의됐다.

### 데이터

- [ ] source·version·ACL·freshness Owner가 있다.
- [ ] answer에서 원문까지 lineage가 연결된다.
- [ ] parser QA와 corpus coverage 수치가 있다.
- [ ] target embedding으로 index가 만들어졌다.

### 평가

- [ ] dev/locked/challenge/rolling shadow가 분리됐다.
- [ ] answerable/unanswerable/high-risk가 포함됐다.
- [ ] required claims와 evidence 좌표가 있다.
- [ ] LLM judge가 human gold에 calibration됐다.

### 실험

- [ ] baseline과 candidate가 동일 suite·corpus에서 paired 실행된다.
- [ ] code/config/model/index/prompt/judge manifest가 남는다.
- [ ] CI, MDE, guardrail, worst trial을 본다.
- [ ] 결과와 결정이 case ID·ADR로 남는다.

### 온프레미스

- [ ] 내부 Git/package/container/model registry가 준비됐다.
- [ ] secrets, network, ACL, audit, retention이 승인됐다.
- [ ] rebuild, deploy, canary, rollback이 재생된다.
- [ ] snapshot/outbox/transport가 checksum으로 검증된다.
- [ ] dashboard, alert, on-call, backup, DR이 있다.

### 조직 전환

- [ ] 고객 담당자가 신규 golden을 스스로 추가할 수 있다.
- [ ] 고객 담당자가 baseline/candidate를 스스로 비교할 수 있다.
- [ ] 고객 담당자가 배포와 rollback을 두 번 연속 성공했다.
- [ ] FDE 철수 후 90일 운영·실험 backlog와 Owner가 있다.

---

이 매뉴얼의 최종 목적은 좋은 RAG 한 개를 납품하는 것이 아니다. 고객 조직 안에
`업무 실패 → 데이터·골든화 → 재현 실험 → 안전한 튜닝 → 온프레미스 배포 → 운영 피드백`
이라는 개선 시스템을 남기는 것이다. 그 시스템이 FDE 없이 계속 돌 때 AX가 완료된다.
