# 골드 축소안 R12 — 13표·60컬럼

2026-10-29. 사용자의 컬럼 축소 요청에 따른 **R11 후속 설계 후보**다. 기존 10표·49컬럼에 벡터 3표·11컬럼만 추가한다. R11의 16표·88컬럼보다 **3표·28컬럼(전체 컬럼 합계의 31.8%)** 줄인다. 실제 DB·제품 코드·MAIN·GENOS는 변경하지 않았다.

## 1. 무엇을 줄였나

| 대상 | R11 | R12 | 줄인 열 | 데이터 보존 방법 |
|---|---:|---:|---:|---|
| 기존 골드 10표 | 52 | 49 | 3 | R10 그대로. 원문 게시/판본 연결은 기존 manifest, 본문 순서는 현재 조회 계약 유지 |
| 벡터 게시 | 7 | 2 | 5 | query/원문 판본/model profile은 manifest, 건수·완료 시각·검증 정보는 완료 JSON |
| 벡터 구간 | 7 | 6 | 1 | 입력 해시는 기존 META_JSON에 보존 |
| 벡터 선택 | 3 | 3 | 0 | 조회 게시 ID PK·선택 벡터 게시 ID·변경순번 유지 |
| 전문검색 전용 3표 | 19 | 0 | 19 | 현재 SRCH_ROW의 unit/length/posting/stats와 manifest를 계속 사용 |
| **전체** | **88** | **60** | **28** | 정보 삭제나 실제 저장 용량 31.8% 감소를 뜻하지 않음 |

R11은 미측정 성능 개선을 위해 별도 FTS 투영과 메타 일반 컬럼을 많이 추가했다. 이번에는 **기존 구조로 수행하는 검색은 재사용하고, 실제 검색·권한 필터·경쟁 제어에 필요한 벡터 컬럼만 추가**한다. 전체 60개는 테이블별 컬럼 수의 합이다. 같은 이름을 재사용하는 컬럼을 제외하면 물리명 종류는 38개이며, R10 대비 새 물리명 종류는 6개다. 이는 표준용어 신규 승인 완료 수를 뜻하지 않는다.

## 2. 남기는 벡터 11컬럼

| 테이블 | 컬럼 | 역할 |
|---|---|---|
| VCTR_POST | `VCTR_POST_ID` PK | 검증한 벡터 묶음 식별 |
|  | `VCTR_POST_IFMN_CTNT` CLOB | 불변 manifest·모델·판본·완료 메타 JSON |
| VCTR_ITEM | `VCTR_POST_ID`, `VCTR_SEG_ID` 복합 PK | 게시본 안의 구간 식별·재개 시 배치 점조회 |
|  | `DOC_ID`, `SRC_UNIT_ID` | 일반 인덱스로 문서 권한·원문 단위 필터 및 그룹화 |
|  | `VCTR_META_CTNT` CLOB | 원문 구조·본문 조각·start/end·원문/블록/입력 해시 |
|  | `EMBD_VCTR_VALU` VECTOR(*,FLOAT32) | 임베딩 숫자 배열 |
| VCTR_HEAD | `RFRN_POST_HASH_VALU` PK | 조회 게시본당 선택 슬롯 |
|  | nullable `VCTR_POST_ID` | 선택 벡터 게시본, NULL이면 비활성 |
|  | `CHAN_NO` | 선택 경쟁·오래된 변경 요청을 막는 순번 |

실제 이름은 `IDD_B03_LGL_접미사` 또는 `IDD_B05_LGL_접미사`다. B03/B05는 공통 모델의 명명안 두 가지이며 공통 데이터를 두 벌 만들라는 뜻이 아니다. R10의 ONTL·POST·타입/길이·PK·필수 여부를 유지했다. 신규 이름·도메인과 native VECTOR의 실제 현장 지원은 미승인/미확인이다.

벡터의 `DOC_ID/SRC_UNIT_ID`를 JSON에만 두면 대량 후보 필터·그룹화에 다시 JSON 추출이 들어간다. 이 두 컬럼과 인덱스는 유지한다. HEAD 3컬럼도 유지해 UNIQUE 함수 인덱스 없이 조회 게시본당 하나의 선택 상태와 CAS를 관리한다.

## 3. JSON에 있어도 검증은 유지

