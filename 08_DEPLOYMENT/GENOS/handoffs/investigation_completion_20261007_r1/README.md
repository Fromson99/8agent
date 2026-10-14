# GENOS 조사 완료 계약 R1

로컬 MAIN generation 44의 검증된 코드 268파일을 동일 바이트로 반입한다. 후속 루프 재설계는 포함하지 않는다. GENOS 현장 배포는 미확인이다.

- [안내서](GUIDE_UTF8.txt)
- [실행 경로 보충 안내 — 직접 통합 / 별도 워크플로우](GUIDE_CURRENT_ENTRY_R2.txt)
- [실제 질의 결과](EXPERIMENT_RESULTS_UTF8.txt)
- [반입 기록](HANDOFF.json)
- [검증 로그](DELIVERY_TESTS.log)

두 실행 경로를 모두 유지한다. 직접 `/chat`은 공통 엔진을 같은 프로세스에서 호출하고, 별도 Python 워크플로우는 기존 코드서빙 경로를 사용한다. 앞단 Socket.IO는 별도 작업이다.

전체 루프의 현재 문제·수정 설계·72개 상태 전이 시나리오는 [의사결정 트리 보고서](../../../../07_DOCS/REFERENCE/REPORTS/AGENT_DECISION_TREE_20261007/AGENT_DECISION_TREE_UTF8.txt)에 있다. 이 후속 설계는 본 ZIP에 구현된 내용이 아니다.
