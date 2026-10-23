# DB 코드 연결 이행과 검증

[전체 목차](../../../ARCHITECTURE/ONTOLOGY_V3.md) · [DB 목차](../DATABASE_ARCHITECTURE.md)

원래 논의의 절 번호를 유지했습니다. 설계 제안과 구현·검증 상태는 각 절의 구분을 따릅니다.

<a id="db-12"></a>

## 12. 기존 방식과 목표 비교

실제 사용자의 지연·정확도·영향 건수는 이번에 실행하지 않았다. ‘확인’은 코드 관측이며 결과가 없는 부분은 미관측이다.

| 같은 상황 | 기존 방식·확인 결과 | 변경 지점 | 원하는 결과·검사 |
|---|---|---|---|
| 다른 사건이 같은 관계를 발견 | 위키 ID에 사건·질문이 포함됨. 실제 중복량 미관측 | OBJECT/KREV + 경험 REF | 여러 출처가 명시적으로 동일 지식 ID를 참조; 임의 자동 병합 없음 |
| 산정 근거가 부족 | 경로·bounded 회수 존재, 관리 lookup은 INSTR 기반 | ENTRY/ROUTE_STEP + M07 find_evidence | 필요 역할과 같은 binding으로 직접 조회; 원문 전달 receipt 확인 |
| 관계 한 개 철회 | 관리 서비스는 채널 retire; basis는 개별 철회 구현 | REVIEW/CONTROL + M06/M08 | 해당 지식 버전만 신규 적용 제한, 기존 원문 조사 유지 |
| 무엇을 사용했는지 확인 | 현재 bridge 메타데이터는 제시 항목 중심 | USE/CLAIM/DEPENDENCY | 제시만 한 후보가 실제 사용으로 집계되지 않음 |
| B→C→A 연결 또는 원문 개정 | 현재 impact는 활성 release의 직접 의존 범위 | 양방향 EDGE + DEPENDENCY + SYNC | 간접 영향 경로와 확인 범위 표시; 새 연결은 검토 후보 |
| 원문 변경 중 장기 요청 | 원문 release pin·검증 기반 존재 | source+knowledge pin, control 재확인 | 판본 혼합 없이 재현하고 철회의 확정 시점 구분 |

같은 원인은 합산 외에도 정의 변경·적용 예외·담보 산식·내규 위임에서 나타날 수 있다. 예시 문구 전용 분기 대신 ref·role·scope·revision 계약으로 처리한다.

<a id="db-13"></a>

## 13. 코드 변경 지도

| 구현 단위 | 기존 진입·파일 | DB 연결 변경 |
|---|---|---|
| M03 후보 생성 | legal_wiki_compiler.compile_snapshots, action-memory build | 경험 참조에서 knowledge 후보 생성. 성공·실패 기록과 의미 채택 구분 |
| M04/M05 모델·원장 | legal_knowledge/contracts.py, adapters/repository.py | 새 namespace·형식 계약, OBJECT/KREV/REF/EDGE/EVIDENCE 작성·조회 |
| M06 검토·게시 | application.Service.command, adapters/oracle.py | 기존 operation·CAS 재사용, REVIEW/CONTROL/RELEASE/OUTBOX 동기 처리 |
| M07 조회 | Service.plan, planning.assemble | ENTRY 기반 호출, facts/as_of/scope 전달, 현재 control·원문 확인 |
| M08 적용 | knowledge_bridge, research_state, unified_publication | 기존 journal에 사건·주장 의존 결속, RUN/CLAIM/USE 투영 및 사용 확정 |
| M09 영향 | Service.impact, basis migration | REF의 판본 계열과 DEPENDENCY 역조회, SYNC coverage 표시 |
| M10 콘솔 | 기존 /v1/legal-knowledge와 관리 화면 | 같은 객체·검토·사용·영향 API 조회. 위키 파일 별도 승인 없음 |

현재 Oracle adapter는 `TABLES`가 세 테이블로 고정되어 있고 INSERT의 CLOB bind 위치도 기존 LK_RECORD에 맞춰져 있다. 테이블만 추가해서 연결이 끝나지 않는다. 확장 table map 버전, 타입별 bind, 새 repository 쿼리, 명령/응답 schema version, 기존 consumer 호환을 함께 변경해야 한다.

M11 실행 정책과 M12 조건 평가기는 별도 운영 DB를 만들지 않는다. 정책 버전·계산 입력/출력 receipt를 기존 지식·실행 계약에 연결한다. 이번 DDL이 2026-09 폐기된 의미 스키마를 되살리거나 현행 원문·term-runtime 계약을 교체하는 것은 아니다.

<a id="db-14"></a>

## 14. 단계별 이행·롤백

