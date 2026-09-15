# 용어집 우선 증분 정합성

## 현행 전체 관계 데이터 소비 — 2026-09-15

[전체 용어·관계 묶음](GLOSSARY_KNOWLEDGE_BUNDLE.md)을 기본 `build-all`과 문서–용어 연결에
배선했다. FIBO/Wikidata 한국어 번역, NLSH, 공식 관계, ID 대응/별칭, 법률용어 관계의
원장 전체를 hash로 고정한다. 실제 소비자는 `glossary_linking`과 기존 의미 작성기의
`dictionary_lookup`이다. 아래 연구 실행/명시 조회의 “기본 CLI 미연결” 설명은 당시 상태이며,
지금의 원천 관측 소비와 구분한다. 의미 자동 승인·운영 RAG 활성화는 하지 않는다.

## 외부 개념의 한국어 번역 DB — 2026-09-15

[한국어 번역 보정 세대](CONCEPT_KOREAN_TRANSLATION_REPAIR.md)는 기수집 FIBO·Wikidata의
원천 ID·정의·관계를 보존하고 한국어 번역을 별도 SQLite에 저장한다. 실제 처리 완료/실패는
해당 가이드의 status 및 completion.json으로 확인한다. 연구 실행기에서 기존 pipeline.py의
`glossary translate` 분기를 명시 주입하며 기본 MAIN CLI에는 아직 연결하지 않았다.
소비자는 한국어 lookup과 원천 관계 inspect다. 번역은 의미 검토 근거를 대체하지 않으며,
현재 glossary review 기본 입력·current_draft·운영 RAG를 자동 변경하지 않는다.

## 2026-09-15 법률용어끼리 연결하는 동일 표기 규칙

사용자 지시: 같은 표기의 법률용어가 없는 일상용어는 제외하고, 법률용어가
있는 항목만 관계를 옮긴다. 여기서 법률용어는 법제처 지식베이스의
`knowledge_terms`이고 본문 출현 여부로 정하는 제품 `LEGAL_TERM`과 다르다.
이 작업은 모델/프롬프트/검색 효과 비교가 아닌 결정적 용어집 DRAFT 구축이다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary legal-relations build \
  --output 01_DATA/LEXICON/glossary-v1/legal-relations-20260915-v1
.venv/bin/python 06_TOOLS/pipeline.py glossary legal-relations inspect \
  --state 01_DATA/LEXICON/glossary-v1/legal-relations-20260915-v1 --term 채권
.venv/bin/python 06_TOOLS/pipeline.py glossary legal-relations verify \
  --state 01_DATA/LEXICON/glossary-v1/legal-relations-20260915-v1
```

입력은 `current_draft`의 hash 고정 사전과 그 사전이 기록한 collection의 전체
카탈로그다. `--glossary`, `--catalogue-db`로 명시할 수도 있지만 collection
identity가 일치해야 한다. 출력은 새 디렉터리에만 발행한다.

- 전체 법률 목록에서 정확한 표기(공백 포함)로 대응한다. 후보 0개는 EXCLUDED,
  1개는 사용자 규칙에 따라 연결, 복수 ID는 기본 HELD다. 원천 동음이의어 Y도 보류한다.
- 복수 후보 중 정확히 하나가 반대 방향의 원천 관계를 제공하고 그 원천의 상대
  표기가 법률 ID 하나에만 대응할 때만 `UNIQUE_RECIPROCAL_RELATION`으로 연결한다.
  이를 독립적인 의미 검증이나 정본 승인으로 취급하지 않는다.
- `legal_term_relations`의 보유 간선을 역으로 읽어 일상→법률의 관측 부분을
  재사용한다. 전체 일상 API를 새로 수집한 결과와 같다고 보고하지 않는다.
- 원천 관계 1건마다 CONNECTED/HELD/EXCLUDED/IDENTITY_ONLY 중 하나를 기록한다.
  상하위는 상위→하위로 통일하고 동의/반의/연관은 ID 순서로 중복 경로를 합친다.
  정규화한 상하위 code는 140304이며 원래 code와 방향은 원천 원장에 남는다.
- 자기 동의어는 간선 대신 IDENTITY_ONLY, 그 외 자기 관계는 보류한다.
  동의/반의/상하위 충돌과 상하위 순환 간선은 HELD로 남긴다.
- `relations.sqlite`는 사용한 카탈로그 표기·ID·내용 hash, 압축 원천 응답,
  원천 간선, 대응 후보, 반대편 근거 ID, 판정과 그래프를 보존한다.
  TSV는 원천 관계별 판정·전체 일상용어 대응·법률 간선 목록이다.
  `graph.json`은 규칙을 통과한 법률 ID 노드·간선만 담는다.
- `verify`는 출력 hash·원천 응답 hash·관계 회계·외래키·법률 ID 제한·제외 규칙·
  상하위 비순환을 검사한다. 법률 의미 정확도의 평가가 아니다.

담당 단계는 용어집 구축이며 소비자는 `inspect/verify`와 사용자 검토다.
PIPELINE.json의 `glossary_authoring` 설정 참조 아래에 선언한 명시 CLI이고,
공통 engine-host·RAG·현재 초안·의미군 membership의 자동 소비는 연결하지 않는다.
완료본과 기존 원문은 보존하며 새 입력은 새 output으로 재구축한다.

## 2026-09-14 ID 기반 외부 관계 연구 실행

[ADR-0404](../../../../04_EXPERIMENTS/ADR/ADR-0404-glossary-id-concept-linking/README.md)는
기존 공식 ID 관계, NLSH URI 별칭 해소, 고유 외부 개념 대응 검토를 실행했다.
공식 관계95,043건을 보존했으며, 외부 대응14건의 모델 관측은 SAME4/DIFFERENT7/UNKNOWN2/계약실패1이다.
이번 소표본에서 양 끝의 유효 SAME 근거가 있는 새 외부 직접 관계는0건이다.

격리 후보의 `glossary relations build/prepare-review/project/inspect`는 기존 pipeline.py의
glossary 분기 형태로 연결했다. 현재 작업 트리의 기본 CLI·review 입력·current_draft에는 반영하지 않았다.
아래 명령은 고정 후보를 주입하는 연구용 조회이며 실제 원천 ID로 공식 관계와 검토 상태를 확인한다.

```bash
PYTHONPATH=02_BACKEND .venv/bin/python -B \
  02_BACKEND/lawrag/research/experiments/glossary_identity_0404.py \
  glossary relations inspect \
  --state 04_EXPERIMENTS/ADR/ADR-0404-glossary-id-concept-linking/artifacts/run-004 \
  --entry-id moleg:knowledge_terms:298317