| JSON 위치 | 보존 내용·검증 |
|---|---|
| 기존 SRCH_POST 정보 | `source_release_id`, `dataset_version`을 읽어 원문 게시본·데이터 판본과 대조 |
| VCTR_POST의 `manifest` | R3 원본 manifest 전체: `schema_version`, `query_id`, `source_release_id`, `dataset_version`, `documents`, `profile`, `segment_profile`. `digest(manifest)=VCTR_POST_ID` 유지 |
| `manifest.profile` | 모델·불변 revision·차원·endpoint 해시·L2 정규화·COSINE·분할/중첩 설정 보존. 모델 차원이 같아도 다른 profile은 혼용하지 않음 |
| VCTR_POST의 완료 메타 | 검증한 count·chain·registered_at·profile_sha256 등을 보존. 이 envelope 키는 R12에서 구현할 계약이며 현재 R3에 모두 저장돼 있다는 뜻은 아님. 기존 manifest 바이트 의미/해시와 별도 관리 |
| VCTR_ITEM META | 기존 `document_id/source_id/unit_id/block_id/start/end/source_sha256/block_sha256/input_sha256` 전체 유지. 일반 DOC/SRC 컬럼과 일치 확인 |

정상 읽기는 **HEAD의 query PK → POST의 pub PK → ITEM의 pub·문서·원문 필터** 순서다. JSON은 PK로 특정한 게시본이나 배치로 특정한 구간에서 읽는다. 전체 게시본의 JSON을 스캔해 활성 상태를 찾는 구조로 돌아가지 않는다. 선택한 POST의 `manifest.query_id`와 HEAD의 query ID를 반드시 대조한다.

profile별 과거 게시본을 대량 SQL 검색하는 기능은 이번 핵심 서비스 경로가 아니다. 해당 관리 조회가 필요해지면 완료 원장을 쓰거나 별도 인덱싱 필요를 평가한다. 모든 JSON 검색이 공짜가 된다고 가정하지 않는다.

## 4. 전문검색·관계 조회를 보존하는 방법

현재 `oracle_query_fulltext.py`는 이미 SRCH_ROW의 종류와 **일반 lookup 토큰 컬럼**으로 posting을 좁힌 뒤 위치 JSON을 확장한다. `oracle_query_catalog.py`에는 lookup ID 묶음 조회도 있다. R12는 이 저장 구조를 유지한다. 검색 단위·길이·토큰 위치·전체 통계가 사라지지 않는다.

R11에서 추가한 `FTS_UNIT/FTS_POST/FTS_STAT` 전용 어댑터는 R12 구현 대상에서 제외한다. 대신 실제 SQL에서 필요한 키를 먼저 제한하고 페이지 점수 재계산·반복 JSON 복원을 줄이는 작업을 수행할 수 있다. **컬럼 수를 줄인 이번 문서만으로 해당 속도 문제가 해결되지는 않는다.**

| 문제 | 기존 방식·관측 | R12 방식·원하는 결과 | 남는 한계 |
|---|---|---|---|
| 등록/매핑 과다 | R11 생성 산출물 16표·88열. 실제 Oracle 효과 미측정 | 13표·60열. 기존49열 의미 보존, 추가 벡터11열만 관리 | 전체 저장 크기·검색 속도 개선율은 미측정 |
| FTS 별도 투영 | 현재는 generic rows로 동작, R11만 새 3표를 제안 | 기존 토큰·위치·길이·통계를 유지하고 일반 키 인덱스로 좁힘 | 위치/길이 JSON 복원 비용이 남음 |
| 페이지 반복 계산 | `_page`마다 `_matches` scoring CTE 재실행. 페이지 내 count는 이미 analytic count로 결합 | 동일 요청·검색·권한·판본의 적중 ID/점수 재사용, 본문은 선택 페이지에서 읽기 | 요청 범위 크기·TTL·eviction·실패 재계산을 구현·측정해야 함 |
| 벡터 활성/필터 | R3는 JSON 함수 인덱스와 활성 UNIQUE 함수 인덱스 사용 | HEAD PK와 ITEM 일반 문서/원문 컬럼 사용 | 정확 벡터 거리 비용 자체는 남음. ANN 도입은 별도 |
| 원문 순서 | `oracle_query.py`에서 판본·문서 범위를 제한한 뒤 TO_NUMBER(BLOCK_ID) 범위/정렬 | 기존 숫자 순서·페이지 계약 유지. R11 순서 컬럼 추가 취소 | 큰 단일 문서의 숫자 범위/정렬 최적화 이점은 포기. 필요 시 실측 후 1열 재검토 |

