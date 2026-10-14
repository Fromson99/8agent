# GENOS 검색 준비 최적화·세부 계측 R3

현장 사진의 RECALL 약 141초, SELECT 준비 약 190초 공백을 분해하기 위한
누적 코드 ZIP이다. 마지막 발송본 `GENOS_NO_SOCKET_CHAT_20261007_R3`를
포함하며, **이번에는 `GENOS_QUERY_LATENCY_20261007_R3` ZIP/TXT를 사용한다.**
미발송 계측 R1/R2는 검사·기준 갱신 기록으로 보존한다. 최신 session-runtime MAIN45를 결속한 R3를 사용한다.

반복 원문 JSON 조회를 source ID 조회로 바꾸고, 요청별 FTS 적중 메타데이터를
재사용한다. 캐시 상한 초과 시 기존 전체 검색으로 돌아간다. 순위·건수·페이지·권한·
원문 읽기·근거·재개 계약을 보존한다. SQL 실행/읽기, 후보 구성, 원문 검증,
상태 저장, 모델 요청 구성/예약/transport를 INFO 로그에서 각각 측정한다.

- [현장 실행 안내](GUIDE_UTF8.txt)
- [누적 코드 ZIP](GENOS_QUERY_LATENCY_20261007_R3.zip)
- [백업·적용·검증·원복 실행 TXT](GENOS_QUERY_LATENCY_20261007_R3_APPLY.txt)
- [요청 로그 요약 Python TXT](GENOS_QUERY_LATENCY_20261007_R3_SUMMARIZE.txt)
- [분리 workflow Python 단계 전체 TXT](GENOS_QUERY_LATENCY_20261007_R3_WORKFLOW_PASTE_ALL.txt)
- [별도 원격 저장소 push TXT](GENOS_QUERY_LATENCY_20261007_R3_PUSH_NEW_REMOTE.txt)
- [검증 결과와 기존 실패 구분](VALIDATION.json)
- [코드 inventory](CODE_MANIFEST.json), [인계 결속](HANDOFF.json)
- [원인 근거·캐시 경계·계측 의미](../../../../07_DOCS/REFERENCE/OPERATIONS/GENOS_QUERY_LATENCY_20261007_R1.md)

로컬 MAIN 포인터 generation45는 변경하지 않았다. 기존 데이터 generation과
glossary cache를 다시 구축하지 않는다. GENOS 적용·push·리비전 배포·workflow
질의 및 속도 개선 정도는 현장 확인 전까지 미확인이다.