```

출력 SQLite의 `official_relation`, `uri_alias`, `concept_mapping`, `review_job`, `projection`과
기존 v3 `sense_*` 표에 원천·ID·입력 해시·근거를 보존한다. 모델 관측을 정본 의미군으로 승인하지 않는다.
전체 외부 개념 대응과 그래프 이웃을 이용한 추가 후보 탐색은 후속 작업이다.

## 2026-09-14 MAIN 용어 검토 v3 배선

`pipeline.py build-all --run-id <새 ID> --execute`는 단위 파이프라인을 순서대로 호출한다:
`glossary review complete` → 완료 영수증·초안 해시 검증 →
`build-data-stages --stage all --glossary-dir <검증된 초안> --execute`.
용어 검토는 호출당 기본 100건이며 미완료면 exit 3으로 멈춘다. 같은 명령으로 재개한다.
원문 구조화·문서별 의미 작성·벡터 DRAFT까지 연결되며 통합 RAG 세대 선택과 피드백 재구축은
아직 이 명령에 연결되지 않았다. 옛 ZIP 실행은 `build-all-legacy` 또는
`genos_pipeline.sh`로 명시한다. 이 경로는 v3 검토 결과를 소비하지 않는다.

```bash
# 입력·용어 검토 계획만 점검 (내부 모델 호출 없음)
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id glossary-docs-001 --exclude-internal --check-only

# GENOS 코드스페이스에서 구축; exit 3이면 같은 명령을 반복
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id glossary-docs-001 --exclude-internal --max-review-jobs 100 --execute
```

MAIN의 유지되는 용어집 작성 경로에 근거 결속 의미 검토를 연결했다. 명령은
`06_TOOLS/pipeline.py glossary review complete`이고 기본 입력은
`GLOSSARY_PIPELINE.json`의 `current_draft`, 기본 상태와 새 초안은 `llm_review.current_review_state/default_output`이다.
기존 `prepare`, `run`, `status`, `compile`도 명시 경로로 계속 사용할 수 있다.

```bash
# 외부/GENOS에서 모델 호출 없이 전수 계획과 입력 해시를 고정
.venv/bin/python -B 06_TOOLS/pipeline.py glossary review prepare
.venv/bin/python -B 06_TOOLS/pipeline.py glossary review status

# GENOS 코드스페이스에서만 내부 LLM을 사용해 한 번에 최대 N건 진행·재개
.venv/bin/python -B 06_TOOLS/pipeline.py glossary review complete --max-jobs 100
```

`complete`는 아직 진행 중인 작업이 있으면 exit 3으로 끝나며 초안을 선택하지 않는다.
같은 명령을 반복하면 완료 작업을 재호출하지 않는다. 모든 계획 작업이 terminal 상태가 되면
새 `dictionary.sqlite`와 `completion.json`을 발행한다. 모델 실패·근거 부족·충돌이 남으면
`review_status=PARTIAL`이다. 잘못된 응답은 attempt 원장에 보존하고 유효한 결과만
초안에 넣는다. `--retry-failed`는 실패한 작업을 명시 재호출한다. 이미 완료 영수증이 있으면
새 output 경로를 지정해 재실행한다.

새 계약은 의미 동일성 `SAME/DIFFERENT/UNKNOWN`과 비동등 관계
`BROADER_THAN/NARROWER_THAN/OVERLAPS/COUNTERPART_OF/RELATED_TO`를 별도 축으로 저장한다.
모델은 제공된 근거 span ID만 선택하고 원문 인용은 시스템이 고정된 source text·offset·hash에서
복사한다. 정의가 없으면 호출을 생략한다. `sense_candidate`, `sense_assertion`,
`sense_conflict`, `llm_review_v3`가 새 초안에 기록되고 `assemble --inspect --term`으로 조회한다.
공식 관계, 의미군 `meaning/membership`, 문서별 적용 범위는 자동 승인하지 않는다.
사전 원문을 동일 표기로 합치거나 모델의 관계를 동의어 확장으로 쓰지 않는다.

후속 `build-data-stages`는 `completion.json`의 원본·새 초안 hash와 데이터 루트 포함 관계가 맞을 때
검토 초안을 기본 사전으로 선택한다. 영수증이 없으면 기존 `current_draft`를 사용한다.
손상·다른 원본·루트 밖의 영수증은 거부한다. 선택된 새 사전은 구조화 캐시를 유지하면서
문서–용어 연결 세대를 새로 만들며, 그 연결을 소비하는 LLM 작업은 새 run ID가 필요하다.
현재 RAG 활성 릴리스와 GENOS 현장 배포는 별도 상태다.

용어 검토 계약은 `LEGAL_SCHEMA.json#authoring_contracts.GLOSSARY_REVIEW`가 고정한
`glossary-sense-review-v3.schema.json`을 사용한다. 현 서빙 세대에 묶인
`legal-semantic-v2.schema.json`과 그 hash는 변경하지 않았다. Lexical 관계를
LegalRelation의 predicate로 조용히 변환하지 않는다.
[사용자 지시·변경 전 해시·검증 영수증](../../../09_ARTIFACTS/AUDITS/20260914-glossary-review-main/README.md).

실제 진입점은 `06_TOOLS/pipeline.py glossary`다. CLI가 `glossary_alignment.main`을 직접 호출한다.
`PIPELINE.json`의 engine-host 프로필과 별도인 명시적 데이터 구축 명령이며, 존재하지 않는 `glossary_authoring` 프로필을 전제로 하지 않는다. 현재 CLI 실행까지 연결됐으며 기존 화면의
시작 버튼은 아직 이 명령에 연결되지 않았다.

## 용어집 v1의 기준 — 사전 먼저, 질문에서의 발견은 이후

```text
법제처·금융·세무의 기존 사전 항목
  → 선택한 법률 코퍼스 본문과 표제어 매치
      ├─ 있음: 법률용어 (CORPUS_PRESENT / LEGAL_TERM)
      └─ 없음: 일상용어 (GENERAL_IN_THIS_CORPUS / EVERYDAY_TERM)
  → 일상용어 ↔ 법률용어의 근거 있는 관계
  → 법률용어 → 법령·조문 연결
  → 이후 사용자 질문에서 용어 발견·의미 선택·탐색
```

‘일상용어’는 우리 코퍼스에서 미출현한 사전 항목이라는 제품 분류다. 출처의 원래 법률/일상
분류와 독립적이며 코퍼스 버전이 바뀌면 재분류된다. 법제처 사전 항목도 미출현이면 일상용어,
금융·세무 항목도 출현하면 법률용어다. 단어의 출현이 법적 정의나 동일 의미를 증명하지는 않는다.
공식 관계는 동의·상하위·관련 등의 종류와 원래 방향을 보존하며 모두 동의어로 바꾸지 않는다.
양쪽이 법률용어이거나 양쪽이 일상용어인 관계도 삭제하지 않는다.

현재 `classification`은 이 기준으로 구성되어 있다. `assemble --inspect --term`은 항목과
공식 관계 양쪽의 `term_class`를 함께 반환한다. `corpus_occurrences`는 본문에서 직접 찾은 위치다.
공식 API의 관련 조문 연결을 뜻하지 않으며 `article_connections`에 그 차이를 표시한다.
현재 작성 초안에 공식 `term_articles` 링크는 아직 조립되지 않았다.

