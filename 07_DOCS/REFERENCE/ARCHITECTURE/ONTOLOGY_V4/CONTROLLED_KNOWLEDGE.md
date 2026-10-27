# 지식 축적·승인·스키마 확장

[v4 목차](../ONTOLOGY_V4.md) · [구축 순서](BUILD_PLAN.md) · [판단 전달과 정정](JUDGMENT_AND_CORRECTION.md) · [멀티턴](MULTITURN_LEGAL_AGENT.md)

2026-10-24 사용자 결정으로 재작성했다. 에이전트가 실제 질문을 조사하며 남긴 판단을 모아, LLM이 개념 단위의 온톨로지 작업 단위와 스키마를 JSON으로 제안한다. 사람이 승인·수정하고, 골드 테이블에 SQL로 적재된 것만 온톨로지로 사용한다. 이 문서는 설계이며 아래 화면·명령·저장 구조는 아직 구현하지 않았다.

## 저장 위치

**2026-10-27 개발계 정정:** 사용자 지정 실버는 `SIDDS.*_S`, 에이전트는 `SIDDA.*_A`다. 원문·구조화·검색·게시 데이터는 개발계 GENOS가 직접 조회할 수 있는 실버에 두고, 온톨로지·숏컷·에이전트 기록은 SIDDA에 둔다. 아래 골드 표와 골드 매핑 설명은 운영 설계 이력이며 개발계에는 이 물리 배치 정정을 우선한다. S3 작업 JSON, 사람의 검토·승인, 실제 SQL 적재 후 사용이라는 절차는 유지한다. SIDDA 데이터의 소비자 접근은 별도 연결 확인이 필요하며 저장 위치 지정만으로 GENOS에서 사용할 수 있다고 보지 않는다. [개발계 전달본과 구현 경계](../../../../08_DEPLOYMENT/DATAIKU/pipeline_layers_20261027_r1/GUIDE.txt).

| 저장소 | 담는 것 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| **에이전트 레이어** (Dataiku Oracle) | 사용자 로그(세션·턴·질문·답), LLM 판단 기록(연결 판단·읽기 판단), 사용자 재지시·정정, 대화 중 용어 관찰, 착지 기록 원료, 사용자에게 보여준 판단 그래프 | RAG 서비스(GENOS 백엔드) | 멀티턴 분류, 개념 묶음 작업 |
| **온톨로지 작업 폴더** (Dataiku S3 관리 폴더) | 온톨로지 작업 단위 JSON 전부: 개념 묶음, LLM 제안 스키마, 승인 상태, 시뮬레이션 결과, 골드 매핑, 적재 SQL과 적재 기록 | 개념 묶음 작업, Streamlit | Streamlit, 시뮬레이션, 적재 SQL 생성 |
| **골드 레이어** (Dataiku Oracle) | 원문, SQL로 적재된 온톨로지, 승인된 용어·별칭, 착지 예시(공개 사례 + 승인된 대화 기록) | 사람이 실행하는 적재 SQL | RAG 서비스 |

로컬 대응:

| GENOS | 로컬 |
|---|---|
| 에이전트 레이어 | 기존 사건 기록 SQLite([case_repository.py](../../../../02_BACKEND/semantic_runtime/legal_agent/case_repository.py)) |
| S3 관리 폴더 | `01_DATA/ONTOLOGY_WORK/` (논리 root `data`) |
| 골드 레이어 | 로컬 SQLite 골드 파일. 표는 매핑 화면에 등록한 표 정의대로 `pipeline.py ontology-work load-local`이 만든다(현장의 신청·생성을 대신) |

S3 관리 폴더는 기존 Dataiku 코드와 같은 방식으로 연다: `dataiku.Folder("LEGAL_ONTOLOGY_WORK", project_key="LEGAL_RAG")`(S3 연결), 읽기는 `get_download_stream`, 쓰기는 `upload_stream`. `get_path()`는 쓰지 않는다. GENOS 서빙은 이 폴더를 읽지 않는다. 서빙은 골드만 Oracle로 조회한다.

## 한눈에 보기

