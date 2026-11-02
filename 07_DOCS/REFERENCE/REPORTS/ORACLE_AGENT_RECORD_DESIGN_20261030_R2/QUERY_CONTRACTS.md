# R2 조회 계약 — 구현 전 검토본

이 문서는 3표·21컬럼 축소안의 조회 경로를 구체화한다. SQL은 [agent_query_review.sql](agent_query_review.sql)에 있으며 Oracle 실행·실행 계획·실제 adapter 구현은 하지 않았다. 데이터·코드의 현재 선택 근거는 [DESIGN](DESIGN.md)과 source_inventory.json을 따른다.

| 예시 | 기존 소비자·관측 경계 | R2 조회 계약 | 예상 접근 인덱스·한계 |
|---|---|---|---|
| Q01 | session_identity·case/shortcut 대화 조회, request_journals | 인증된 세션의 실행 목록을 시각/키로 페이지 조회 | RUN I1. CLOB 없이 필요한 메타데이터만 반환 |
| Q02 | request_journals 및 case request 재조회 | 요청별 과거 실행과 현재 요청 상태를 함께 확인 | RUN I2 + 기존 STATE PK. 목록만 보고 새 실행을 소유하지 않음 |
| Q03 | publication.recover·case_repository.recover_requests | 상태별 후보를 찾고 STATE의 lease/fence/budget/outbox를 별도 묶음 확인 | RUN I4. 후보 조회가 복구 소유권·재전송 허가는 아님 |
| Q04 | progress.poll_journal·ontology_work.observations.export_journal | 고정 EVENT 종류의 소유 원장별 seq 이후 불변 기록 | REC I1. 원 event kind를 종류별 표로 나누지 않음 |
| Q05 | corrected_memory·case/shortcut 정정 이력 | 같은 원 객체의 보존판본 1 이상을 순서대로 조회 | REC PK. 현재 투영0을 과거 판본으로 반환하지 않음 |
| Q06 | repository 모델 시도·workflow 호출 상태 | 실행 안의 CALL 현재 투영을 상태 조회키로 찾음 | REC I2. 원 호출 상태·원 예산/전송 영수증과 재대조 |
| Q07 | app.source·근거/span/view 참조·부모자식 연결 | 정확 끝점 판본으로 정방향/역방향 참조를 페이지 조회 | REC I2. 원 REF와 선택한 graph head를 확인 |
| Q08 | 현재 판단/head·현재 outbox 조회 | 인증된 소유자/종류/기록키/판본0의 정확 조회 | REC PK. 원 보존판본·STATE head와 결속 확인 |
| Q09 | wiki_recall 등 소유 원장 밖의 등록된 검색 투영 | 등록된 IX 종류/조회키로 후보를 찾고 각 owner 권한 확인 | REC I3. 공통/개인 ACL 소비자 연결을 별도 검증 |
| Q10 | 원 payload·모델 wire·발행 결과 복원 | 권한 있는 REC/RUN이 참조한 완성 manifest 읽기 | BODY PK. 임의 hash 입력을 읽기 권한으로 쓰지 않음 |
| Q11 | 위 본문의 무손실 복원 | manifest의 1..N 조각을 묶음으로 읽어 크기/hash 확인 | BODY PK. CLOB 전송 잘림·누락·압축 오류는 실패 |

표의 인덱스는 정의상 대응이다. 실제 optimizer 선택·왕복 수·sort 여부·지연은 미검증이다. ORDS가 CLOB를 잘라 반환할 수 있으므로 CLOB 문자열을 받았다는 사실만으로 복원을 성공 처리하지 않는다. 기존 clob_text와 같은 완전 길이/내용 대조 경계를 보존하고 실제 전송 방식에 맞게 구현한다.

## 키·종류·원값

키 생성은 버전이 있는 canonical envelope와 정확 타입을 사용한다. namespace, 원 store ID, 원 표, 원 PK tuple, owner 종류가 빠져 동명이 충돌하지 않도록 한다. 숫자1/문자열1/NULL/빈 문자열은 envelope에서 구별하고 원 PK/원값도 본문에 보존한다. 해시만 같은데 원 식별자가 다르면 재사용하지 않는다.

Oracle VARCHAR2의 빈 문자열 처리 때문에 빈 원 식별값을 컬럼에 직접 쓰지 않는다. 64자리 해시를 컬럼에 두고 원 빈 문자열·NULL은 본문에 따로 보존한다. 원 SQL 컬럼명을 목표 물리명으로 치환하는 것으로는 이 계약이 성립하지 않는다.

`EVENT`는 보존판본1로 한 번만 추가한다. 원 event kind/seq/id/hash/payload는 본문에 있다. 새 정렬순번은 소유 원장별 cursor와 같은 transaction에서 할당하고 유일성을 adapter가 검사한다. 원 seq가 같은 서로 다른 원장을 한 owner로 합치지 않는다. 부분 이전 실패를 건너뛴 채 cursor를 성공 위치로 기록하지 않는다.