`build-data-stages`에서 용어집 정의를 LLM에 전달하는 기능은 만들어진 용어집의 후속 소비자다.
사전 자체의 구축·용어 관계·법조항 연결을 그 힌트 제공으로 대체하지 않는다. 기존 문서별 인용
정의는 별도 출처와 적용 범위를 가진 보조 항목이며, 배경 단어를 새 용어로 추출하지 않는다.

## 현재 기본 작성 초안 — 2026-09-14

`GLOSSARY_PIPELINE.json.current_draft`는 `01_DATA/LEXICON/glossary-v1/boundary-20260914-v3`를
선택한다. `pipeline.py build-data-stages`의 새 문서–용어 연결도 이 초안을 사용한다.
이전 `definitions-20260913-v2`와 기존 리뷰 결과는 별도 버전으로 보존하며 자동 이식하지 않는다.

매처 `literal-boundary-josa-v2`는 `ㆍ`·`·`를 단어 경계로 처리하고 `로부터`·`으로부터` 계열을
지원한다. 긴 합성어 안의 짧은 부분 일치를 허용하지 않으며 원문 offset을 보존한다.
API 대조에서 놓쳤던 5건을 모두 복구했다. 같은 수집 자료로 새 초안을 만들어 비교한 결과다.

| 항목 | 이전 초안 | 현재 초안 |
|---|---:|---:|
| 사전 원천 항목 | 113,458 | 113,458 |
| 공식 용어 관계 | 95,043 | 95,043 |
| 본문 출현 위치 | 2,022,684 | 2,065,590 |
| 본문에 등장한 원천 항목 | 70,851 | 71,115 |

기존 출현 위치의 누락은 0건이고 42,906건이 추가됐다. 추가 위치 전수의 의미적 적합성을 평가한
수치는 아니다. API 추가 수집·LLM 호출 없이 재구축했다. 공식 API 조문 링크의 버전·출처 결속은
계속 후속 작업이며, 5건 복구가 API와 본문 연결 전체의 동등성을 뜻하지 않는다.
[재구축·검증 기록](../../../../04_EXPERIMENTS/ADR/ADR-0369-pdf-build-feedback/README.md).

## 최초 수집

저장소 `.env` 또는 실행 환경에 승인된 `LAW_OC`를 설정한다. 값은 기록에 남기지 않는다.
키가 없으면 수집을 중단하고 공개 예시 인증값으로 대체하지 않는다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary collect
```

법령용어 사전과 지식베이스 법령용어 전체 목록을 각각 수집한다. 일상용어도 받으려면
`--include-everyday`를 추가한다. 검색어 필터는 사용하지 않는다.
완료 패키지는 `01_DATA/PACKAGES/EXTERNAL`에 저장하고 자동으로 로컬 용어 카탈로그에 적재한다.
페이지 누락, 총건수 변동, 식별자 충돌, 기존 원문의 해시 변조를 발견하면 완료 발행하지 않는다.
법령용어 사전은 같은 원천 ID에 여러 표기가 연결될 수 있어 원천 ID·원문 표기·사전구분코드·
법령종류코드를 함께 식별한다. 원천 ID는 그대로 보존한다. 같은 페이지의 완전히 동일한
행만 한 번 적재하고, 제외된 행의 페이지·행 번호·내용 해시는 패키지의
`request-plan.json#normalization`에 남긴다. 페이지 사이의 중복이나 내용 충돌은 계속 거부한다.
API 원문 행 수와 정규화 후 항목 수는 별도로 집계한다.
같은 명령은 중단 지점부터 이어받으며, 새 갱신은 `--snapshot refresh-20260912`처럼
새 이름을 지정한다. API 갱신은 전체 목록을 다시 받아야 삭제와 변경까지 확인할 수 있다.
문서 정합성 단계는 받은 목록의 내용 해시 차이만 검사한다.

이미 받은 완성 패키지는 다음으로 적재한다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary import --package /absolute/path/manifest.json
```

## 시작: 문서와 대조

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary start --documents 01_DATA/RAW/law
.venv/bin/python 06_TOOLS/pipeline.py glossary status
```

현재 외부 법령 XML과 행정규칙 XML을 사용할 수 있다. 사용자 문서는 TXT/Markdown 또는
파싱된 `result.json`의 `blocks[].text`를 지원한다. PDF/HWP는 먼저 문서 파서를 거쳐야 한다.
입력 디렉터리는 지원 형식으로 준비한 **전체 문서 snapshot**이어야 한다. 사라진 문서는
삭제된 것으로 보고 해당 출현 근거를 철회한다. 다른 문서 집합은 별도 `--state-dir`를 쓴다.

- 새/변경 문서: 전체 용어와 검사.
- 그대로인 문서: 새/변경 용어만 검사. 이전 음성 결과도 건너뛴다.
- 변경/삭제 용어와 문서: 기존 출현 근거 무효화.
- 검사 코드·규칙 변경: 전체 조합 재검사.
- 글자 수 필터 없음. 공백 차이를 허용하고 원본 본문의 필드 위치·offset을 보존한다.
- 앞뒤 단어 경계 또는 닫힌 조사 목록으로 출현을 검사한다. 형태소 의미 판정은 아니다.
  예: 투자신탁은 → 투자신탁 허용, 투자신탁 → 투자만 부분 일치한 것은 제외.
- 인용된 정의 대상 뒤의 '란/이란'을 정의문 힌트로 기록한다. 정의조의 모든 출현을
  정의로 취급하지 않는다. 이 힌트만으로 정의 적용범위나 의미 Concept을 승인하지 않는다.

## 결과

`01_DATA/LEXICON/moleg-alignment`에 검사 SQLite, `runs/` 실행 영수증,
`generations/<hash>/glossary.json` 확장 용어집, `CURRENT.json` 현재 세대 포인터가 생긴다.
문서에 출현한 용어는 활성 검색 표면으로 승격된다. 정의/법령용어/일상용어/미확인 표시와
원천 데이터, 사전 ID, 문서 근거를 유지한다. 기존 수동 glossary와 정본 Concept을 덮어쓰지 않는다.
데이터 변경이 없으면 재실행의 `checked_pairs`는 0이며 같은 용어집 세대를 재사용한다.

동일 표기의 여러 원천 ID는 유지한다. 표기가 같다는 것만으로 서로 다른 의미를 병합하지 않는다.
LLM 호출은 없으며 검색 정확도 개선 효과는 아직 평가하지 않았다.

## 목록·문서 출현 연결의 기존 완료 상태

