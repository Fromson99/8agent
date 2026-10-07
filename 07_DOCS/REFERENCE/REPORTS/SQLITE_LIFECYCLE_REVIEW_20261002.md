# SQLite 스키마와 적재 로딩 조회 전체 과정 검토

우리 스키마에는 읽기 효율을 떨어뜨리는 구체적인 문제가 있다. 전체 문서와 개별 블록의 중복 JSON, 서빙에 함께 실리는 대규모 구축용 관계 payload, 수백만 연결 행의 긴 문자열 키, 조회 후 필터링·페이지 처리, 읽기 도구 안의 journal 쓰기가 비용을 누적시킨다. 개선은 저장 구조와 소비자 쿼리를 함께 다뤄야 한다.

스키마 추출 문서 자체의 DDL은 확인한 13개 DB와 모두 일치했다. 문제는 추출의 정확성보다 그 스키마를 생성하고 읽는 방식에 있다. 기존 세대 결속·원문 보존·검색 색인·캐시에는 유지할 장점도 있다. 현장 지연의 최대 원인과 개선 시간은 이번 읽기 전용 진단으로 인증하지 않는다.

## 검토 범위와 근거

- 대상 문서: [SQLite 전체 스키마와 제약조건 및 설계 이유](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/sqlite-schema-20261002T071554Z/full-detail/SQLite_전체스키마_제약조건_설계이유.md).
- 문서 SHA-256: `480721a88b862a6866c87dae33e87840ba523dcd1497d6fcc8a259fc2f011eea`.
- 로컬 활성 릴리스: `legal-agent-source-prefix-20260930-r3`, 활성 포인터 generation `37`.
- 데이터: `01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation`.
- 관측 시작: 2026-10-02 08:34 UTC. WSL 로컬 파일을 읽기 전용으로 검사했다.
- 활성 DB 10개, 해당 navigation에 연결된 감사 DB 1개, 문서 부록의 로컬 경험 원장·요청 journal 각 1개를 대조했다. 부록은 현장 운영 DB를 대표하지 않는다.
- 적재·구축은 현재 작업 코드의 실제 호출을 추적했다. 서빙은 선택 릴리스 코드를 우선 확인하고 작업 코드와의 차이를 기록했다. frozen 서빙 릴리스에는 구축 코드 전체가 없으므로 현재 구축 코드를 과거 세대의 생성 코드와 동일하다고 주장하지 않는다.
- 자체 검토다. 모델 호출, 새 품질 실험, 후보 성능 비교, MAIN 변경, GENOS 접근은 수행하지 않았다. 스키마 문서·제품 코드·완료 DB는 수정하지 않았다.

관측값과 코드 해시는 [evidence.json](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/sqlite-lifecycle-review-20261002/evidence.json), 용어집 물리 용량은 [glossary-size.json](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/sqlite-lifecycle-review-20261002/glossary-size.json)에 보존했다. 기본 검사 코드는 [inspect_schema.py](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/sqlite-lifecycle-review-20261002/inspect_schema.py)다. 추가 코드 해시·정의 출처·원문 관계 검사는 evidence.json에 별도 보강했다.

## 초기 적재에서 실제 사용까지의 연결

| 단계 | 실제 진입점과 동작 | 산출물과 소비자 | 검토 결과 |
|---|---|---|---|
| 입력 선택·구조화 | `pipeline.py build-data-stages --stage structure` → `genos_stages.structure` → `genos_build.ingest_files/source_jobs` | 선택 RAW·형식별 파서 → 구조 결과·`source.sqlite` | 입력 지문·부모·블록 소속을 검사한다. 전체 결과 JSON과 마디·블록을 동시에 저장한다. |
| 원문 통합 | `document-release` → `merge_sources` | 여러 명시 source store → 새 `store.sqlite` | 같은 문서 ID의 내용 충돌은 거부한다. 문서별 전체 rows를 메모리로 가져와 해시·복사한다. |
| 용어 연결 | `term_generation.build_generation` → `glossary_linking.project` | `links.sqlite`, 원문 복사본, 연결 보고서 | 원문 블록 스캔·표기 매칭·출처별 후보를 보존한다. 연결 원문 복사와 게시용 복사가 겹친다. |
| 서빙 원문 생성 | `storage.publish` | 원문 3표·manifest → `Store` | `CREATE TABLE AS SELECT` 후 고유·범위 인덱스를 만든다. 원래 제약은 보존되지 않는다. |
| 용어집·색인 생성 | `prepare_assets`·`compile_index`·`fulltext.build` | glossary 사본·검색 캐시, navigation, FTS | 선택 용어집 전체를 복사·검증한다. navigation은 조 단위 본문·정의·참조·연결을 만든다. |
| 감사 분리·공유·활성화 | `separate_navigation` → `publish_shared_generation` → 명시 CURRENT 변경 | 감사 DB·검색 세대·영수증 | 감사 보존과 검색 경량화가 있다. 공유 복사와 활성화는 별도이며 CURRENT는 비교 후 교체한다. |
| 앱 시작·최초 자원 준비 | `service.application` → 선택 코드 `create_app/Pipeline` → `Store`·`TermIndex`·`Glossary`·`ReverseMatcher` | 검증된 DB, Python 목록·맵·트라이·구조 캐시 | 대형 파일 해시와 전체 카탈로그 적재가 집중된다. 캐시는 프로세스 안에서 재사용된다. |
| 질문·탐색·읽기 | `/v1/rag/ask` → `legal_agent_adapter` → v5 `TiersTools` → `workflow_relations_tools/ExplorationTools`·`SourceSession` | 검색 후보·원문 span·요청 journal | FTS·ID 인덱스는 활용한다. 일부 도구는 전체 조회 후 필터·페이지 처리하고 핸들을 기록한다. |
| 결과·피드백·경험 | 요청 journal → 단계 산출물·publication/outbox·피드백 후보, 선택형 경험 처리 | 버전 결속 답변·관측·수정 후보 | 원문과 판단 이력 분리는 타당하다. 쓰기 비용과 오래된 경험의 적용 범위는 원문 조회와 별도로 관리해야 한다. |