함수 **인덱스** 미사용은 SQL에서 TO_NUMBER/JSON_TABLE 같은 함수를 전부 금지한다는 뜻이 아니다. 다만 해당 식의 결과에 일반 B-tree가 직접 적용된다고 주장하지 않는다. 문자 정렬로 바꿔 원문 10번을 2번보다 앞에 놓거나 범위/커서 의미를 바꾸지 않는다.

FTS는 현재 tokenizer·다단어 문구·반복 토큰·global pre-ACL phrase df·BM25·동점·total/cursor를 보존한다. ACL 뒤의 통계로 df를 바꾸면 순위가 변하므로 최적화와 구분한다. 결과는 현재 권한으로 제한한다. 관계도 owner/target이 행 종류별로 뜻하는 바와 미해결/후보 상태를 유지한다.

벡터는 기존처럼 문서·원문 단위별 MIN 거리 집계 후 순위를 매긴다. ANN 청크 top-k 후 그룹화가 같은 결과라고 가정하지 않는다. 이 설계에는 ANN 인덱스가 없다.

## 5. 무결성·실패·변경 경계

PK·NOT NULL과 일반 인덱스를 유지하고, 물리 FK·업무 CHECK·PK 외 UNIQUE·함수 인덱스는 만들지 않는다. Oracle 카탈로그에서 NOT NULL이 유형 C로 나타날 수 있으므로 ‘업무 CHECK 없음’을 NOT NULL 제거로 해석하지 않는다.

직접 컬럼 관계는 11개, 별도의 게시 JSON 관계는 2개로 문서화했다. 여기에 판본 경유 원문·다형 참조·ontology anchor 검증을 적용한다. 검증은 행별 원격 EXISTS를 반복하지 않고 게시 범위 배치 조회·anti-join·집계·해시 대조로 수행한다. JSON 관계도 게시 시 전체 검증 대상이다.

적재/활성화는 R11에서 명시한 보호를 유지한다. 실제 공유 PK 공간별 writer lease/fencing 확보 → 배치마다 token 확인 → 쓰기 중지/전수 검증 → 완료 POST 봉인 → 짧은 HEAD CAS 순서다. 원문 공용 행은 데이터 판본을 제어키로 포함한다. BUILDING·lease·실패 로그는 Agent/Dataiku 제어 영역에 두며, POST에는 완료된 불변 묶음만 노출한다. 이 제어는 구현 요구이고 현재 연결 완료 상태가 아니다.

| 상황 | 처리 |
|---|---|
| 부분 적재·중단 | HEAD 전환 금지. 같은 입력/profile·저장 행 내용 일치와 writer token 확인 후 재개 |
| 오래된 writer의 뒤늦은 배치 | fencing token·검증/봉인 상태로 거절. 시간 만료만으로 재시작하지 않음 |
| HEAD 최초 INSERT 경쟁·A→B→A | PK 충돌 처리, 이전 pub+순번 CAS, 선택/해제 때 순번 증가 |
| 잘못된 POST query/profile·원문 판본 | JSON에 옮겨졌어도 읽기/봉인 시 불일치 거절 |
| 원문/권한 변경 | 요청이 고정한 판본과 현재 허용 범위 검증. 다른 요청·판본 캐시 재사용 금지 |
| 직접 SQL로 부분 행 조회 | 봉인 게시본을 거치는 조회 VIEW/API와 계정 권한 필요. soft FK만으로 비노출이 자동 보장되지 않음 |

완료 게시본은 수정하지 않고 자동 물리 삭제도 하지 않는다. 향후 정리 기능은 HEAD·진행 요청·보존 이력 확인과 게시/삭제의 공통 제어키가 필요하다. 온톨로지 Gold 게시와 Agent WORK/EVT는 실제 동일 DB 트랜잭션이 가능한 권한/연결을 확인하며, 불가능하면 outbox 계약을 먼저 구현한다.

## 6. 변경 지도·이행

| 실제 위치 | 작업 |
|---|---|
| `02_BACKEND/semantic_runtime/physical_mapping.py`, `00_SYSTEM/ORACLE/physical_mapping.yaml` | Gold 13표 매핑·타입·PK·일반 인덱스·소프트 검증 계약. 현재 dev_silver 물리 FK/CHECK 검사를 일괄 제거하지 않음 |
| `oracle_migration.py`, `oracle_query_publish.py`, `oracle_query_catalog.py` | 기존 원문/조회 logical payload를 Gold 이름에 연결. FTS 형식은 유지. 봉인·원천·해시 검증 연결 |
| R3 payload `initial_vector.py`, `vector_publish.py`, `vector_silver/schema.py`, `publisher.py` | 2표6열 계약을 Gold3표11열로 변경. JSON 함수 인덱스 필수 검사 교체, HEAD·일반 컬럼·완료 메타·Agent 제어 연결 |
| `oracle_query_fulltext.py`, `oracle_query_db.py`, `oracle_query_index.py` | 전용 FTS 표 추가 없이 범위 선제한·배치·요청 범위 재사용. 실제 Oracle 계획/왕복 검증 |
| `ontology_work/repository.py`, `runtime.py`, `service.py`, `oracle_query_service.py` | Gold/Agent commit 경계, 실제 매핑/code pin·서빙 전환·재개·롤백 확인 |