승인된 LAW_OC로 `initial` snapshot의 세 목록 전체 수집과 문서 대조를 완료했다.
API 원문 437,790행 중 같은 페이지의 완전 중복 12행을 제외한 437,778항목을 적재했다.
법령용어 사전 73,041항목, 지식베이스 법령용어 144,361항목, 일상용어 220,376항목이다.
법령·행정규칙 문서 62개와 대조해 61,298항목을 활성화하고 출현 근거 3,374,264건을 기록했다.
모든 출현 근거의 원문 offset, 생성 JSON 해시 및 SQLite 무결성 검사를 통과했다.
실행 ID는 `c38c8a38655246e6ae16a6b631586310`이며 결과는
`01_DATA/LEXICON/moleg-alignment/exports/a09637e33fd40914d6d9e13fc1e62b42a05892b2d1dc94177661da153ae1287f/RESULT.md`에 있다.
이는 CLI 데이터 생성 완료이며 화면 시작 버튼이나 운영 RAG 연결 완료를 뜻하지 않는다.


## 정의·출처·관계까지 완성 수집하기

`Glossary Management`는 Document Ingestion 앞에서 준비하는 공통 기반이다.
문서–용어 출현 연결은 구조화 이후 `glossary start`가 맡는다.
현재 pulling은 없으며, 아래 명령은 외부 공개 API의 명시적 1회 수집/재개다.

```bash
# 세 목록이 모두 필요하다. 기존 완료 목록이 있으면 다시 수집할 필요 없다.
.venv/bin/python 06_TOOLS/pipeline.py glossary collect --include-everyday
# 기존 목록에서 모든 정의 ID 및 제공된 관계·조문 링크를 추적해 수집 대상을 동결한다.
.venv/bin/python 06_TOOLS/pipeline.py glossary complete --snapshot complete-20260911 --plan-only
# 미완료 요청부터 순차 실행한다. 기본은 전수 수집이다.
.venv/bin/python 06_TOOLS/pipeline.py glossary complete --snapshot complete-20260911
# 상태 확인 및 제한된 단위로 수집/재개
.venv/bin/python 06_TOOLS/pipeline.py glossary status --snapshot complete-20260911
.venv/bin/python 06_TOOLS/pipeline.py glossary complete --snapshot complete-20260911 --max-requests 100
```

- 구현: `lawrag.pipeline.glossary_enrichment`. 목록·파서·수집 구현을 snapshot에 결속한다. 변경된 입력/구현으로 재개하려면 새 snapshot을 사용한다.
- 공개 API는 기존 HttpClient의 직렬 호출·최소 1초 간격·백오프를 따른다. 전체 대상은 2026-09-11 목록 기준 627,119요청이며 여러 날이 걸릴 수 있다. GENOS API와 LLM 호출은 없다.
- `completion/<snapshot>/collection.sqlite`에 요청별 상태, 원문 응답(압축), 해시, 정규화 레코드, 원천 용어 연결을 저장한다. 실패하면 중단하고 같은 명령으로 완료 응답을 재사용한다.
- 원천이 명시적으로 ‘일치하는 법령용어가 없음’을 반환하면 빈 응답 건수로 기록한다. API 오류나 잘못된 응답을 빈 정의로 처리하지 않는다. `collection_complete`는 계획된 요청의 완료이며 정의의 전수 존재나 법률 품질 승인이 아니다.
- 목록의 복수 원천 ID를 각각 조회한다. `sense`에 출처별 정의를 저장하고 `term_sense`로 연결한다. `SOURCE_ID`는 원천 ID에 의한 연결, `LABEL_CANDIDATE`는 같은 표기에 따른 검토 후보다. 이름만 같다고 의미를 통합하지 않는다.
- `official_relation`에 모든 수집 관계 코드를, `official_article`에 법령 ID·조문 좌표와 원문을 보존한다. 검색 경로는 기존 SYNONYM/RELATED 선택을 유지하고 미사용 관계 수를 보고한다.
- 완료 후 같은 함수로 GENOS용 `dictionary.sqlite`와 `glossary.zip`을 생성한다. 기본 용어 목록, 정의·출처, 관계·조문과 수집 범위는 함께 버전 결속된다. `COMPLETED.json`은 완료 사전을 가리키며 문서 출현 연결의 `CURRENT.json`과 구분한다.
- 기존 목록 JSON의 빈 definition을 동음이의어 중 하나로 덮어쓰지 않는다. 완성된 정의는 별도 `sense`와 연결 테이블에서 조회한다. 기존 문서 출현 근거도 보존한다.
- GENOS `build-all --knowledge-zip ...`은 동일한 사전을 만들고 원문에서 찾은 용어에 출처별 정의 후보를 함께 전달한다. 후보 수·잘림·연결 종류를 표시하며 정본 승인으로 취급하지 않는다. 비XML 구조화에 용어집을 넣는 BL-001 실험과는 별도다.

출력의 coverage에서 정의 본문/출처 건수, 원천 ID 연결 용어 수, 표기 후보 수,
관계·조문 수를 확인한다. `empty_responses`와 `terms_without_source_requests`도 함께 확인한다.
초기 목록 437,778건과 정의 본문 0건이라는 이전 상태를 새 수집 완료로 오해하지 않는다.

공식 응답 필드 근거: [법령용어 본문 조회 가이드](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsTrmInfoGuide).
상세 호출은 목록 원천 ID에 결속된 trmSeqs 경로의 실제 공개 응답도 확인했다.


## 2026-09-11 전수 수집 실행 — 2026-09-12 사용자 요청으로 중지

최종 snapshot은 `complete-20260911`이다. 명령·시작 시각·프로세스 ID·코드 해시는
`90_RUNTIME/moleg_glossary_completion/complete-20260911/run.json`, 출력은 같은 폴더의
`worker.log`에 남는다. 이 기록은 시작 사실이며 현재 생존/완료 여부를 보장하지 않는다.
현재 진행률은 `pipeline.py glossary status --snapshot complete-20260911`의 completion을 확인한다.
완료 전에는 GENOS용 새 완성 ZIP이나 운영 서빙 완료로 보고하지 않는다.

초기 연결 확인용 `definitions-20260911`은 원천 결손 처리 보완 전 기록으로 보존한다.
실행/재개 대상은 최종 snapshot이며 이전 임시 snapshot을 운영 용어집으로 선택하지 않는다.

## 현재 문서 데이터셋에 한정한 수집 — 2026-09-12

사용자가 전체 관계 수집 대신 현재 데이터셋의 용어 정의·출처·직접 관계·연결 조문만 요청했다.
기존 `complete-20260911`의 전체 수집 프로세스는 중지했으며 완료 원문 응답은 보존한다.
현재 활성 세대는 `semantic-moleg-links-20260911-v1`의 159문서다. 약 164개라는 사용자 표현과
실제 활성 문서 수를 구분하며 별도 목록이 지정되면 해당 세대로 새 scope를 만든다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary complete \
  --snapshot corpus159-20260912 \
  --corpus-generation 01_DATA/SEMANTIC/GENERATIONS/semantic-moleg-links-20260911-v1 \
  --reuse-snapshot 01_DATA/LEXICON/moleg-alignment/completion/complete-20260911/collection.sqlite \
  --plan-only