~~~mermaid
flowchart TD
    A["질문 조사 → 에이전트 레이어에 판단 기록"] --> B["판단 모음"]
    R["사용자 재지시·정정 (에이전트 레이어)"] --> B
    B --> C["LLM: 개념 묶음 + 필요하면 새 스키마 제안"]
    C --> J["S3에 JSON 저장"]
    J --> D["Streamlit: 사람이 승인·수정·쪼개기·합치기·반려"]
    D --> U["시뮬레이션"]
    U --> M["매핑 화면: JSON 필드 ↔ 골드 표·컬럼"]
    M --> Q["적재 SQL 생성 → 사람이 실행"]
    Q --> G["골드 레이어"]
    G --> F["다음 질문에서 회수·사용"]
~~~

## 판단 모음에서 온톨로지까지

### "모은다"는 무엇인가

판단 기록은 온톨로지를 만드는 **재료**다. 기록 원본은 에이전트 레이어에 이력으로 남는다. 개념 묶음 작업이 그 기록을 읽어 개념 단위로 재구성하고, S3에 JSON으로 저장한다. 사람이 승인하고 골드에 적재된 것만 온톨로지가 된다.

| 구분 | 무엇 | 어디 | 온톨로지인가 |
|---|---|---|---|
| 판단 기록 | 한 질문에서 내린 결정 하나와 사유 | 에이전트 레이어 | 아님 (재료·이력) |
| 개념 묶음 JSON | 같은 개념에 대한 여러 판단을 정리한 것 | S3 | 아님 (작업 중) |
| 승인된 개념 묶음 JSON | 사람이 승인·수정한 것 | S3 | 아님 (적재 대기) |
| 골드 적재분 | 적재 SQL로 골드 표에 들어간 것 | 골드 | 맞음 |

### 모으는 판단

