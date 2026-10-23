# DB 조회 인덱스와 거래금액 사례

[전체 목차](../../../ARCHITECTURE/ONTOLOGY_V3.md) · [DB 목차](../DATABASE_ARCHITECTURE.md)

원래 논의의 절 번호를 유지했습니다. 설계 제안과 구현·검증 상태는 각 절의 구분을 따릅니다.

<a id="db-8"></a>

## 8. 대표 조회와 인덱스

실제 바인드 SQL은 [READ_QUERIES.sql](READ_QUERIES.sql)에 있다. 이는 adapter 내부 조회 골격이며 공개 API나 권한 검사의 완성 구현이 아니다.

| 목적 | 시작 키·경로 | 제안 인덱스·반환 |
|---|---|---|
| 최초 조문 진입 | 질문에서 기존 검색이 얻은 term ID·source anchor → LK_ENTRY | release+key 종류+hash; 제한된 후보·근거 위치 |
| 산정 근거 추가 확보 | 현재 판단의 NEED_ROLE + 같은 source binding → ENTRY/ROUTE_STEP/EVIDENCE | 역할 적중 후 scope·조건·현재 통제 확인 |
| 검토 이력 | object_id + revision → LK_REVIEW → LK_RECORD | 대상 버전+기록 시각 |
| 의미 관계 탐색 | subject_ref 또는 target_ref + 허용 predicate | 양방향 간선 인덱스; 조건 포함 후보 경로 |
| 변경 영향 | 바뀐 REF → DEPENDENCY → 소비 지식/주장 | target_ref 인덱스; 주장→run/발행 receipt |
| 동일 문서 계열 개정 | tenant+kind+family_key_hash → 관련 REF | 판본을 합치지 않고 이전/신규 참조와 대응 기록 조회 |

키셋 페이지와 호출별 행·시간·깊이 예산을 사용한다. 세부 수치는 현장 데이터 분포와 허용 지연을 측정한 뒤 설정하며 이번 문서에서 처리량을 예측하지 않는다.

그래프는 전체 전이 폐쇄를 미리 만들지 않는다. 목적·predicate·범위·기준일을 제한하여 앞뒤 간선을 작은 묶음으로 탐색하고 방문한 ref/관계 버전 집합으로 순환을 막는다. B→C→A 발견 시 각 관계의 원문·조건을 검증하고 현재 사안의 적용성은 LLM 의견으로 기록한다. 새로운 합성 관계를 저장하려면 M03 후보로 등록하여 검토한다.

<a id="db-9"></a>

## 9. 거래금액 예시의 실제 저장 흐름

다음은 가상 규정·가상 사건이며 실제 법률 판단이나 관측 결과가 아니다.

1. 기존 원문 저장소에 ‘같은 거래의 계약 합산’ 근거와 ‘10억 원 이상 승인’ 근거가 있다. 각각의 정확한 판본·span을 `LK_REF`에 연결한다.
2. `K-AGG`는 합산 판단 관계, `K-AMOUNT-CHECK`는 금액 기준 판단의 필수 검토 항목, `K-AMOUNT-ROUTE`는 산정 근거 위치를 가진 경로다. 각각 독립 object_id와 revision을 갖는다.
3. K-AMOUNT-CHECK의 조건·필요 역할은 knowledge payload에, 적용 대상과 해결 경로 연결은 LK_EDGE에 둔다. K-AMOUNT-ROUTE의 위치는 LK_ROUTE_STEP에 둔다.
4. 담당자가 K-AGG revision 2를 해당 범위에서 채택하면 LK_REVIEW와 control 원장을 추가한다. 게시 release는 그 정확한 버전을 선택한다.
5. 질문에서 금액 기준 판단이 발견되면 LK_ENTRY가 검토 항목을 제시한다. ‘합산 범위’가 부족하면 같은 필요 ID·현재 상태로 경로를 조회한다. 읽기 실패는 근거 부재로 저장하지 않는다.
6. 현재 두 계약 8억·4억은 기업 공통 지식에 저장하지 않고 사건 사실의 버전 참조로 남긴다.
7. ‘두 계약을 같은 거래로 본다’는 현재 적용 해석, ‘합계 12억’ 계산, ‘승인 필요’ 조건부 결론을 서로 다른 claim으로 기록한다.
8. LK_DEPENDENCY는 승인 claim → 합산 해석 claim·계산 claim·기준 원문, 계산 claim → 입력 사실 등을 연결한다.
9. 합산 관계를 철회하면 해당 버전을 사용하는 후속 자동 적용을 막고, 역의존으로 이전 판단을 재검토 후보로 찾는다. 8억+4억 계산 자체가 틀렸다고 자동 변경하지 않는다.

예시의 계산은 형식 조건이 표현되는 범위에서만 실행한다. 금액 단위·환산·반올림·평가일을 입력 계약으로 확인하며, 같은 거래인지의 해석을 SQL이 임의 확정하지 않는다.

---

[이전: DB 식별 버전 테이블과 ERD](MODEL.md) · [목차](../DATABASE_ARCHITECTURE.md) · [다음: DB 트랜잭션 철회와 복구](TRANSACTIONS.md)