```

실제 수집/재개는 동일 명령에서 `--plan-only`를 빼고 실행한다.
상태는 `pipeline.py glossary status --snapshot corpus159-20260912`로 확인한다.

- 문서·원문·스키마 세대 해시를 고정하고 실제 본문의 법령용어·지식용어 출현을 기준으로 요청을 선택한다. 문자 기반 탐색이며 모든 의미적 용어를 발견했다고 보장하지 않는다.
- 일상용어 전체를 독립적인 수집 출발점으로 삼지 않는다. 선택된 법령용어의 직접 관계 한 단계만 받으며 발견된 관련어의 관계를 다시 재귀 수집하지 않는다.
- 정의는 출처별 후보로 보존한다. 같은 표기에 해당하는 외부 법령의 정의가 반환될 수 있으며, 그것을 현재 문서에 적용되는 정의로 확정하지 않는다.
- 조문 API 응답 중 선택된 문서명과 실제 보유 조문 좌표에 대응하는 행만 최종 연결 데이터로 발행한다. 범위 밖 행 수를 기록하고 원 API 응답은 보존한다. 과거 원문과 현재 API의 판본 일치까지 자동으로 승인하지 않는다.
- `제1-2조` 같은 규정의 조문을 법률 API의 `제1조의2`로 변환하지 않는다. API를 적용할 수 없는 협회 규정·가이드라인도 본문의 출현 근거와 인용 정의 문장은 수집 범위에 포함한다.
- `scope.sqlite`에는 선택 문서, 용어별 대표 출현 근거, 정의문 단서와 원문 블록, 보유 조문 좌표가 들어간다. 모든 출현을 전수 저장하는 정합성 결과와는 별도다.
- 완료된 ZIP에도 scope 근거를 함께 반입한다. GENOS 사전의 `scope_document`, `scope_occurrence`, `scope_definition`에서 문서/정의 근거를 조회할 수 있다. 로컬 정의문 단서는 정본 의미 승인 결과가 아니다.
- 재사용할 과거 수집은 먼저 중지한다. 선택된 요청과 일치하는 완료 응답만 해시 확인 후 현재 파서로 재검증하고 새 snapshot에 복사한다. 과거 전체 수집 상태를 수정하지 않는다.
- `total_requests`, `reused_responses`, `remaining_requests`로 규모를 판단한다. 범위 밖 목록 항목은 `unqueried_catalogue_terms`로 표시하며 수집 누락으로 취급하지 않는다.
- 이 옵션은 기존 `glossary complete`의 범위 선택 기능이다. 별도 고아 실행기나 pulling 스케줄러를 만들지 않는다.


선택 결과: 159문서의 본문에서 법령용어 12,176항목·지식용어 30,675항목을 확인했다.
이는 의미별 개념 수가 아니라 출처별 목록 항목 수다. 대표 출현 근거는 298,557건,
인용 정의문 단서는 8,520건이다. 수집 계획은 정의 35,501요청, 직접 용어 관계 30,675요청,
조문 연결 30,675요청으로 총 96,851요청이다. 과거 완료 응답 10,357개를 재사용해
전환 시점의 새 조회 대상은 86,494요청이다. 요청 간격만으로 최소 약 24시간이며 완료 시각은 보장하지 않는다.
범위·재사용·외부 조문 제외·GENOS 반입 관련 검증을 포함해 48개 회귀 테스트를 통과했다.

실제 실행 기록은 `90_RUNTIME/moleg_glossary_completion/corpus159-20260912/run.json`,
출력은 같은 폴더의 `worker.log`다. 실행 기록과 현재 프로세스 생존 여부는 구분한다.


## 여러 기관의 용어집 확장 설계

KRX·금투협·금융위·내부 문서의 정의와 일상표현 연결은 [공통 용어집 설계](../ARCHITECTURE/MULTI_SOURCE_GLOSSARY.md)를 참조한다. 설계안이며 현재 법제처 수집/문서 범위 기능의 구현 완료와 구분한다.


## 외부 기관 공개 사전 수집

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary collect-external --snapshot public-20260912
# 일부 원천만 수집/재개
.venv/bin/python 06_TOOLS/pipeline.py glossary collect-external --snapshot public-20260912 --source nts
# 외부 사전 상태만 조회 (법제처 수집 상태와 구분)
.venv/bin/python 06_TOOLS/pipeline.py glossary status --external --snapshot public-20260912
```

구현은 `lawrag.pipeline.collect_public_glossaries`이며 기존 `glossary` CLI에 연결된다.
`bok`, `econedu`, `kofia`, `nts`, `krx`를 선택할 수 있다. 실제 원천별 확보 상태는
`01_DATA/LOGS/glossaries/<snapshot>/collection.json`을 확인한다. 일부 원천만 선택한
실행의 `collection_complete`는 그 실행의 `requested_sources`에만 해당한다.

- 원문은 `01_DATA/RAW/glossaries/<snapshot>/<source>/`, 구조화 가능한 사전 항목은
  `01_DATA/STRUCTURE/glossaries/<snapshot>/<source>/entries.jsonl`에 저장한다.
- HTTP 원문마다 URL·요청 조건·취득 시각·형식·바이트 수·SHA-256을 기록한다.
  재개할 때 같은 요청·해시인지 확인하고 완료 응답을 재사용한다. 원천 갱신은 새 snapshot으로 받는다.
- 경제배움e는 공식 전체 엑셀을 받고 목록 총건수와 비교한다. 엑셀의 순번은 안정적 원천 ID가
  아니므로 snapshot·행 좌표로 식별한다. 설명 원문과 출처표시·변경금지 안내를 보존한다.
- 국세청은 모든 목록 페이지에서 원천 ID를 모은 뒤 개별 상세 정의를 받는다.
  목록의 말줄임 설명을 완전한 정의로 취급하지 않는다. 중복 ID·누락·총건수 변화를 검사한다.
- 한국은행·금투협 PDF는 형식·페이지를 확인해 원문으로 보관한다. PDF 수집은 VLM 구조화
  또는 항목별 의미 검토 완료가 아니다. 금투협 자료는 과거 금융투자사료로 구분한다.
- KRX는 접근 및 개별 항목 확보가 확인돼야 완료로 보고한다. 메뉴 HTML만으로 완료 처리하지 않는다.
- HTTP 요청은 기존 공통 클라이언트의 직렬 요청·최소 1초 간격·백오프를 따른다.
  국세청 상세 1,718건은 최소 약 29분과 응답 시간이 필요하다. 실패 원천은 미완료로 남긴다.
- 이 결과는 RAW/DRAFT 수집 자료다. 법제처 카탈로그 import, 기관 간 의미 병합, 관계 승인,
  운영 RAG 선택 세대 변경, GENOS 배포는 실행하지 않는다. 후속 다기관 정규화·검토 입력으로 사용한다.

원천별 수집 결과는 [공개 용어집 수집 결과](../REPORTS/PUBLIC_GLOSSARY_COLLECTION_20260912.md)를 참고한다.

## 2026-09-12 직접 용어 관계 우선 수집