| 종류 | 담는 내용 | 예 |
|---|---|---|
| 연결 판단 | 출발 조항, 대상 조항(확인/미확인), 연결 타입(14종), 따라감/안 감/보류, 사유 | 제97조 제1항 제2호 → 시행령(위임, 대상 미확인), 보류 |
| 읽기 판단 | 읽은 조항, 핵심/보조/조건부/보류/안 씀, 확인한 내용, 사유 | 제97조 — 핵심, "필요경비 세 범주를 정함" |
| 사용자 재지시 | 어떤 판단을 무엇으로 바꾸라고 했는지, 그 뒤 결과 | "시행령 163조 읽어" → 읽음 → 답에 사용 |
| 사용자 정정 | 잘못된 대상·값·연결과 바른 대상 | "200만 원짜리 말고 100만 원 규정" (재지시 "빼" + "읽어"로 기록) |
| 용어 관찰 | 사용자 표현, 대상 법률 용어, 근거 발화·찾은 조문, 적용 범위 | "스톡옵션은 주식매수선택권 말하는 거야" → 용어 후보([용어집](LANDING.md#용어집--별도-도구)) |

질문 원문은 각 판단의 **발견 이력**으로만 연결한다. 지식은 질문이 아니라 조항(원문)에 붙는다. 그래서 다른 질문이 같은 조항에 도달해도 같은 지식을 쓴다.

### "개념 단위"는 무엇인가

개념은 온톨로지의 개념 노드다. 우리 저장소에서는 용어집의 개념과 같은 단위다. 예: "자본적지출액", "양도비", "의무보유 한도".

판단 기록은 조항마다 낱개로 흩어져 있다. 같은 개념을 다룬 판단을 질문과 관계없이 모은 것이 **개념 묶음**이다. 사람은 판단 수백 건을 하나씩 보지 않고 개념 묶음 단위로 승인한다.

묶는 규칙:
1. 판단이 가리키는 조항에 이미 용어집 개념이 연결돼 있으면 그 개념에 붙인다.
2. 없으면 LLM이 판단 내용과 원문을 보고 개념 이름을 제안하고 `NEW_CONCEPT_CANDIDATE`로 표시한다.
3. 같은 이름이라도 정의 조문이나 적용 범위가 다르면 다른 개념으로 둔다. 자동으로 합치지 않는다.
4. 한 판단은 여러 묶음에 들어갈 수 있다(예: 한 조항이 두 개념을 정의). 판단 ID로 중복을 추적한다.

### 개념 묶음 JSON

아래는 구조 예시다. 실제 판단 기록에서 만든 것이 아니다.

~~~json
{
  "schema_version": "ontology-bundle-v0",
  "bundle_id": "cb-0001",
  "revision": 1,
  "status": "CANDIDATE",
  "concept": {"label": "자본적지출액", "glossary_ref": null, "kind": "NEW_CONCEPT_CANDIDATE"},
  "provisions": [
    {"anchor": {"document_id": "...", "version": "...", "unit_id": "...", "content_sha256": "...", "label": "소득세법 제97조 제1항 제2호"},
     "role": "SCOPE", "value": null, "note": "필요경비 범주로 정하고 세부는 대통령령에 위임"},
    {"anchor": {"document_id": "...", "version": "...", "unit_id": "...", "content_sha256": "...", "label": "소득세법 시행령 제163조 제3항"},
     "role": "SCOPE", "value": null, "note": "위임받은 세부 항목"}
  ],
  "relations": [
    {"from": "소득세법 제97조 제1항 제2호", "type": "DELEGATES_TO", "to": "소득세법 시행령 제163조 제3항", "target_status": "CONFIRMED"}
  ],
  "review_notes": ["세부 항목을 읽을 때 제3항 본문의 공통 조건도 함께 읽는다"],
  "evidence_judgments": [
    {"judgment_id": "...", "session_id": "...", "turn": 1, "kind": "연결 판단", "decision": "보류", "reason": "..."},
    {"judgment_id": "...", "session_id": "...", "turn": 2, "kind": "사용자 재지시", "instruction": "시행령 163조 읽어", "result": "읽음, 답에 사용"}
  ],
  "proposed_by": {"model": "...", "run_id": "...", "at": "..."},
  "history": []
}
~~~

`anchor`의 문서·판본·단위 ID·원문 해시는 서버가 판단 기록에서 그대로 옮긴다. LLM이 만들지 않는다. `evidence_judgments`의 원문 본문은 복사하지 않고 판단 ID로 에이전트 레이어를 가리킨다.

### 개념 묶음 작업

| 항목 | 규칙 |
|---|---|
| 실행 | 사람이 실행한다. 로컬은 `pipeline.py ontology-work bundle`, GENOS는 같은 모듈을 Dataiku 노트북/레시피에서 실행. 자동 주기 실행은 하지 않는다 |
| 입력 | 에이전트 레이어에서 지난 실행 이후의 판단 기록(연결 판단·읽기 판단·재지시·정정). 처리 위치는 S3 `ontology/state/bundling_watermark.json`(마지막 처리 판단 기록 시각·ID) |
| 묶기 | 판단 기록을 조항 anchor로 모은 뒤, 용어집 개념이 있으면 그 개념으로, 없으면 LLM이 개념을 제안 |
| LLM 입력 | 한 호출에 anchor 최대 20개. anchor마다 판단 기록 요약(판단·사유·재지시)과 원문 앞부분 1,500자. 출력은 `ontology-bundle-v0`·`ontology-schema-proposal-v0` JSON |
| LLM 출력 검사 | JSON 구문·스키마 → 연결 타입·역할 값 → anchor·판단 ID가 입력에 있었던 것인지. 실패하면 같은 입력과 오류로 1회만 다시 요청. 그래도 실패하면 그 anchor들은 처리하지 않은 채로 두고(워터마크를 넘기지 않음) 실패 기록을 남긴다 |
| 모델 | 로컬은 현행 외부 실험 모델 정책(Qwen3.8). GENOS는 Dataiku에서 GENOS 내부 LLM을 호출한다(호출 가능, 2026-10-24 사용자 확인) |
| 예산 | 한 실행에 LLM 호출 최대 50회. 넘으면 그 지점에서 멈추고 워터마크를 처리한 곳까지만 넘긴다. 20개·1,500자·50회는 초기값이며 단계 4 첫 실행 결과로 조정한다 |
| 묶음 ID | `cb-` + sha256(개념 이름(NFC, 앞뒤 공백 제거, 연속 공백 1칸) + 처음 묶인 anchor unit_id들의 정렬 목록)의 앞 12자리. 다시 실행해도 같은 개념은 같은 ID |
| 기존 묶음이 있을 때 | 새 판단이 생긴 묶음만 새 revision을 `CANDIDATE`로 만든다. 승인·적재된 이전 revision은 그대로 두고, 새 revision이 다시 승인·적재될 때까지 골드에는 이전 revision이 남는다 |

### 상태

| 상태 | 뜻 | 바꾸는 쪽 |
|---|---|---|
| `CANDIDATE` | LLM이 제안 | 개념 묶음 작업 |
| `APPROVED` | 사람이 승인(수정 포함) | Streamlit |
| `REJECTED` | 사람이 반려. 사유 필수 | Streamlit |
| `ON_HOLD` | 근거 부족으로 보류. 판단이 더 쌓이면 다시 제안 | Streamlit |
| `SIMULATED` | 시뮬레이션 통과 | 시뮬레이션 |
| `MAPPED` | 모든 필드가 골드 표·컬럼에 매핑됨 | 매핑 화면 |
| `LOADED` | 적재 SQL 실행 기록이 등록됨 → 사용 가능 | 적재 기록 등록 |

상태는 revision마다 있다. 수정·쪼개기·합치기는 새 revision 또는 새 묶음을 만든다. 이전 revision 파일은 지우거나 덮어쓰지 않는다. `LOADED`된 revision 뒤에 새 revision이 생기면, 새 revision이 `LOADED`될 때까지 골드와 RAG는 이전 `LOADED` revision을 쓴다.

## 승인 화면 (Streamlit)

용어·별칭 후보는 같은 화면의 '용어' 탭에서 승인·수정·반려한다. 승인한 용어도 개념 묶음과 같이 적재 SQL로 골드에 들어간 뒤부터 쓰인다. 상세는 [랜딩의 용어집](LANDING.md#용어집--별도-도구).

기존 [지식 작업공간](../../../../03_FRONTEND/APPS/legal-knowledge-streamlit/site_design_app.py)의 승인·반려·수정 동작을 확장한다. 로컬에서 먼저 만들고 같은 앱을 Dataiku에 올린다. 화면은 S3 JSON을 읽고 쓴다.

| 동작 | 결과 |
|---|---|
| 승인 | 상태를 `APPROVED`로. 새 revision 파일 저장 |
| 수정 | 개념 이름·조항 역할·값·연결·검토 메모를 고친 뒤 `APPROVED`. 수정 전 revision 보존 |
| 쪼개기 | 서로 다른 개념이 섞인 묶음을 둘 이상의 새 묶음으로 나눔. 원래 묶음은 `history`에 분할 기록 |
| 합치기 | 같은 개념의 두 묶음을 하나로. 원래 두 묶음은 `history`에 병합 기록 |
| 반려 | `REJECTED`, 사유 필수. 판단 기록은 그대로 |
| 보류 | `ON_HOLD` |

묶음마다 근거 판단 기록, 실제 원문, 질문, 사용자 재지시를 펼쳐볼 수 있게 한다. 원문은 화면을 열 때 원문 저장소에서 조회한다. JSON에 복사하지 않는다.

## 효력

승인해도 바로 쓰이지 않는다. 골드에 SQL로 적재되어야 한다. 골드에 새 표나 컬럼이 필요하면 사람이 신청하고 만들어지기까지 시간이 걸린다. 신청 절차는 이 시스템의 범위 밖이다.

| 상태 | 쓰이는 곳 |
|---|---|
| 판단 기록 | 같은 세션의 멀티턴 (재지시·재답변) |
| `CANDIDATE`~`MAPPED` | Streamlit, 시뮬레이션. RAG 답변에는 쓰지 않음 |
| `LOADED` (골드 적재) | 모든 질문의 조문 진입·경로 조립 |

## 스키마 v0: 세부 조항 구조

연결 타입은 새로 만들지 않는다. 이미 [relation_read_policy.py](../../../../02_BACKEND/semantic_runtime/legal_agent/relation_read_policy.py)에 14종이 있다.

| 연결 타입 | 뜻 |
|---|---|
| CITES, BASED_ON | 단순 인용·근거 |
| APPLIES_MUTATIS_MUTANDIS | 준용 |
| USES_DEFINITION | 다른 조항의 정의를 씀 |
| DELEGATES_TO, SPECIFIES_DELEGATED_CASES_OF | 위임, 위임받은 내용을 구체화 |
| EXCLUDES, HAS_EXCEPTION, DEEMS | 제외, 예외, 간주 |
| VIOLATION_SANCTIONED_BY | 위반 시 제재 |
| TEMPORAL | 시행일·적용례·경과 |
| ANNEX_STANDARD, ANNEX_FORM | 별표 기준, 별지 서식 |
| UNKNOWN | 판별 못 함 |

새로 만들 것은 조항 **안의 내용** 구조다. v0는 개념 묶음 JSON의 `provisions[]` 한 항목이며 다섯 항목으로 시작한다.

| 항목 | JSON 필드 | 값 | 예 (cm-001) |
|---|---|---|---|
| 위치 | `anchor` | 문서·판본·단위 ID, 표시 이름 | 코스닥시장 상장규정 제26조 제1항 제4호, 기준일 2026-08-27 |
| 역할 | `role` | `DEFINITION`(정의) / `SCOPE`(범위) / `REQUIREMENT`(요건) / `THRESHOLD`(수치 기준) / `EXCEPTION`(예외) / `PROCEDURE`(절차) / `EFFECT`(효과) | `THRESHOLD` |
| 대상 개념 | 묶음의 `concept` | 개념 이름·용어집 참조 | 의무보유 한도(벤처금융·전문투자자) |
| 값 | `value` | `{"number": "0.1", "unit": "ratio", "display": "100분의 10", "comparison": "LTE", "basis": "상장신청일 현재 상장신청인의 자본금", "qualifier": "각각"}`. `comparison`은 `LT`/`LTE`/`GT`/`GTE`/`EQ` | 위 예 |
| 연결 | 묶음의 `relations[]` | 14종 중 하나, 출발·대상 조항 | — |

`value.qualifier`처럼 계산 방식을 바꾸는 문구를 값에 담는다. cm-001의 질문 "합산 기준인가?"에 대한 답이 "각각"이라는 단어에 달려 있다. 값이 없는 조항은 `value: null`이다.

## 새 스키마 제안

v0로 표현할 수 없는 판단이 나오면 LLM이 새 필드를 제안한다. 이 제안이 곧 "사용자 대화에서 나온 에이전트 판단을 모아 LLM이 제안한 스키마"다.

~~~json
{
  "schema_version": "ontology-schema-proposal-v0",
  "proposal_id": "sp-0001",
  "status": "PROPOSED",
  "target": "provisions[].value",
  "new_field": {"name": "period", "type": "duration", "example": "상장일부터 6개월", "required": false},
  "reason": "의무보유 기간처럼 기간 값을 수치·단위로 담을 곳이 없음",
  "evidence_bundles": ["cb-0003", "cb-0007"],
  "proposed_by": {"model": "...", "run_id": "...", "at": "..."}
}
~~~

| 상태 | 뜻 |
|---|---|
| `PROPOSED` | LLM 제안 |
| `ACCEPTED` | 사람이 Streamlit에서 받아들임. 이후 개념 묶음 JSON에서 이 필드를 쓸 수 있음 |
| `REJECTED` | 사람이 거절. 해당 값은 묶음의 `review_notes`로 남김 |

받아들인 필드도 골드 표에 해당 컬럼이 생기고 매핑되기 전에는 적재할 수 없다.

## 시뮬레이션

승인한 묶음과 받아들인 스키마가 문제없는지 모델 호출 없이 검사한다. 결과는 S3에 JSON으로 저장한다.

| 검사 | 내용 |
|---|---|
| 형식 | 모든 필드가 스키마 v0와 받아들인 제안에 맞는지. 미등록 필드·잘못된 연결 타입·잘못된 역할 값이 없는지 |
| 원문 결속 | 모든 `anchor`가 실제 원문 단위를 가리키고 판본·해시가 맞는지 |
| 근거 결속 | 모든 `evidence_judgments`가 에이전트 레이어의 실제 판단 기록을 가리키는지 |
| 재생 | 샘플 질문의 저장된 판단 기록에 이 묶음을 적용해 경로를 다시 조립했을 때, 인용 조항이 이전과 같은지, 달라졌다면 무엇이 달라졌는지. 경로 조립기는 단계 6에서 생기므로 **단계 6 전에는 이 검사를 "미실행"으로 표시하고 나머지 네 검사로 판정**한다 |
| 골드 규약 | 매핑된 컬럼의 물리명·용어명 30바이트, `VARCHAR` 타입과 한글 길이, Description 필수 항목 |

하나라도 실패하면 `SIMULATED`가 되지 않고 실패 항목이 화면에 보인다. 모델을 다시 호출해 답변 품질까지 비교하는 검사는 실험 절차(ADR)로 따로 한다.

## 골드 매핑과 적재

골드 표·컬럼은 사람이 신청해 만든다. 만들어진 표 정의를 매핑 화면에 등록하고, JSON 필드를 연결한다. 현장 표 정의를 받기 전에는 [골드 메타 규약](../DATAIKU_GOLD_METADATA_20261022/README.md)에 맞춘 **제안 표 정의**로 로컬에서 진행하고, 현장 정의를 받으면 매핑 화면에 등록해 바꾼다.

| JSON 필드 | 골드 표 | 골드 컬럼 | 상태 |
|---|---|---|---|
| `provisions[].value.basis` | (현장 골드 온톨로지 표) | (승인된 컬럼명) | 미매핑 / 매핑 / 타입 불일치 / 길이 초과 |

- 매핑은 S3에 JSON으로 저장하고 적재 SQL 생성에 쓴다. 확정된 매핑은 `00_SYSTEM/ONTOLOGY_GOLD_MAPPING.json`으로 내보내 코드 릴리스에 고정하고, RAG 서비스는 이 파일로 골드를 조회한다. 서빙은 S3를 읽지 않는다.
- 현재 Oracle 지식 어댑터에는 테이블 이름 매핑만 있다(`oracle.validate_tables`). 매핑 화면은 이를 필드·컬럼 단위로 넓힌다.
- 모든 필드가 매핑된 `SIMULATED` 묶음만 `MAPPED`가 된다.
- 적재 SQL은 `MAPPED` 묶음에서 자동 생성해 S3에 저장한다. GENOS용은 Oracle `MERGE`, 로컬용은 SQLite `INSERT … ON CONFLICT DO UPDATE`다. GENOS에서는 사람이 Dataiku에서 실행하고, 결과(행 수·실행 시각·실행자)를 적재 기록으로 등록하면 `LOADED`가 된다. 로컬에서는 `load-local`이 실행하고 기록까지 쓴다.
- 표 설계는 [골드 메타 규약](../DATAIKU_GOLD_METADATA_20261022/README.md)과 [테이블 정의서 기준](../DATAIKU_GOLD_METADATA_20261022/TABLE_SCHEMA_WORKBOOK.md)을 따른다.

## S3 폴더 구조

~~~text
ontology/
  schema/v0.json                          스키마 v0 (코드와 함께 고정)
  schema/proposals/<proposal_id>.json     LLM 제안 스키마
  bundles/<bundle_id>/r<revision>.json    개념 묶음 revision (불변)
  bundles/<bundle_id>/HEAD.json           현재 revision 번호
  simulations/<run_id>.json               시뮬레이션 결과
  mappings/<mapping_id>.json              골드 표 정의와 필드 매핑
  loads/<load_id>/load.sql                적재 SQL
  loads/<load_id>/receipt.json            사람이 등록한 실행 기록
  state/bundling_watermark.json           개념 묶음 작업의 마지막 처리 위치
~~~

revision 파일은 새로 쓰기만 한다. `HEAD.json`을 바꿀 때는 먼저 다시 읽어 예상 revision과 같을 때만 쓴다. 다르면 쓰지 않고 화면에 최신 내용을 보여준다.

## LLM이 할 수 없는 것

LLM은 개념 묶음과 새 필드를 **제안**만 한다. 다음은 하지 못한다.

1. 실행할 도구·SQL·코드·외부 목적지를 만드는 것. 적재 SQL은 매핑에서 코드가 만든다.
2. 스키마·연결 타입을 직접 등록하는 것. 사람이 받아들인 제안만 쓴다.
3. 존재하지 않는 조항 ID·판본·판단 ID·승인을 만드는 것. ID는 서버가 실제 기록에서 옮긴다.

v0로도, 받아들인 제안으로도 담을 수 없는 판단은 버리지 않고 묶음의 `review_notes`에 원문 표현대로 남긴다.

## 기존 지식 저장소와의 관계

기존 `legal_knowledge` 저장소(`lk_record`·`lk_head`·`lk_lookup`, 초안·검토·게시)는 MAIN103에서 꺼져 있다(`management_enabled=false`). v4 온톨로지는 이 저장소를 거치지 않고 S3 JSON → 골드 적재 경로를 쓴다. 기존 계약 검사 함수(`contracts.require` 등)는 JSON 형식 검사에 재사용할 수 있다.
