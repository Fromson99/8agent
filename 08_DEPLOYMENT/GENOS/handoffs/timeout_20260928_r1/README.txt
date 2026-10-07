GENOS timeout-sync-20260928-r1 — 현장 인계

현재 코드 전수 감사: BEFORE 996개 파일/94개 시간 설정 관련 파일. AFTER 1016개 파일/93개 관련 파일.
현재 요청 기본 예산 1800초, 워크플로우 json/stream과 GENOS 호출 도구 기본 대기 2100초.
DOC 변환 진단 기본 900초. embedding의 연결15/응답300초는 해당 호출의 개별 예산으로 보존.
워크플로우는 명시 환경값을 양쪽 HTTP 경로에 적용하고 WORKFLOW_SETTINGS/실패 분류/리비전 로그를 제공.
현재 프로필 해시와 엔진 코드 pin 갱신. 고정 과거 세대, 데이터 generation/CURRENT, 실제 .env는 변경하지 않음.

검증: 타임아웃/워크플로우/서비스/설치/관계 deadline/팀 선택/동시 요청/하네스 153 passed.
확대 검사에서는 116 passed와 실패6개가 있었으며, 예산 변경에 따른 deadline 테스트1개를 수정 후 위153개에 포함해 통과.
나머지5개는 기본 시간을 변경 전으로 되돌린 격리 복사본에서도 동일 원인으로 재현됨.
5개: 문서 이름 순위, navigation_match 테스트 단독 import, work 후보 순서, task max_actions 계약, 참조 적용 fulltext/navigation 결속.
이 실패들을 고쳤거나 전체 검색/참조 기능의 무결성을 인증했다는 의미는 아님.

사용 순서: ZIP+APPLY.txt 같은 폴더 → bash APPLY.txt(기존 ~/DEV 백업 적용) → 변경 검토/commit
→ MODE=verify GENOS_GENERATION=/실제/선택/generation bash APPLY.txt → 통과commit push/코드서빙 리비전 반영
→ WORKFLOW_PASTE_ALL.txt 전체 워크플로우 Python 단계 교체/배포 → 워크플로우 테스트 화면 WORKFLOW_SETTINGS
→ 코드서빙 runtime.request_budget=1800과 워크플로우 대기2100 확인 → 실제 질문.
코드서빙 환경: GENOS_RAG_WALL_SECONDS=1800. 워크플로우 환경: GENOS_CODESERVING_TIMEOUT_SECONDS=2100 한 항목만.
동일 질문/요청ID에서 HTTP500이300초에 다시 오면 응답 detail과 중계/서빙 로그가 필요.
바깥 code=0/success는 dict 반환 성공이며 data.answer_status=failed는 답변 실패임.

GENOS commit/push/generation hash/서빙 리비전/내부 모델 응답/300초500 해소는 아직 미확인.
로컬 모의 검증이며 외부 모델 호출/성능 비교 실험 없음.
고정G19 코드는 byte 검증으로 보존하며 알려진 Python3.11 비호환 과거 모듈의 실행은 인증하지 않음.