현재 금융·세무 사전에 법제처의 공식 일상표현 연결을 대조하기 위한 실행은
`corpus159-relations-20260912-r2`이다. 본문에 출현한 지식용어 30,675항목의
`legal_term_relations`만 조회한다. 전체 사전 목록과 금융·세무 원문은 재수집하지 않는다.
법제처 관계 원문의 출발 ID·대상 ID·일상/법률 종류·관계 코드·응답 해시를 보존한다.
발견한 일상용어의 관계를 재귀 조회하지 않는다. 표기 일치는 의미 동일성 승인이 아니다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary complete \
  --snapshot corpus159-relations-20260912-r2 \
  --corpus-generation 01_DATA/SEMANTIC/GENERATIONS/semantic-moleg-links-20260911-v1 \
  --completion-endpoint legal_term_relations \
  --reuse-snapshot 01_DATA/LEXICON/moleg-alignment/completion/corpus159-relations-20260912/collection.sqlite
.venv/bin/python 06_TOOLS/pipeline.py glossary status --snapshot corpus159-relations-20260912-r2
```

`--completion-endpoint`는 `complete`와 명시적 문서 세대가 필요하다. 여러 번 지정할 수
있으며 선택 API는 수집 계획에 고정된다. 계획 확인은 `--plan-only`, 제한 실행은
`--max-requests N`을 추가한다. 실행 중인 동일 snapshot은 파일 잠금으로 중복 실행을 막는다.
API 선택 수집은 `collection_only=true`이며 선택 요청이 완료되어도 전체 정의·조문을
포함한 완성 사전이나 `COMPLETED.json`으로 자동 발행하지 않는다. 이 응답 DB는 후속
용어집의 원천 관계 대조 입력이며 운영 RAG 변경이나 GENOS 배포가 아니다.

실행 기록과 로그는 `90_RUNTIME/moleg_glossary_completion/corpus159-relations-20260912-r2/`에
있다. 실제 진행률은 위 status 명령의 completion을 읽는다. `status.json`은 계획 작성 및
수집 종료 시 갱신되므로 장시간 실행 중 실시간 진행률로 쓰지 않는다. 최소 요청 간격
1초 기준 약 8시간 31분이며 응답 지연·실패 시 더 걸린다.

이전 기록을 다시 확인한 결과, 전수 수집은 KeyboardInterrupt로 중지되었고,
`corpus159-20260912`는 정의 응답 20,708개를 보존한 상태에서 해당 PID가 종료되어 있다.
후자의 실패 요청은 0건이고 worker.log에 예외 기록이 없어 종료 원인은 확정할 수 없다.
두 DB의 SQLite quick_check는 정상이다. 초기 `definitions-20260911`에는 ValueError
1건과 원천 결손 응답 처리 보완에 따른 대체 기록이 있으나 문서 범위 수집보다 이전 기록이다.
범위 제한이 데이터 손상을 일으켰다는 근거는 확인되지 않았다.
기존 수집은 정의를 모두 받은 뒤 관계를 받는 순서여서 직접 관계 완료 건수는 0이었다.
따라서 이번에 재사용할 완료 관계 응답은 없으며, 기존 정의 데이터는 원위치에 보존한다.

선택 API 수집·범위 필수·재개·범위 변경 거부·일상용어 비재귀·자동 발행 방지와
기존 수집/정합성 회귀를 포함한 27개 단위 테스트가 통과했다.

이번 직접 관계 수집의 첫 실행 `corpus159-relations-20260912`는 74개 응답을 받은 뒤
MST 1504487에서 `<Law>일치하는 법령용어가 없습니다. 검색조건을 확인하여 주십시오.</Law>`를
반환받아 중단했다. 기존 검증기가 이 공식 자료 없음 응답을 예상하지 못한 것이 원인이다.
`legal_term_relations`의 해당 envelope·정확한 문구·빈 레코드 조합만 결손으로 인정하도록
보완했다. 인증 오류·기타 envelope는 여전히 중단한다. 빈 응답 원문·해시는 저장하며
`empty_responses`에 집계한다. 후속 r2는 앞선 74개 정상 응답을 검증·재사용한다.
이는 이번 실행에서 확인한 원인이며, 로그가 없는 이전 corpus159 실행의 종료 원인까지
같았다고 추정하지 않는다. 초기 실패 실행과 원문은 보존한다.


## 부분 수집 데이터로 용어집 v1 조립

`pipeline.py glossary assemble`은 용어집 작성 단계다. 기존 v1의 entry/surface/occurrence
테이블과 본문 matcher를 재사용하며 `glossary_assembly`가 범위 선택·공식 관계·기관 사전
대조를 연결한다. RAG 질의 처리나 의미 정본 승격을 실행하지 않는다. 기존 `v1-build`는
전수 목록을 적재하는 이전 초안 명령이므로 현재의 범위 기반 구성은 `assemble`을 사용한다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary assemble \
  --relations-db 01_DATA/LEXICON/moleg-alignment/completion/corpus159-relations-20260912-r2/collection.sqlite \
  --external-dir 01_DATA/STRUCTURE/glossaries/public-20260912 \
  --corpus-generation 01_DATA/SEMANTIC/GENERATIONS/semantic-moleg-links-20260911-v1 \
  --definitions-db 01_DATA/LEXICON/moleg-alignment/completion/corpus159-20260912/collection.sqlite \
  --definitions-db 01_DATA/LEXICON/moleg-alignment/completion/complete-20260911/collection.sqlite \
  --output 01_DATA/LEXICON/glossary-v1/scoped-finance-20260912-v1

.venv/bin/python 06_TOOLS/pipeline.py glossary assemble \
  --output 01_DATA/LEXICON/glossary-v1/scoped-finance-20260912-v1 --inspect --term 신탁
```

순서는 **수집 시점 고정 → 본문 출현 용어와 공식 직접 이웃 선택 → 출처별 설명 자료 보존
→ 본문 출현 색인 → 금융·세무 사전 표기 대조 → 미수집·의미 검토 분리**다.

- 법제처 전체 일상용어는 적재하지 않는다. 선택한 본문 용어와 받은 직접 관계의 대상만
  포함한다. 금융·세무 사전은 기존 구조화 항목을 보존하며 출처 간 의미를 자동 병합하지 않는다.
- 수집 DB를 짧은 읽기 트랜잭션으로 읽고 즉시 해제한다. 선택한 요청 상태·완료 원문·응답
  해시·정규화 행은 출력 DB의 `source_request`에 고정한다. 이후 수집 진척이 기존 초안을
  바꾸지 않는다. 전체 관계 요청 계획이 본문 지식용어 범위와 정확히 일치하는지 검증한다.
- `official_relation`은 방향·원천 ID·관계 코드·출처를 그대로 보존한다. 동의어·상위어·하위어를
  모두 SYNONYM으로 바꾸거나, 사전 간 표기 일치만으로 공식 관계를 전이하지 않는다.