현재 작업 코드의 `GENOS_REFERENCE_SCOPE_V2` 선택, reference target/candidate/witness 표, 최소 단위 fulltext, 통합 v6는 활성 v3 navigation 데이터와 구분한다. 추출 문서가 이 차이를 명시한 것은 정확하다.

## 실제 용량과 중복

단위는 MiB = 1,048,576 bytes, GiB = 1,073,741,824 bytes다. 파일 용량은 SQLite 파일의 물리 크기이며 JSON 용량은 UTF-8 값의 합이다. 물리 페이지에는 인덱스·헤더·여유 공간도 있으므로 두 값을 직접 합쳐 절감량으로 사용하면 안 된다.

| DB | 파일 용량 | 주 역할 |
|---|---:|---|
| glossary graph | 11,673.19 MiB | 외부 node·원천 관계·근거 |
| navigation | 1,855.77 MiB | 용어 출현·정의·원문 탐색·참조 |
| glossary identity | 852.46 MiB | 외부 개념 대응·관계 projection |
| dictionary | 721.31 MiB | 용어·정의·원천 요청·문서 출현 |
| glossary cache | 623.59 MiB | 통합 표기 및 표기 FTS |
| store | 480.03 MiB | 문서·구조 마디·블록 |
| translations | 405.74 MiB | 번역 단위·상태·시도 원장 |
| legal | 355.12 MiB | 법률 용어·관계·판단 원장 |
| lookup | 225.72 MiB | 출처별 표기 목록 |
| fulltext | 47.25 MiB | PeCab 본문·표제 역색인 |
| 활성 10개 합계 | **16.84 GiB** | 감사 DB 제외 |
| 별도 navigation 감사 DB | 14,241.55 MiB | 분리 전 전체 구축 snapshot, 서빙 조회 대상 아님 |

| 관측·계산 항목 | 값 | 해석 |
|---|---:|---|
| `document.json` | 159행, 177.31 MiB | 최대 한 행 17.58 MiB. 전체 blocks 308,795개·nodes 230,417개 내장 |
| 별도 `source_block.json` | 308,795행, 94.61 MiB | 별도 text 컬럼 41.71 MiB가 JSON에도 전수 동일하게 중복 |
| 별도 `source_unit.json` | 230,417행, 81.28 MiB | document 내 nodes와 별도 마디 행이 공존 |
| navigation `source.json` | 33,443행, 110.10 MiB | 전수에서 `text == '\n'.join(blocks[].text)` 확인 |
| navigation `definition.json` | 8,533행, 50.35 MiB | term_ids 연결 434,835개, 한 정의 최대 581개. 연결 수 자체가 오류라는 판정은 아님 |
| navigation `reference.json` | 146,994행, 280.29 MiB | source_text 합 134.27 MiB; 같은 source/block/hash/text를 한 번씩 세면 17.67 MiB |
| reference의 반복 witness text | **116.60 MiB** | 위 두 값의 차이. 제거 가능한 실제 DB 파일 크기나 압축률이 아님 |
| `occurrence`의 ID 값 | 5,539,572행, 총 390,625,379 bytes | term/source 두 문자열 합 평균 70.52 bytes. 행·인덱스 헤더 제외 |
| `occurrence`와 PK·역조회 인덱스 | **1,087.23 MiB** | navigation 파일의 약 58.6% |
| graph `edge` | 7,142,320행 | payload TEXT 값만 5,879,303,895 bytes, 약 5.48 GiB |
| graph `edge` 물리 표 | 9,277,632,512 bytes | 약 8.64 GiB. 별도 관계 인덱스 용량은 미포함 |