위 파일명은 실제 코드 위치를 가리키며 이번에 수정한 파일이라는 뜻은 아니다. 상세 원천과 코드 규칙은 엑셀에 담았다.

새 표 적재→검증→reader 확인→선택 전환 순서로 이행한다. R12는 FTS 분리로 인한 manifest 변경을 요구하지 않지만, **실제 Gold target_binding/스키마 계약 변경이 조회 manifest를 바꾸면 새 조회 게시 ID가 필요**하다. 그 경우 query ID를 포함하는 벡터 manifest/segment ID도 새로 결속한다. 같은 profile·정확한 입력 해시의 벡터 숫자는 검증해 재사용할 수 있다. 무조건 재임베딩하지 않는다.

기존 Silver·게시본·원장은 보존한다. 롤백은 호환되는 코드 매핑·조회 채널·벡터 선택을 함께 되돌린다. 기존 요청은 고정한 판본으로 끝낸다. 1000 BYTE 설계 컬럼과 현재 어댑터512 BYTE 입력 상한, 원천 CLOB과 R10 문서명2250 BYTE의 차이는 남는다. 실제 길이를 검증하고 초과를 조용히 자르지 않는다.

## 7. 검증과 수치의 범위

| ID | 구분 | 값/기준 |
|---|---|---|
| C1 | 설계 집계 | 49+2+6+3=60열, 10+3=13표 |
| C2 | 계산 | (88−60)/88×100=31.818…%. 등록 대상 컬럼 합계 감소율이며 용량·속도 감소율 아님 |
| C3 | 정적 집계 | PK13, 일반 인덱스11, 물리 FK/업무 CHECK/PK 외 UNIQUE/함수 인덱스0 |
| C4 | 미측정 | Oracle 실행시간·p95·처리량·디스크 변화·ANN 성능·구현 인일은 미산정 |

표/컬럼을 줄여도 같은 벡터 숫자·원문·토큰 위치를 저장하므로 저장 용량은 비례해서 줄지 않는다. JSON 메타를 PK 조회 후 읽는 비용이 일반 컬럼 조회보다 클 수 있고, 전문검색·큰 문서의 숫자 정렬 비용도 남는다. 이 안의 직접 이점은 등록·매핑·별도 저장 형식의 수를 줄이는 것이다.

문서 검사는 기존49컬럼의 이름/타입/정의/PK/필수 여부 보존, R11 제거28열의 명세, MODEL·XLSX·DDL의 열 순서/타입·합계, B03/B05 동등성, 참조 복합 PK·타입, 일반 인덱스 컬럼 유효성을 확인한다. 결과는 [VALIDATION.json](VALIDATION.json)에 있다. 자체 검토이며 Oracle 컴파일·현장 성능 인증이 아니다.

구현 후에는 같은 원문·권한·판본으로 관계/FTS 결과·문구·순위·커서·정확 벡터 그룹 순위·원문 hash를 대조해야 한다. 중복·부분 실패·stale writer·CAS 충돌과 재개/롤백도 확인한다. 반복 페이지의 SQL수·왕복·JSON 복원·본문 읽기를 따로 측정하고, 허용 지연 기준은 실제 기준선 확인 후 시험 전에 확정한다. 이번 문서 수정에서 새 품질/성능 실험은 실행하지 않았다.

근거: [R10 등록본](../DATAIKU_GOLD_REGISTER_20261028_R10/R10_수정안내.txt), [이전 R11 설계](../DATAIKU_GOLD_REDESIGN_20261029_R11/DESIGN.md), [R3 벡터 전달본](../../../../08_DEPLOYMENT/DATAIKU/vector_silver_20261029_r3/GUIDE.txt), 실제 코드 해시 [SOURCES.json](SOURCES.json). R11의 전용 FTS·추출3열·벡터17열은 R12에서 적용하지 않으며 비교 이력으로 남긴다.