- `external_candidate`는 기관 항목 → 일치한 원천 항목 → 본문 용어의 대조 경로를 보존한다.
  표제어·원천 영문·명시적인 약어 표제어 부분 일치는 구분되며 전부 MEANING_REVIEW다.
  여러 원천 ID나 후보 경로 수를 동음이의어의 의미 개수로 해석하지 않는다.
- `classification`은 해당 항목의 표제어가 실제 선택 본문에 등장하는지 검사한다. 법적 권위나
  특정 법에서의 의미 동일성 판단이 아니다. 별칭 출현만으로 표제어 출현을 인정하지 않는다.
- `review_queue`는 후보가 있으면 MEANING_REVIEW, 후보 없이 본문에 등장하면 CORPUS_LINKED다.
  둘 다 없고 관계 수집이 미완료이면 WAITING_FOR_RELATIONS, 완료 후에도 없으면 UNLINKED_REVIEW다.
  후자는 연결이 불가능하다는 뜻이 아니라 현재 원천에서 대조 경로를 찾지 못했다는 뜻이다.
- `--definitions-db`는 반복 지정할 수 있다. 완료 응답만 원문 해시와 파서로 재검증하고 범위에
  대응하는 자료만 `definition_record`에 보존한다. 011401/011402는 설명, 011403은 번역,
  011405는 안내, 그 외는 미분류 원천 자료다. `definition_candidate`에서 SOURCE_ID와
  LABEL_CANDIDATE를 구분한다. 사전 비고·영문 번역을 법률 정의로 자동 확정하지 않는다.
- `report.json`은 수집 완료/미완료/실패/빈 응답 수, 본문 분류, 관계 코드, 원천 설명 자료 유형,
  대조 후보·검토 상태와 입력·구현 해시를 기록한다. `--inspect`는 생성물 해시를 검증하고
  해당 버전의 상태를 읽으며 `--term`으로 항목·공식 관계·대조 경로·설명 후보를 조회한다.
- 추가 수집 이후 같은 명령에 **새 --output 디렉터리**를 지정하면 새로운 시점으로 재구축한다.
  현재는 전체 초안 재구축이며 항목별 증분 컴파일이나 자동 실행 스케줄은 아니다.
  이전 초안·수집 원문·운영 선택 포인터는 보존한다.

부분/전체 재구축, 조회, 범위 밖 일상용어 제외, 의미 비병합, 관계 종류 보존, 손상 원문 및
범위 거부, 구축 중 수집 진척 격리, 설명/번역/안내 분리와 기존 v1·수집 회귀를 포함한
45개 단위 테스트를 통과했다. 실제 생성물의 건수와 완료 여부는 해당 버전 report를 따른다.


## 정의 중심 용어집 v1 정리 — 2026-09-13

2026-09-13 당시 작성 스키마는 `glossary-assembly-v2` / `glossary-llm-review-v2`였다. 제품 이름은 용어집 v1이며,
이전 산출물은 그대로 보존한다. 기존 v1 검토 계획은 재실행하지 않고 새 초안에서 prepare한다.
법제처 선택 관계 요청 30,675건은 완료되어 있으며 전체 상세 정의 수집 완료와는 구분한다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary assemble \
  --relations-db 01_DATA/LEXICON/moleg-alignment/completion/corpus159-relations-20260912-r2/collection.sqlite \
  --external-dir 01_DATA/STRUCTURE/glossaries/public-20260912 \
  --corpus-generation 01_DATA/SEMANTIC/GENERATIONS/semantic-moleg-links-20260911-v1 \
  --definitions-db 01_DATA/LEXICON/moleg-alignment/completion/corpus159-20260912/collection.sqlite \
  --definitions-db 01_DATA/LEXICON/moleg-alignment/completion/complete-20260911/collection.sqlite \
  --output 01_DATA/LEXICON/glossary-v1/definitions-20260913-v2

.venv/bin/python 06_TOOLS/pipeline.py glossary assemble \
  --output 01_DATA/LEXICON/glossary-v1/definitions-20260913-v2 --inspect --term PF대출
```

- 법제처 공식 관계와 경제배움e·국세청 사전은 보존한다. 사전 설명문에 등장한 단어로 후보를
  만드는 GAP_PROPOSAL 경로와 --gap-pool-limit 옵션은 제거했다. 단어별 금지 목록이 아니다.
- `entry_corpus_link`는 제공 기관과 무관하게 표제어의 실제 본문 출현을 연결한다. 법제처 항목과의
  대조 후보가 없어도 CORPUS_LINKED로 남기며 법적 의미나 적용 가능성 승인으로 해석하지 않는다.
- `corpus_definition`은 인용된 명칭 뒤의 이란/란/이라 함은/라 함은 패턴을 찾는다. 문서 ID·원문 해시·
  본문 블록·단위의 상위 조문 좌표·용어/정의 offset·원문을 보존한다. 같은 표제어라도 서로 다른
  문서/버전/위치의 정의를 합치지 않는다. 포괄적인 정의 추출기나 법률 해석기는 아니다.
- 문장 종결 단서가 있는 것은 CLOSED_SENTENCE_HINT, 목록/후속 블록 등이 필요한 것은
  CONTINUATION_REQUIRED다. 모두 미승인 후보다. 중단된 정의를 완전한 정의로 모델에 주지 않는다.
- 같은 절의 ‘이 법에서/이 조에서’ 등 명시적 범위 표현은 offset과 함께 EXPLICIT_SCOPE_HINT로
  보존한다. 상위 조문에만 범위 선언이 있거나 명확하지 않으면 UNRESOLVED다. 문서 전체 적용을
  추정하지 않는다. 명시적인 타 법령·조문 참조도 원문과 함께 UNREVIEWED로 남긴다.
- `entry_definition_link`는 표제어가 같은 사전 항목과 문서별 정의를 LABEL_CANDIDATE로 연결한다.
  금융·세무 표제어와 같은 본문 정의는 LOCAL_DEFINITION_LABEL 검토 후보가 된다.
- `assemble --inspect --term`은 사전 정의, 문서별 정의·범위·참조 단서, 본문 출현 위치와 공식 관계를
  함께 보여준다. 후보의 출처 ID 개수를 동음이의어의 의미 개수로 바꾸지 않는다.

## 용어집 LLM 검토 배선 — v2 역사적 절차

양쪽에 실제 사전 설명/정의 또는 종결 단서가 있는 본문 정의가 있을 때만 MEANING_CHECK를 준비한다.
비고·영문 번역·안내 링크·일반 출현 문맥만으로 비교 작업을 만들지 않는다. 본문 정의는 해당 문서와
위치를 하나의 대상 ID로 고정하고 같은 블록의 단서·예외 원문도 별도 문맥으로 보존한다.
원문은 최대 4,000자, 법제처 설명 후보는 최대 6개이며 생략/잘림 상태를 표시한다.

```bash
# 전체 검토 계획: 모델 호출 없음
.venv/bin/python 06_TOOLS/pipeline.py glossary review prepare \
  --glossary 01_DATA/LEXICON/glossary-v1/definitions-20260913-v2 \
  --state 01_DATA/LEXICON/glossary-v1/reviews/definitions-20260913-v2-r2