## 발견사항과 우선순위

아래 우선순위는 측정된 밀리초 순위가 아니라 확인된 반복량·영향 범위·수정 의존성에 따른 검토 판단이다. 모든 항목의 **문서 반영 상태는 이 검토서에 기록 완료**, **구현·검증 해결 상태는 미수정**이다. 기존에 해결된 부분은 각 항목에서 따로 설명한다.

| ID | 심각도 | 단계와 문제 | 판정·필요한 보완 |
|---|---|---|---|
| SR01 | 높음 | 전체 문서·본문·블록 JSON 중복과 메타데이터 조회의 결합 | 수정 필요. 원문 보존층과 작은 조회 projection 분리 |
| SR02 | 높음 | 대형 구축용 graph 관계 원장이 서빙 파일 검증 범위에 포함 | 수정 필요. 실제 소비 표·컬럼 중심으로 서빙 bundle 구성 |
| SR03 | 높음 | 수백만 연결 행에 긴 문자열 키와 중복 B-tree 저장 | 수정 필요. 내부 정수 키·연결표 물리 구조를 별도 후보로 설계 |
| SR04 | 높음 | 최초 로딩에 전체 파일 검증·카탈로그·구조 적재 집중 | 수정 필요. 세대별 사전 구축 projection과 worker별 검증 정책 필요 |
| SR05 | 높음 | 정의 조회의 전체 JSON 재조회·조건 검사 전 본문 로딩 | 수정 필요. 검색 키·출처 관계의 명시 컬럼 및 선필터 |
| SR06 | 높음 | 전체 결과 처리 뒤 페이지 절단·범위 필터 | 수정 필요. 정확 total·순위·cursor 계약을 보존하는 조회 설계 |
| SR07 | 중간 | 원문 READ·검증의 `SELECT *`와 개별 블록 반복 조회 | 수정 필요. 필요한 컬럼·묶음 조회, 원문 검증 보존 |
| SR08 | 중간 | 적재 중 원문·bundle 복사·해시·검증의 여러 전수 통과 | 조건부 개선. 중복 검증 증명을 재사용하되 무결성 gate 유지 |
| SR09 | 중간 | 생성·통합·게시 단계별 DB 제약 수준 불일치 | 수정 필요. 명시 DDL·필수값·관계 검사 계약 통일 |
| SR10 | 중간 | 읽기 도구의 핸들 생성이 자동 커밋 쓰기로 연결 | 수정 필요. 실제 동작 단위의 원자적 쓰기 묶음과 측정 |
| SR11 | 낮음 | 동일 컬럼의 중복 인덱스 | 수정 필요. 소비자·쿼리 계획 확인 후 중복 제거 후보 |
| SR12 | 중간 | 로컬 경험 원장의 WAL 설정과 GENOS 저장 조건 구분 필요 | 조건부 타당. 로컬 부록을 NFS 운영 계약으로 전용하면 안 됨 |

### SR01 전체 객체 JSON과 자주 읽는 필드를 분리해야 한다

현재 구축의 `_build_source_store`는 전체 구조 결과를 `document.json`으로 저장하고, 같은 nodes와 blocks를 각각 마디·블록 테이블에 쓴다. 블록 본문도 `source_block.text`와 JSON에 동시에 들어간다. navigation 구축은 조의 본문을 `text`와 `blocks[].text`로 다시 저장한다. 원문과 파생 색인이 별도로 존재할 이유는 있지만, 조회할 때 두 표현을 항상 함께 읽을 이유는 약하다.

특히 활성 `ReverseMatcher._build`는 `document_metadata`를 얻기 위해 모든 `document.json`을 가져와 파싱한다. 선택된 159문서에서는 해당 키가 0건인데 177.31 MiB의 JSON을 통과한다. JSON이 이미 메모리 캐시에 있더라도 최초 Python 디코딩과 객체 생성은 필요하다. 이후 matcher 캐시가 재사용되므로 매 요청 비용으로 표현해서는 안 된다.

제안은 전체 구조 JSON을 감사·복구 보존층에 유지하고, 서빙에는 문서명·메타데이터·ladder 등 실제 소비 필드를 명시적으로 제공하는 것이다. navigation도 표제·소속·좌표와 본문을 분리하고, 조 본문과 block 목록의 중복 보유가 필요한 API는 읽기 경계에서 재구성한다. source/text/span 해시는 원문 동일성 기준을 유지해야 한다.

