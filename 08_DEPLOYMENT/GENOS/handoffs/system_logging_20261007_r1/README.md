# GENOS 배포·환경·일반 로그 NFS 저장 R1

배포 명령 시작부터 stdout/stderr, 환경·의존성 오류, 전체 traceback,
HTTP 일반 로그와 별도 Python 워크플로우 오류를 NFS에 기록하는 반입본이다.
기존 query-latency R3·MAIN45 서빙 코드를 보존한 304파일 누적 ZIP이다.

- [현장 실행 안내](GUIDE_UTF8.txt)
- [304파일 코드 ZIP](GENOS_SYSTEM_LOGGING_20261007_R1.zip)
- [로그 수집을 내장한 check/apply/verify/gate/push/rollback TXT](GENOS_SYSTEM_LOGGING_20261007_R1_APPLY.txt)
- [별도 Python 워크플로우 전체 TXT](GENOS_SYSTEM_LOGGING_20261007_R1_WORKFLOW_PASTE_ALL.txt)
- [기록 범위·원문·NFS 실패·복구 계약](../../../../07_DOCS/REFERENCE/OPERATIONS/GENOS_SYSTEM_LOGGING_20261007.md)
- [코드 inventory](CODE_MANIFEST.json), [현장 상태와 선택 MAIN 결속](HANDOFF.json), [검증 결과](VALIDATION.json)

기본 경로는 `/nfs-root/diamo/8-agent/logs/system/<run_id>/`다.
NFS 불통이면 임시 로컬 pending을 남기고 복구할 수 있다.
우리 프로세스 실행 이전의 플랫폼 자체 오류는 플랫폼 로그를 별도로 내보내야 한다.

로컬 작업 코드와 합성 반입 검증이다. GENOS 적용·Git push·새 리비전 배포·
실제 NFS mount/쓰기·workflow 화면 테스트는 미확인이다. 메일은 발송하지 않았다.
로컬 MAIN generation45와 데이터 CURRENT를 변경하지 않았다.