# 소수 작업만 가진 별도 샘플 계획: 모델 호출 없음
.venv/bin/python 06_TOOLS/pipeline.py glossary review prepare \
  --glossary 01_DATA/LEXICON/glossary-v1/definitions-20260913-v2 \
  --state 01_DATA/LEXICON/glossary-v1/reviews/definitions-20260913-v2-r2-sample3 --sample-jobs 3

# GENOS 내부에서만 실제 샘플 실행
.venv/bin/python 06_TOOLS/pipeline.py glossary review run \
  --state 01_DATA/LEXICON/glossary-v1/reviews/definitions-20260913-v2-r2-sample3 --max-jobs 3
.venv/bin/python 06_TOOLS/pipeline.py glossary review status \
  --state 01_DATA/LEXICON/glossary-v1/reviews/definitions-20260913-v2-r2-sample3
.venv/bin/python 06_TOOLS/pipeline.py glossary review compile \
  --state 01_DATA/LEXICON/glossary-v1/reviews/definitions-20260913-v2-r2-sample3 \
  --glossary 01_DATA/LEXICON/glossary-v1/definitions-20260913-v2 \
  --output 01_DATA/LEXICON/glossary-v1/definitions-20260913-v2-reviewed-sample3
```

--sample-jobs는 문서 정의/법제처 비교와 서로 다른 기관 사전 항목을 순서대로 교차 선택한다.
입력 해시와 선택된 작업 ID를 고정하며 나머지는 OUTSIDE_SAMPLE로 보존한다. 소수 호출 결과를
전체 검토 완료로 표시하지 않는다. 기본 run은 10건, 최대 1,000건이고 완료 작업은 건너뛴다.
실패/중단 작업의 재호출은 --retry-failed가 필요하다.

모델은 SAME_MEANING / RELATED_ONLY / DIFFERENT_MEANING / INSUFFICIENT_EVIDENCE 중 하나를
정확한 입력 해시·양쪽 원문 인용과 함께 반환한다. compile은 후보 상태와 llm_review 감사 자료를
새 초안에 보존한다. 공식 관계·본문 연결·정의의 적용 범위·meaning/membership을 자동 승인하지 않는다.

실제 provider는 기존 GENOS LLM 전용 배선이며 임베딩이나 외부 fallback이 없다. 현재 Codex에서는
GENOS에 접근하지 않는다. 합성 응답 계약 테스트와 실제 모델 호출은 별개이며 실제 호출 여부는
해당 review state의 attempt/provider/receipt로 확인한다. 입력·구현·모델이 달라지면 새 계획을 만든다.
GENOS 반입 후 경로가 달라져도 compile --glossary는 원본과 동일한 해시의 사전만 허용한다.

### 생성·검증 기록

현재 초안은 `definitions-20260913-v2`, 현재 검토 계획은 `reviews/definitions-20260913-v2-r2`다.
전송 스키마 수정 전 계획은 이전 기록으로 보존하며 r2를 사용한다. `prompt.json`은 API 전송용
부분 스키마와 로컬 전체 검증 스키마를 함께 보존한다. API가 지원하지 않는 길이·배열 개수 제약은
전송에서 제외하고 응답 수신 후 전체 스키마로 검사한다. 검증 기준을 완화한 것이 아니다.

본문 정의는 4,345개 명칭 / 8,533개 위치다. 이전 scope의 8,520건은 같은 블록·명칭을 한 번만
기록했지만 현재는 반복된 정확한 위치도 보존한다. 종결 단서가 있는 6,558건과 후속 본문이 필요한
1,975건을 구분한다. 같은 절에 명시된 범위 단서는 142건이며 나머지 8,391건은 UNRESOLVED다.
상위 조문 범위나 정의의 전체 적용 범위를 추정해서 채우지 않는다.

금융·세무 1,728개 원천 항목의 본문 출현을 보존했다. 법제처 동일 표제어가 없는 263개 명칭 /
274개 원천 항목도 모두 본문에 연결되며 UNLINKED_REVIEW로 남지 않는다. 본문 정의와 금융·세무
사전이 겹치는 명칭은 131개다. 공식 관계 95,043건과 이전 본문 출현을 모두 보존했다.
현재 실제 검토 가능 작업은 973건이며 전수 모델 검토를 실행하지 않는다.

회귀 테스트 62개와 실제 정의 원문·offset 전수 검사를 통과했다. 공개 샘플의 외부 Haiku 검증
기록은 `90_RUNTIME/glossary_definition_e2e/20260913-v2-r2/`에서 확인한다. 첫 실행의 API 스키마
거부 기록은 같은 상위 경로의 `20260913-v2/`에 보존한다. 외부 검증은 공개 입력 3건에 한정한
별도 실행이며 제품 기본 provider의 GENOS 전용 정책이나 전역 반출 설정을 바꾸지 않는다.
실제 GENOS 모델·현장 전송 검증은 여전히 미실행이다.


## 새 구조화 문서에 용어집 연결 — 2026-09-13 작업 코드

현행 소비자는 `pipeline.py build-data-stages`다. `current_draft`를 기본으로 사용하며
`--glossary-dir`로 다른 불변 작성 버전을 지정할 수 있다. `genos_build` 직접 호출은 이 옵션을
명시해야 한다. 과거 `build-all --knowledge-zip`의 ZIP 기반 사전 경로는 별도다.

`glossary_linking.project`는 구조화 원문을 바꾸지 않고, 표제어의 긴 표기 우선 매칭과 현재 문서의
인용 정의 추출을 수행한다. 문서·블록·단위·offset, 사전 해시와 원천 entry ID를 보존한다.
다른 문서의 국소 정의를 현재 문서의 정의로 전달하지 않으며 동일 문서의 정의도 적용 범위 미검토
후보로 둔다. `catalogue_link`는 기존 사전의 표기 연결이며 법적 적용이나 의미 동일성 승인이 아니다.

전체 출현·원천 후보 ID는 `LEXICON/LINKS/<지문>/links.sqlite`에 남긴다. LLM 입력은 기존
`dictionary_lookup` 필드에 작업당 최대 24개 출현·표기당 최대 6개 정의 후보로 제한하고 생략 건수를
표시한다. 입력의 원문은 그대로이며 이 힌트로 원문의 의미·조건·효과를 검토한다. 실제 `genos_build`는
`LLM/<run>/<document>/glossary-linked/authoring-source.sqlite`를 기존 작성 큐와 후속 적재에 전달한다.

용어집만 변경되면 구조화 캐시를 재사용하고 연결 산출물만 새 지문으로 만든다. 기존 LLM 실행과
사전 해시가 다르면 새 run-id가 필요하다. 연결 자체는 모델 호출 0회이며 GENOS 배포·실호출 및
운영 RAG 반영을 뜻하지 않는다. PDF 구조 규칙 생성에 사전을 제공하는 BL-001은 계속 대기다.
