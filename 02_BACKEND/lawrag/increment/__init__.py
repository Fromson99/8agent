"""규정 문서 증분 처리 — 바뀐 조문만 새 판본으로 올린다.

흐름: 수집 → 입력 검증 → 구조화 → 기존 현행본 조회 → 조문 비교 → 게이트
→ 승인 → 색인 준비(숨김) → 활성화(한 트랜잭션) → 영향 전파.

입구(법제처 XML, 이후 내규 docx·HWP·PDF)가 달라도 `DocumentSnapshot`
형태로 맞추면 비교·승인·활성화는 같은 엔진을 탄다. 옛 조문 판본은
지우지 않고 시행 구간(ENFC_END_DT)을 닫는다.

모듈
- normalize: 공백·유니코드 정규화, 해시, 인용 번호 가리기
- lawgo_parse: 법제처 법령·행정규칙 XML → DocumentSnapshot
- addenda: 마지막 부칙에서 조문별 시행일 읽기
- diff: 계보 유지 조문 비교 (SAME/AMEND/MOVE/MOVE_AMEND/REF_ONLY/ADD/DELETE)
- gate: 변경률·강한 경고
- store: 테이블 정의와 SQL (Oracle·SQLite 같은 문장)
- service: 상태 전이와 단계 실행
- preview: 신구조문 대비표
- cli: 명령줄 진입점
"""
