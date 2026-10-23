# DB 트랜잭션 철회와 복구

[전체 목차](../../../ARCHITECTURE/ONTOLOGY_V3.md) · [DB 목차](../DATABASE_ARCHITECTURE.md)

원래 논의의 절 번호를 유지했습니다. 설계 제안과 구현·검증 상태는 각 절의 구분을 따릅니다.

<a id="db-10"></a>

## 10. 트랜잭션·철회·재개

### 지식 수정·검토 명령

기존 command의 operation ID와 입력 hash를 유지한다. 같은 ID·같은 입력은 기존 receipt를 반환하고, 같은 ID의 다른 입력은 충돌이다.

한 Oracle 트랜잭션에서 권한·기대 revision 확인 → 불변 LK_RECORD 추가 → 관련 동기 투영 → LK_HEAD CAS → 필요 outbox → operation receipt를 확정한다. 모델 호출·원문 대량 읽기·네트워크 대기를 이 잠금 안에서 수행하지 않는다. 실제 서비스에서 순서를 더 좁혀야 한다.

Oracle adapter의 SERIALIZABLE/CAS를 출발점으로 삼되 ORA-08177·동시 수정은 성공으로 삼지 않는다. 기존 담당 명령 계층에서 같은 operation의 결과를 확인하고 최초 기한·시도 예산을 보존한다. 무조건 자동 재시도를 추가하지 않는다. [Oracle 동시성 문서](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html)

### 게시와 원문 개정

게시 준비에서는 지식·근거·조건·검토 범위·전체 release 항목·인덱스 hash를 확인한다. 활성화는 기존 channel CAS로 한다. 새 초안 작성만으로 이전 게시 지식이 교체되지 않는다.

초기 v3 소비는 source query release와 knowledge release의 source binding이 일치할 때만 허용한다. 원문 채널이 먼저 바뀌면 새 지식 묶음의 대응 검토가 끝날 때까지 기존 허용 원문 조사로 처리하고, 구 지식을 새 판본에 적용했다고 표시하지 않는다. 원문 채널과 지식 채널이 서로 다른 adapter에 있을 때 두 변경을 하나의 DB 트랜잭션으로 가장하지 않는다.

관계 개정의 위치 대응과 법률 의미 유지 판단도 분리한다. basis migration이 좌표를 찾았다는 것만으로 새 지식 revision을 자동 승인하지 않는다.

### 현재 사용 중단과 진행 중 답변

LK_SCOPE_GATE는 tenant/scope별 짧은 사용 확정 경계다. 철회 명령과 M08의 사용 확정은 같은 gate 행을 잠그고 현재 control을 확인한다. 철회는 control 원장·투영·epoch·outbox를 같은 트랜잭션에서 갱신한다. 여러 scope가 있으면 정렬된 같은 순서로 잠그고 범위를 제한한다.

M08은 정확한 사용 버전·gate epoch·source/permission 검증 시점으로 **사용 확정 receipt**를 기존 operation/원장 계약에 추가하는 방향이다. 현재 구현된 receipt라고 설명하지 않는다. 관계 철회 이전에 확정된 사용과 이후 거절된 사용의 순서를 구분한다.

외부 실행 journal·답변 스트림과 Oracle receipt는 하나의 commit이 아니다. journal 기록이 실패하면 발행 완료로 표시하지 않고 같은 receipt·답변 artifact로 복구한다. 철회가 이미 전달된 문장을 회수할 수는 없다. 사용 확정 이후 철회는 영향 분석·재검토 대상으로 남긴다. 외부 문서 권한 변경도 재확인 시점을 명시하며 전송 시점까지의 전역 원자성을 주장하지 않는다.

### 비동기 투영과 누락

LK_OUTBOX는 지식 명령과 같은 DB 트랜잭션에서 enqueue한다. 외부 journal은 동일 이벤트 ID·hash를 보존한 기존 후처리 경로에서 읽는다. 두 저장소에 먼저 쓴 뒤 모두 성공했다고 가정하지 않는다.

worker는 lease owner·lease epoch를 조건으로 갱신하고, 만료 뒤 되살아난 이전 worker의 완료 기록을 거절한다. dedup 키·입력 hash·최초 deadline·누적 attempts를 유지한다. 적용 책임은 후처리 한 곳으로 두고 영구 실패를 무한 재시도하지 않는다.

**가장 큰 sequence나 최신 timestamp를 읽었다는 이유로 완전한 처리를 선언하지 않는다.** LK_SYNC에는 확인한 생산자/partition 목록, 입력 cut, 연속 처리 위치, 건너뛴 사건·실패·미반영 범위를 기록한다. ImpactReport는 그 범위 안의 COMPLETE/PARTIAL/UNKNOWN을 표시한다.

<a id="db-11"></a>

## 11. DB와 애플리케이션이 각각 보장할 것

| 검사 | DB 제약 | 서비스·adapter 책임 |
|---|---|---|
| 존재하는 지식 버전·내부 주장 연결 | PK/FK·nullable 배타 CHECK | payload와 행 키/hash 일치 |
| 후보·관계·경로 타입 | OBJECT_KIND enum | EDGE는 RELATION, ROUTE_STEP은 EVIDENCE_ROUTE 등 타입 간 계약 |
| 검토와 사용 허용 | 검토 FK, ENABLED에 review 필수 | 같은 대상 revision·scope·정책의 ADOPT인지 확인; 충돌 처리 |
| tenant·문서 권한 | 소유 키와 조회 조건 | 연결된 모든 ref의 최신 권한 검사. FK 존재를 접근권한으로 해석하지 않음 |
| 원문 현재성 | 고정 ref/hash 저장 | 원문 포트의 실제 span·판본·개정 대응 검증 |
| 의미 지지·적용 | 상태 저장 가능 | LLM/사람의 근거 있는 의견. DB가 참·거짓을 자동 확정하지 않음 |
| 불변성 | 원장 INSERT와 CAS head 구조 | 직접 UPDATE/DELETE 권한 제한, hash 재검증, 이행 도구 통제 |
| 재개·중복 | UNIQUE·CAS·lease epoch | 동일 입력·예산·deadline·완료 receipt 보존 |
| 조회 완전성 | coverage 기록 | 미색인·권한 제한·미발행·미완료 상태를 숨기지 않음 |

DDL은 내부 FK를 제공하지만 tenant가 다른 두 유효 ID를 잘못 연결하는 모든 경우를 막지는 못한다. command의 교차 참조 검증과 조회 시 scope 필터를 필수 계약으로 둔다. 이 경계의 계약·실제 API 검증 전에는 쓰기를 활성화하지 않는다.

---

[이전: DB 조회 인덱스와 거래금액 사례](QUERIES.md) · [목차](../DATABASE_ARCHITECTURE.md) · [다음: DB 코드 연결 이행과 검증](MIGRATION.md)