`CALL`의 lookup은 상태 종류를 포함한 버전 있는 키다. 논리호출/시도별 검색이 더 필요하면 `IX:CALL_ATTEMPT`와 같은 등록된 조회 행을 추가한다. `REF_OUT/REF_IN`의 lookup은 끝점의 owner/종류/기록키/정확 판본을 포함한다. 양방향 투영과 원 REF는 같은 본문을 참조하되, reader는 정확 원 REF·선택 head를 확인한다.

종류별 lookup의 원 재료·정렬순번 의미·immutable/current 여부·보유 정책은 registry에 고정한다. 검색 조건이 새로 생겼다고 무조건 본문 전체 JSON 검색을 추가하지 않는다. IX를 추가하면 실제 저장 행수와 쓰기 비용이 늘어나므로 실행 계획과 함께 검토한다.

## 페이지·동시 변경

- Q01 첫 조회의 상한 시각을 정하고 이후 페이지에서 마지막 `(시각,실행키)`를 쓴다. 페이지 사이 상태 변경은 보일 수 있다. 목록은 감사 시점의 일관된 스냅샷을 뜻하지 않는다.
- Q02/Q05/Q11은 불변 키·판본·조각에 대해 마지막 키를 사용한다. Q11 조각0은 데이터 페이지에 섞지 않는다.
- Q03은 스캔 상한 시각과 `(변경일시,실행키)` cursor를 쓴다. 후보 상태가 바뀌면 현재 스캔에서 빠질 수 있으므로 다음 스캔은 다시 시작한다. 실제 복구는 짧은 transaction의 CAS/fence로 소유한다.
- Q04는 시작 시 확정된 event cursor를 watermark로 고정한다. 원장별 정렬순번은 유일하고 증가하며 gap을 허용한다. 다음 페이지는 마지막 성공 seq 이후다. 온톨로지 수집 cursor는 전체 payload 수집/검증/중복 확인 성공 뒤에만 전진한다.
- Q06/Q07/Q08/Q09의 현재/검색 투영은 변경 가능하다. 처음 선택한 STATE head/revision을 페이지 묶음 전후로 확인하고 바뀌면 묶음을 폐기해 다시 조회한다. 새 작업을 실행하거나 모델을 재호출하는 재시도가 아니다. 반복 변경은 제한된 충돌로 반환한다.

OFFSET 누적 페이지는 기본으로 쓰지 않는다. 조회 제한은 반환 행 수·bytes·deadline과 함께 강제하며, 제한에 걸린 후보를 없던 기록처럼 처리하지 않는다. 권한이 거부된 후보가 포함된 페이지의 결과 건수만으로 전체 허용 후보가 소진됐다고 단정하지 않는다.

## 원기록·출처·승인 지식

출처는 현재 투영만 따라가면 과거 답변이 가리킨 원문·판단 판본을 바꿔 버릴 수 있다. 발행 영수증의 불변 기록키/판본/본문 hash로 출처를 읽고 현재 문서 접근권한·원 판본/hash를 검증한다. 권한 변경을 원 hash 수정으로 통과시키지 않는다. 관련 원문을 현재 Gold에서 재검증하는 부분은 기존 소비자 책임을 유지한다.

Q09는 검색 후보 조회 틀이다. 기존 위키의 정확 후보 순위·교집합·승인/ACL 의미를 증명하지 않는다. 개인 경험/조직 공통 승인 자료를 나누어 기존 코드의 실제 소비 계약을 옮겨야 하며, 이 부분을 연결하지 않고 NFS 제거를 완료로 표시하지 않는다. Gold 지식 형식으로의 변환과 자동 승인은 이번 초안에 포함하지 않는다.

## 저장 transaction과의 관계

SELECT 예시에는 `INSERT/UPDATE/DELETE/COMMIT`이 없다. 기존 STATE의 단건 put을 여러 번 호출해 이 조회 투영을 맞추는 방식도 아니다. 새 adapter가 불변 기록·현재/IX 투영·RUN·STATE·operation 영수증을 같은 transaction에 저장해야 한다. 본문은 사전 등록한 검증된 완성본만 참조한다. 중간 상태를 성공으로 읽지 않는다.

실제 구현 종료 기준은 기존 SQLite 경로와 같은 업무 입력에서 원값/원 hash/판단 판본/권한/사건 순서/발행 결과를 대조하고, 같은 request·오래된 fence·부분 CLOB·응답 유실·프로세스 재시작을 확인하는 것이다. 이 문서의 SELECT 정적 파싱 통과를 그 시험 결과로 보고하지 않는다.
