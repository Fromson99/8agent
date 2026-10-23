# DB 아키텍처 문서 안내

[전체 목차](../../ARCHITECTURE/ONTOLOGY_V3.md) · [구현 단위](IMPLEMENTATION_NAMES.md) · [현재 코드 검토](REVIEW.md)

**기존 Oracle 원장 위에 지식 버전·검토·실제 사용·변경 영향을 연결하는 설계입니다.** 기존 LK_RECORD/LK_HEAD/LK_LOOKUP을 유지하고 18개 추가 논리 테이블을 제안합니다. 원문·답변 본문은 각 정본을 참조합니다.

기준일은 2026-10-22입니다. Oracle 19c 호환 기능을 기준으로 한 설계·DDL 초안이며 실제 DB 생성·이행·성능 측정·MAIN 변경·GENOS 접속은 수행하지 않았습니다.

**Dataiku 레이어 구분(사용자 확인 2026-10-22):** 질의·에이전트 판단·실행 로그는 **에이전트 레이어**, 구조화 데이터·온톨로지·LLM Wiki는 **골드 레이어**에 저장합니다. [저장 책임 기준](../../../../00_SYSTEM/ARCHITECTURE.md#dataiku-data-layers)을 따르며, 아래 논리 테이블의 실제 데이터셋·Oracle 스키마 배치는 이 기준으로 구체화해야 합니다.

**골드 스키마 작성 기준(사용자 추가 자료 2026-10-22):** 물리 모델을 구체화·변경할 때 [메타마이너 명명·타입·Description 규약](../../../../00_SYSTEM/ARCHITECTURE.md#dataiku-gold-schema-convention)과 [테이블 목록·Bizmeta·등록 대상·컬럼 정의 양식 및 사진 7장](../../ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/TABLE_SCHEMA_WORKBOOK.md)을 함께 따릅니다. 테이블별 출처·유형·가공 과정·생성시각, 컬럼 논리명·물리명·표준용어/도메인/인포타입 매핑, 타입 대조와 신청·승인·생성 상태를 작성해야 합니다. 아래의 기존 스키마·DDL 초안은 이 자료에 맞춘 표준 매핑·메타 승인·운영 생성이 완료된 모델이 아닙니다.

<a id="v3-24"></a>

## 상세 문서

| 문서 | 내용 |
|---|---|
| [전체 구조와 기존 저장소](database/OVERVIEW.md) | 설계 결론, 기존 Oracle·basis·조사경험 저장소, 배치와 쓰기 책임 |
| [식별·버전·테이블·ERD](database/MODEL.md) | 공통 키·효력 시점·권한·참조, 테이블별 정본과 JSON 경계 |
| [조회·인덱스·거래금액 사례](database/QUERIES.md) | 최초 진입, 근거 숏컷, 관계 탐색, 변경 영향 조회 |
| [트랜잭션·철회·복구](database/TRANSACTIONS.md) | CAS·게시·원문 개정·사용 확정·outbox·누락 관리 |
| [코드 연결·이행·검증](database/MIGRATION.md) | 현행 대비 목표, 변경 파일, 이행·롤백·자원·검사 |

## 스키마와 조회 산출물

| 파일 | 용도 |
|---|---|
| [스키마 명세](database/SCHEMA_DRAFT.json) | 전체 컬럼·PK/FK·제약·인덱스 |
| [Oracle DDL 초안](database/ORACLE_DDL_DRAFT.sql) | 테이블·FK·인덱스 정의, 미실행 |
| [주요 조회 SQL](database/READ_QUERIES.sql) | 바인드 기반 조회 6개, adapter 연결 전 골격 |
| [코드 확인 근거](database/EVIDENCE.json) | 당시 코드·선택 릴리스 지문 |
| [설계 당시 정적 검사](database/VALIDATION.json) | 문서 분리 전 검사 결과, 당시 파일 hash 보존 |
| [문서 분리 검사](../../ARCHITECTURE/ONTOLOGY_V3/REORGANIZATION_VALIDATION.json) | 분리 후 링크·내용 보존·DDL 불변 확인 |

검토·적용·현재 원문 유효성은 서로 다른 상태입니다. 제시한 후보와 실제 사용한 지식을 구분하고, 미색인·권한 제한·반영 지연이 있으면 영향 조회의 확인 범위를 표시합니다.