1. **계약·현장 목록 대조:** 기존 Oracle catalog·table map·PK/타입/권한·실행 저장소를 확인한다. 실제 현장 자료 전까지 물리 배치를 확정하지 않는다.
2. **추가 테이블과 adapter:** 기존 테이블 DROP/ALTER 없이 신규 구조를 준비한다. schema version과 단계별 DDL receipt를 기록한다. Oracle DDL은 암묵 commit이 있으므로 전체 DDL의 ROLLBACK을 복구 계획으로 쓰지 않는다. [Oracle 트랜잭션 문서](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html)
3. **명시적 변환:** 기존 definition·위키를 원문/경험 출처와 연결해 후보로 등록한다. 기존 PUBLISHED를 새 ADOPT로 바꾸지 않는다. `LK_RECORD(namespace='migration')`에 옛 ID/버전/hash → 새 ID/버전, 변환 코드/schema hash, 상태·실패를 보존한다.
4. **투영 구축·검토:** release별 관계·근거·진입 색인을 작은 배치로 구축한다. 사용 기록은 실제 존재하는 journal 사건만 투영한다. 과거 ‘제시’ 기록을 ‘사용’으로 소급 변환하지 않는다.
5. **소비 연결:** 기존 API와 import 호환을 유지하며 v3 요청에만 새 계약을 선택한다. 소비 전 검증, 동일 코드의 service/API 연결, 실패·재개·철회 검사를 수행한다. 품질 효과 비교는 별도 ADR로 동결한다.
6. **MAIN·현장:** 적격 검증 후 승격 도구와 활성 포인터·실제 로컬 서비스 binding을 확인한다. GENOS 반입·Oracle 접속·워크플로우·내부 모델 검증은 별도 단계다.

롤백은 새 reader를 끄고 확인된 이전 원문 조사 경로로 복귀한다. 새로 철회한 지식을 구 consumer가 다시 쓰게 만드는 rollback은 허용하지 않는다. 개별 철회를 읽지 못하는 구 reader라면 지식 소비를 off로 두어야 한다. 새 원장·이행 이력·실패·기존 원문을 삭제하지 않는다.

<a id="db-15"></a>

## 15. 자원·검증·남은 결정

전체 원문을 재임베딩하거나 그래프를 RAM에 올리는 것을 선행 조건으로 두지 않는다. ID·참조·작은 payload 중심으로 스트리밍 변환하고 무거운 작업은 하나씩 수행한다. 현재 로컬에 다른 모델 실험 프로세스가 있어 이번 작업은 소규모 파일 읽기·문서/DDL 정적 검사만 수행했다.

추가 저장량은 대략 **지식 버전 payload 합 + 참조/관계/근거 행 + 실행별 사용·의존 행 + 인덱스/DB overhead**다. 원문 전체의 추가 복제는 포함하지 않는다. 실제 행 크기·LOB 압축·인덱스 배율·실행량은 미측정이므로 GB·TPS·응답시간·일정을 제시하지 않는다.

동일 입력에서 후보 수·읽은 행/LOB bytes·DB 호출·지식 단계 지연·원문 도구 호출·중요 누락·검토 시간을 측정한다. 추가 검색·검토·관리 비용이 절감한 조사 비용보다 크면 효과가 악화될 수 있다. 지식 적중률을 오류 확률로 환산하지 않는다.

필수 검사는 다음과 같다.

- 원장/투영 hash 일치, FK·타입·키 계약, 같은 operation의 멱등성과 다른 입력 충돌.
- 같은 이름·다른 정의, unknown 효력일, 다중 판본·기간 경계·소급 정정.
- 교차 tenant·문서 권한, 비공개 근거를 경유한 제목·영향 건수 노출 방지.
- 게시 준비 중 실패, 원문 채널 선행 변경, 철회와 사용 확정의 경합.
- OFFERED/SELECTED/APPLIED/POSTHOC 구분, 부분 답변·실패·재작성 artifact 구분.
- outbox 중복·lease 만료·늦은 worker·기한 소진·journal 반영 지연·commit 결과 불명.
- 관계 순환·깊이 제한·미색인·권한 제한에서 완전한 영향 분석이라고 표시하지 않음.
- 같은 코드와 pin의 실제 API/service → 저장 → 답변/콘솔 연결. 현장 Oracle 19c에서 DDL·쿼리·CLOB·실행 계획·동시성 별도 확인.

이번 정적 검사 결과는 연결된 VALIDATION에 남긴다. Oracle DDL 실행, 실제 데이터 무결성·성능, 법률 의미 품질, 화면 렌더링, 독립 검토를 대신하지 않는다.

---

[이전: DB 트랜잭션 철회와 복구](TRANSACTIONS.md) · [목차](../DATABASE_ARCHITECTURE.md)