근거: [현재 초기 저장](/home/jin/8-AGENT/02_BACKEND/lawrag/pipeline/genos_unified.py:406), [선택 릴리스 메타데이터 로딩](/home/jin/8-AGENT/08_DEPLOYMENT/RELEASES/legal-agent-source-prefix-20260930-r3/code/02_BACKEND/semantic_runtime/navigation_match.py:214), [navigation 본문 구성](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/term_index.py:146).

### SR02 graph 원천 원장이 전체 용량의 가장 큰 부분이다

graph.sqlite는 약 11.40 GiB이고 edge 표만 약 8.64 GiB다. 표본 payload에는 관계의 source/subject/target/predicate와 evidence 등이 들어 있다. 정확한 반복·외부 원자료 의미를 조사하지 않고 이를 삭제해서는 안 된다.

다만 온라인 `ConnectionReader._relations`는 외부 관계를 identity의 `source_edge`에서 찾고, graph는 node 존재·상세 정의를 읽는 데 사용한다. 구축용 `glossary_knowledge.Knowledge`는 graph edge를 실제로 사용한다. 따라서 **구축용 graph 원장은 보존하고 온라인 소비 projection을 따로 만드는 것**이 적합하다. graph라는 이름만 보고 전체를 불필요하다고 판단할 수 없다.

지금 `Glossary` 생성은 graph 파일 전체의 SHA-256을 확인한다. 파일을 열거나 특정 node 한 건을 읽는 것과 별도로 이 전수 검증이 로딩 비용을 만든다. 원천 edge를 포함한 파일 크기는 배포 복사·해시·캐시 점유에도 영향을 준다. 이 검토는 graph 파일 크기가 지연의 최대 비중이라고 시간 측정한 결과는 아니다.

근거: [서빙 파일 검증](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/full_glossary.py:45), [실제 관계 소비](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/full_glossary_connections.py:136), [구축 graph 소비](/home/jin/8-AGENT/02_BACKEND/lawrag/pipeline/glossary_knowledge.py:198).

### SR03 occurrence는 TEXT 키와 물리 저장 방식의 비용이 크다

`occurrence(term_id TEXT, source_id TEXT, PRIMARY KEY(term_id,source_id))`는 일반 rowid 테이블이다. 표와 복합 PK 인덱스, source 역조회 인덱스가 별도로 존재한다. dbstat 관측은 각각 약 431.18 MiB, 437.29 MiB, 218.76 MiB다. 앞서 표본 ID 길이로 설명한 부분은 이번 전수 합계 평균 70.52 bytes로 보완했다.

외부의 영구 문자열 ID는 유지하고, generation 안에서만 쓰는 `term_pk/source_pk` 정수 매핑과 연결표를 검토할 수 있다. 작은 복합키 연결표의 `WITHOUT ROWID`도 후보가 된다. 둘 모두 실제 조회·반대 방향 인덱스·구축 속도·ID 재현성을 검증해야 하며 임의의 절감률을 보장하지 않는다. 외부 문자열 ID나 비숫자 구조 ID를 그대로 INTEGER로 캐스팅하는 변경은 부적절하다.

