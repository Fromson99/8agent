# 기능별 구현 및 확인 범위

[결과 요약](README.md) · [실제 사례](EXAMPLES.md) · [운영 경로](OPERATIONS.md)

최신 코드는 ADR-0644의 동결 후보이며 활성 MAIN이 아니다. 모든 구현이 파일로 존재한다는 이유만으로 현장 완료로 처리하지 않는다.

| 설계 영역 | 구현·배선 | 실제 확인/제한 |
|---|---|---|
| P0 기준 고정 | 활성 MAIN·소스 세대·코드·정책·실험 lineage 고정 | 후보 자동 선택 없음, pointer 불변 확인 |
| P1 지속 기록 | 전 요청 intake, 멱등 키, 불변 이벤트, artifact, outbox | 분류 실패·재시도·프로세스 종료 후 원문 보존 |
| P2 사건·정정 | investigation/branch/issue, 세션 명시 연결, exact span, typed fact/CAS/복원/관계 철회 | 개인·팀·문서 범위 격리와 늦은 답변 차단 |
| P3 지식 구성 | 모델 segment 선택, units/claims/procedures/relations/checklists, exact source gate, 불량 주장 격리 | 실제6개 사례와 관련 사건2turn 수락 |
| P3 증분·연결 | 처리된 불변 기록 제외, bounded page/cursor, 명시 관련 사건 묶음, 이전 단위 비교·관계 제안 | 정정 후 이전 이벤트 제외, source/관계 변경 CAS, 늦은 trace 미소비 보존 |
| P4 조회·힌트 | 기존 memory/query 확장, exact lookup·현재 권한·source 검사, Markdown/JSON 투영 | projection 삭제·실패 후 재생성; DB가 정본 |
| P5 절차·판단 | 승인된 read-only catalogue, typed argument/DAG, 3값 조건, SOURCE/INTERPRETATION receipt | 실제 native 절차/판단 재결속은 scripted 계약으로 검사; 실제 법률 재사용 품질 인증 아님 |
| P6 운영 | 기존 action-memory/unified-memory CLI, 야간 창·lock·예산·lease·retry3·격리 | 야간 실제 운영·내부 모델은 미확인 |
| 이행 | v3/native/action/query/corrected archive, 원 ID mapping, delta, 제거 사실 미확인 revision, 명시 외부 artifact hash 이행 | 원본 보존·native trace 조회·scope·멱등 검사 |
| 복구 | DB+artifact 백업, 새 세대 복원, reconcile, 해시 고정 전환/롤백 계획 | 실제 child process 종료·동시 동일 수신·복원6개 검사 |
| 검토 | 별도 운영자 검토 파일, 명시 import, target revision/hash 및 SOURCE 선행 검사 | 일반 사용자 명령에서 검증 위조 불가; 실제 전문가 검토 receipt 미등록 |
| 보존 | 승인 정책 입력, 원문/artifact/trace/import/명시 백업 연결 목록 | 기간·보존 의무·삭제 승인 미제공; 파괴적 삭제 미실행 |
| MAIN/GENOS | 후보에서 기존 실행 진입점에 연결 | 품질/지연/비용 미통과로 MAIN 미승격, GENOS 미배포 |

기능 flags는 capture/compile/hint/procedure/judgment를 분리한다. 후보의 flags 활성화와 운영 MAIN 활성화는 다르다. 외부 효과 도구·임의 저장 문자열 실행·자동 법률 승인·범위 확대는 허용하지 않는다.

100개 검사와 실제 모델 결과는 유한한 확인 범위다. 전체 장애 경계·장기 부하·실제 개인정보 보존·다중 호스트 운영을 인증하지 않는다.