SQLite의 일반 비정수 PK 테이블과 WITHOUT ROWID의 저장 차이는 [공식 문서](https://www.sqlite.org/withoutrowid.html)를 확인했다. 긴 키는 보조 인덱스에도 영향을 줄 수 있으므로 모든 테이블에 일괄 적용하지 않는다.

### SR04 최초 로딩 비용과 반복 요청 비용을 구분해야 한다

선택 릴리스에는 navigation 파일 검증 캐시, glossary 해시 memo와 연결 풀, TermIndex 카탈로그·정의 캐시, matcher 구조 캐시가 이미 있다. 원문 Store도 검증 증명을 캐시한다. 따라서 매 질문마다 16 GiB를 해시한다는 진단은 틀리다.

그러나 최초 자원 초기화는 다음을 수행한다.

1. 선택 원문·navigation·fulltext 및 glossary 소비 파일의 전체 해시를 확인한다. 확인한 파일 집합의 크기 합은 약 **16.49 GiB**다. 이는 해당 초기화 경로의 파일 크기 합계이며 실제 물리 디스크 읽기량·지연 실측은 아니다. OS 캐시와 호출 순서의 영향을 받는다.
2. term 253,324개·edge 48,101개, 통계·표기·정의 목록을 읽고 Python 구조를 만든다.
3. 원문 마디 230,417개·source 33,443개·문서 JSON과 구조 탐색용 정보를 읽는다.
4. 여러 worker가 있다면 프로세스 캐시와 Python 객체는 각 worker에 생길 수 있다. OS 페이지 캐시와 Python 객체 공유는 별개다.

미리 구축한 작은 카탈로그·메타데이터 projection, 필요한 범위의 지연 적재, 검증된 세대의 명시 warmup이 우선이다. 해시 검증을 없애는 방식으로 개선하지 않는다. 현재 작업 service의 warmup은 명시 GENOS 세대에 한정되며 로컬 frozen 릴리스로 자동 fallback하지 않는다.

근거: [해시 memo·연결 풀](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/navigation_agent.py:43), [선택 릴리스 TermIndex 캐시](/home/jin/8-AGENT/08_DEPLOYMENT/RELEASES/legal-agent-source-prefix-20260930-r3/code/02_BACKEND/semantic_runtime/term_index.py:380), [자원 준비](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/document_agent.py:20), [warmup](/home/jin/8-AGENT/service.py:567).

### SR05 정의 검색에 반복 전수 읽기가 남아 있다

v5 도구가 상속하는 `ExplorationTools.lookup_definition`은 `SELECT json FROM definition ORDER BY id`로 8,533행 약 50.35 MiB를 읽고, Python에서 source 범위·정규화 문자열을 검사한다. 이미 정의 카탈로그를 적재했는데 이 도구는 SQL JSON을 다시 읽는다. 후속 페이지도 같은 조회를 다시 수행한다.

또 다른 경로인 `workflow_relation_cards.definitions`는 캐시를 사용하지만, 정의의 key가 질문 대상과 맞는지 검사하기 전에 `sources.get(source_id)`를 호출한다. 전체 범위를 끝까지 순회하는 경우 관련 source JSON을 불필요하게 많이 적재할 수 있다. 정의가 가리키는 고유 source는 3,184개이고 그 JSON 합계는 약 31.65 MiB다. 모든 호출이 끝까지 순회한다는 뜻은 아니다.

정의의 normalized key·document/source ID·검토 상태를 조회 컬럼으로 두고 먼저 후보를 줄여야 한다. `term_ids` 배열 434,835개도 용어↔정의 연결로 관리하면 해당 관계를 직접 조회할 수 있다. LABEL_CANDIDATE를 승인된 의미로 바꾸지 않고 범위·동음이의·출처 상태를 보존해야 한다.

근거: [선택 릴리스 정의 조회](/home/jin/8-AGENT/08_DEPLOYMENT/RELEASES/legal-agent-source-prefix-20260930-r3/code/02_BACKEND/semantic_runtime/legal_agent/exploration_tools.py:395), [관계 정의 조회](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/workflow_relation_cards.py:160).

### SR06 페이지가 작아도 내부 처리가 작은 것은 아니다

FTS는 `MATCH`와 rank를 사용한다. 그러나 SQL 자체에 문서 범위가 들어가지 않고 Python `allowed` 집합으로 거른다. v5 호출은 rank에 limit를 주지 않으며, 정확 total·좌표 중복 제거 뒤 페이지를 만든다. 문서 하나를 선택해도 전체 색인의 일치 결과를 읽는 경로가 남는다. 이후 페이지 요청에서도 검색 결과를 다시 구할 수 있다.

`term_occurrences`는 해당 용어의 모든 source를 조회한 뒤 허용 범위를 교집합 처리하고, 모든 결과의 node card·route·handle을 만든 다음 페이지를 자른다. 출력 10건이어도 내부 작업이 10건으로 제한되는 구조가 아니다. literal 경로도 후보 문서 본문을 훑으며, EXPLAIN에서 문서 인덱스와 정렬용 임시 B-tree를 확인했다.

현재 v5의 문서/폴더 fulltext 결과 매핑은 matcher 메타데이터를 사용해 전체 결과 본문 로딩을 줄여 둔 상태다. 이 개선을 무시하고 “FTS 결과마다 본문 전체를 읽는다”고 일반화하면 안 된다. bounds가 있는 하위 구조 검색과 다른 도구의 본문 읽기는 남아 있다.

scope를 색인 조회와 더 가깝게 결속하고, total 계산·ID 페이지 조회·반환 페이지 상세화를 나눠야 한다. 정확 total을 포기하거나 임의 LIMIT를 넣어 회수 범위를 줄이는 변경은 현재 계약과 다르다. 동일 검색의 다음 페이지는 generation·scope·query·순위 규칙에 결속된 cursor 결과를 재사용하는 후보가 적합하다.

근거: [fulltext 전체 rank와 후필터](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/fulltext.py:297), [v5 위치 매핑](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py:159), [용어 출현 조회](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/exploration_tools.py:395).

### SR07 원문 READ는 인덱스가 있어도 과다 컬럼과 반복 호출이 있다

`Store.source`는 문서·블록 키로 찾지만 `SELECT *`를 사용해 text와 중복 JSON을 함께 가져온다. `SourceSession._read`는 source가 가진 블록 ID들을 개별 조회하고, 근거 검증에서는 같은 원문 블록을 다시 조회한다. 서브트리 경로 역시 `SELECT *`를 사용한다.

현재 block 범위 조회는 `CAST(block_id AS INTEGER)` 때문에 무조건 느린 상태가 아니다. 같은 표현식의 `block_range` 인덱스를 실제 EXPLAIN이 사용한다. ID 조회도 source PK·unit_pk 인덱스를 사용했다.

원문·해시·필수 좌표만 읽는 projection과 블록 묶음 조회를 우선 검토한다. 같은 요청에서 검증한 블록을 재사용하려면 generation과 파일 불변성·span 해시 검사를 유지해야 한다. 모든 Store 소비자가 같은 필드를 필요로 하지는 않으므로 기존 반환 계약을 일괄 축소하면 안 된다.

근거: [원문 읽기](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/storage.py:104), [READ·검증](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/source_tools.py:84).

### SR08 구축과 게시의 전수 I/O도 별도 비용이다

현재 원문 통합은 문서별 SELECT *·fetchall·digest·INSERT를 거친다. `glossary_linking.project`는 원문을 복사하고, `term_generation`은 연결 결과 중 원문 복사 반환값을 받지 않은 채 원래 source를 다시 게시한다. 그 복사본은 연결 보고서에 결속된 감사 산출물이므로 바로 삭제할 수는 없지만, 동일 원문을 파일 복제 대신 불변 참조·해시로 표현할 여지가 있다.

`prepare_assets`는 glossary bundle 전체를 세대에 복사하고 파일별 해시를 확인한다. 이후 Store/TermIndex/verify_assets/공유 게시에서 추가 검증과 복사가 이어진다. 실패·재개·입력 변경 탐지를 위한 검증은 필요하다. 검증한 파일의 동일성을 단계 간 안전하게 재사용할 수 있는지 검토해야 한다.

navigation 감사 분리는 이미 검색 DB를 줄였다. 현재 작업 코드에는 같은 파일시스템에서 전체 원장을 이동하고 검색 표만 새 DB에 복사하는 경로가 있다. 과거 copy/drop/VACUUM 방식만 보고 최신 구축도 항상 전체 원장을 두 번 복사한다고 판단하면 안 된다. 서로 다른 파일시스템·지원하지 않는 SQL 객체에서는 보수적 경로가 남는다.

근거: [통합 복사](/home/jin/8-AGENT/02_BACKEND/lawrag/pipeline/document_release.py:170), [연결 복사](/home/jin/8-AGENT/02_BACKEND/lawrag/pipeline/glossary_linking.py:124), [세대 생성](/home/jin/8-AGENT/02_BACKEND/lawrag/pipeline/term_generation.py:73), [서빙 묶음](/home/jin/8-AGENT/02_BACKEND/lawrag/pipeline/term_serving_bundle.py:11), [감사 분리](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/navigation_storage.py:77).

### SR09 제약의 일관성이 부족하지만 실제 오염과는 구분한다

현재 초기 source store, 통합 store, 게시 store의 NOT NULL·PK·FK·JSON 검증 수준이 다르다. 게시의 CTAS는 기존 제약을 승계하지 않으며 UNIQUE 인덱스만 재생성한다. navigation도 대부분 TEXT 및 JSON 형식·참조 무결성을 생성 코드에 의존한다.

이번 검사에서 원문 마디의 문서 부재, 부모 부재, 블록의 마디 부재, 블록/문서 원본 해시 불일치·NULL은 모두 0건이었다. navigation의 source/term/edge/definition/reference ID NULL도 0건이었다. 따라서 제약 부족을 현재 데이터 오염의 증거로 제시하지 않는다. 전체 도메인 의미·모든 DB 외래키·계층 cycle 전수 검증은 하지 않았다.

명시 DDL로 서빙 projection을 생성하고 필수 식별자·부모·범위·JSON 확장필드의 계약을 통일하는 것이 적절하다. 불변 세대의 무결성 검증과 FK/CHECK는 역할이 다르다. 이것만으로 읽기 속도가 빨라진다고 주장하지 않는다.

### SR10 읽기 도구 안에 쓰기 비용이 섞여 있다

요청 journal은 `isolation_level=None`, `synchronous=FULL`, DELETE journal을 사용한다. `ExplorationTools.handle`은 기존 identity를 조회한 뒤 신규 핸들을 INSERT한다. v5 도구 handler 호출 전체가 하나의 쓰기 transaction 안에 들어가 있지는 않다. 후보·경로·breadcrumb·cursor 생성이 여러 자동 커밋 쓰기로 이어질 수 있다.

따라서 도구 전체의 elapsed time을 source DB 읽기 시간으로 해석하면 안 된다. 조회, JSON 디코딩, 위치 구성, journal begin/body/commit을 나눠야 한다. 현재 코드에는 이 구간 일부의 측정 로그가 이미 있다. journal 스키마의 수십 DDL은 생성 시 한 transaction으로 묶여 있으므로 그 문제를 새 결함으로 중복 제기하지 않는다.

핸들 발행을 도구의 논리적 작업 단위로 묶는 방안이 적절하다. 상태 전이·재실행·중단 복구를 먼저 정의해야 하며, 성능을 위해 동기화나 불변 이력 검사를 끄는 방안은 권하지 않는다. `navigation_handle(kind,identity_json,binding_hash)` 조회에는 별도 검색 키/인덱스를 검토할 수 있으나 요청별 행 수와 비용 확인이 우선이다.

근거: [journal 연결](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/repository.py:34), [핸들 조회·기록](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/exploration_tools.py:41), [v5 handler 실행 경계](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py:374).

### SR11 같은 목적의 인덱스가 중복된다

identity에는 `official_out`과 `delivery_official_source`가 모두 `official_relation(source_id)`를, `official_in`과 `delivery_official_target`이 모두 `official_relation(target_id)`를 색인한다. 하나씩 남기는 후보를 검토할 수 있다. delivery 두 인덱스의 물리 크기 합은 약 6.54 MiB여서 전체 용량·로딩의 최우선 과제는 아니다.

다른 인덱스는 일부 접두 컬럼이 같아도 정렬·covering·선택도 역할이 다를 수 있다. 이름이 비슷하다는 이유로 삭제하지 않는다. 현재 선언과 EXPLAIN을 함께 확인해야 한다.

### SR12 경험 원장의 환경별 저장 계약이 필요하다

추출 문서의 action-memory 부록은 로컬 WAL DB이며 현재 `action_memory_store.Memory`의 기본 생성 코드도 WAL이다. 온라인 journal은 DELETE로 별도다. 이 둘을 같은 운영 설정으로 설명하면 안 된다. 최신 통합 경험 경로와 이 부록이 동일한 활성 DB라는 증거도 없다.

SQLite 공식 문서는 WAL의 공유 메모리 때문에 네트워크 파일시스템에서 다중 호스트 사용을 지원하지 않는다고 설명한다. 해당 로컬 클래스를 GENOS 공유 NFS에 그대로 연결하는 경우에는 별도 설계가 필요하다. 현재 현장에서 그렇게 연결됐거나 장애가 발생했다는 판정은 아니다. [SQLite WAL 문서](https://www.sqlite.org/wal.html).

근거: [로컬 경험 생성](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/action_memory_store.py:34), [v5 요청 journal 설정](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/journal-v5.sql:2).

## TEXT와 JSON에 대한 최종 판단

이 시스템에서 TEXT·JSON의 비용은 실제다. 긴 문자열 키가 여러 B-tree에 반복되고, 큰 JSON 전체를 읽어야 하는 소비자가 있고, 원문과 근거 문자열이 중복된다. JSON 문법의 따옴표나 필드명만 줄이는 것으로 이 구조적 비용을 해결하기는 어렵다.

법령 본문·정의 문장 자체는 TEXT로 두는 것이 자연스럽다. BLOB으로 같은 UTF-8 바이트를 옮기는 것만으로 작아지지 않는다. 자주 검색·조인하는 식별자, 숫자 좌표, 상태, 문서 범위, 관계는 명시 컬럼과 인덱스로 제공하고, 가변적인 원천 payload는 보존층 또는 필요할 때 읽는 별도 필드로 두는 편이 적합하다.

SQLite는 페이지 단위로 파일을 읽고 큰 값은 overflow 페이지를 사용할 수 있다. 따라서 키 검색이 인덱스를 타도 선택된 큰 JSON을 반환하는 비용은 남는다. 반대로 작은 컬럼만 SELECT했다고 항상 모든 큰 payload를 읽는다고 단정해서도 안 된다. 이번 문제 제기는 실제로 JSON 또는 SELECT *를 선택하는 코드에 근거한다. [SQLite 파일 형식](https://www.sqlite.org/fileformat.html).

JSONB 전환이나 다른 DB 제품 교체만으로 full scan·중복 본문·후필터·핸들 쓰기를 해결할 수는 없다. JSONB는 후보 중 하나이며 현재 Python `json.loads` 소비자와 SQLite 버전·반입 계약까지 바뀌므로 단순 컬럼 타입 변경으로 다루지 않는다.

## 제안하는 수정 순서와 이행 범위

1. **반복 요청에서 불필요한 읽기부터 줄인다.** 정의 조회의 선필터, 정의 관계의 key 검사 순서, 반환 페이지에 한정한 카드 생성, 원문 읽기의 필요한 컬럼·묶음 조회를 정리한다. 현재 도구의 scope·exact total·cursor·해시 검증을 유지하는지 검사한다.
2. **큰 저장물을 서빙용으로 분리한다.** 문서 메타데이터와 전체 구조 JSON, source metadata와 본문, reference edge와 witness, glossary 원천 원장과 서빙 projection의 경계를 정의한다. 원천 데이터는 보존한다.
3. **대량 연결의 내부 키를 재설계한다.** 영구 외부 ID↔세대 내부 정수 ID를 명시 매핑하고 occurrence 등 연결표에 적용한다. WITHOUT ROWID와 양방향 인덱스는 실제 후보로 검증한다.
4. **최초 로딩과 구축을 정리한다.** 작은 카탈로그를 사전 생성하고, 파일 검증 증명 재사용·worker 수·warmup·공유 저장 경로를 맞춘다. 프로세스별 전체 Python 객체 수와 메모리를 확인한다.
5. **journal 쓰기를 논리 작업 단위로 묶는다.** 출력이 작아도 카드·핸들 발급 수가 커지는 경로를 먼저 제한하고, 복구 가능한 transaction 경계를 유지한다.

이는 구현 제안이며 이번 검토에서 실행하지 않았다. 원문 Store는 현재 정확히 3개 테이블과 `term-source-generation-v1`을 요구한다. 별도 테이블을 무작정 추가하면 로더가 거부한다. 새 계약을 정할 때 다음 소비자를 함께 수정해야 한다.

- `merge_sources`·`publish`의 위치 기반 INSERT/SELECT *, 구조화 source 생성기와 검증기.
- `TermIndex`·`SourceMap`·matcher·Store·fulltext·용어집 cache/manifest.
- 정의·참조·원문 span·선택 도구, 피드백·경험의 generation/source 참조.
- source manifest·navigation/fulltext 해시·glossary cache 결속, 공유 게시·CURRENT·rollback.

원문 물리 DB를 바꾸면 store SHA가 바뀌므로 navigation/fulltext/관련 cache의 결속·재구축 범위를 명시해야 한다. 원문 재파싱이 필요한지와 저장 형식 이행만 필요한지는 별도 결정이다. 기존 불변 세대는 보존하고 새 세대를 만든다. 내부 정수 ID는 외부 source ID나 인용 좌표를 대체하지 않는다.

## 검증 결과와 남은 확인

**확인 완료:** 13개 DB의 실제 sqlite_master DDL과 추출 inventory가 일치했다. 활성 release/data manifest 결속, 실제 store/navigation 전체 파일 해시를 검증했다. 핵심 JSON 용량·중복은 위에 명시한 범위에서 전수 집계했다. source의 문서·부모·블록 소속·해시 관계 검사와 주요 쿼리의 EXPLAIN을 수행했다. 코드·데이터 변경과 외부 모델 호출은 없었다.

**미실행:** GENOS 현장 cold/warm 시간, OS/NFS I/O, worker RSS, 실제 요청별 쿼리·디코딩·commit 지연, 전체 DB 의미 무결성·정답 품질, 후보 이행·속도 비교. 부록 journal과 경험 원장은 해당 로컬 파일의 스키마 관측이며 전체 실행을 대표하지 않는다. 새 통합 v6 경험 DB는 추출 대상에 없으므로 그 운영 상태는 판단 유보다.

후속 측정은 동일 선택 세대·코드·질문·범위에서 `resources.index/tools/glossary/matcher/fulltext`, `fulltext.sql.timings`, `fulltext.location.timings`, `source_sql_*`, `source_json_decode_ms`, `journal.transaction.timings`를 연결해야 한다. 캐시 없음·동일 프로세스 반복·재시작·동시 worker를 구분한다. 최소한 문서 목록, 좁은 범위 FTS, 넓은 범위 FTS, 정의 조회, 다수 출현 용어, 참조 확장, 원문 READ, 다음 페이지, 세대 교체 후 재시작을 포함한다.

성능 비교 후보를 만들고 실행하는 단계에서는 저장소의 ADR 선점·기준 동결·동일 조건 비교 절차를 따른다. 이 검토의 파일 크기나 기존 코드 주석의 과거 지연 값을 새 성능 측정으로 사용하지 않는다.
