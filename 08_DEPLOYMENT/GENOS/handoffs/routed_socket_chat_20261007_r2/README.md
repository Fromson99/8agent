# 통합 Socket.IO / 별도 Python 워크플로우 SSE 선택 R2

R1의 HTTP/Socket.IO 선택을 사용자가 요청한 실행 방식 선택으로 수정했다.
`GENOS_MAIN_MODE=workflow`는 기존 별도 Python 워크플로우의 `/stream` SSE 백엔드,
`integrated`는 같은 프로세스 RAG와 Socket.IO 토큰 전송을 선택한다.
기본값과 `existing` 호환 별칭은 `workflow`다. Run은 `python3 main_router.py`다.

GENOS 플랫폼의 채팅앱 대상과 소켓 옵션은 별도로 맞춘다. 서버 변수 하나로 플랫폼
워크플로우 정의까지 전환한다고 설명하지 않는다. 실제 GENOS 연결·배포는 미확인이다.

- [반입·모드별 플랫폼 설정·검증·원복](GUIDE_UTF8.txt)
- [296파일 누적 코드 ZIP](GENOS_ROUTED_SOCKET_CHAT_20261007_R2.zip)
- [적용·같은 checkout 검증·push·원복 실행 TXT](GENOS_ROUTED_SOCKET_CHAT_20261007_R2_APPLY.txt)
- [기존 별도 Python 단계 전체 TXT](GENOS_ROUTED_SOCKET_CHAT_20261007_R2_WORKFLOW_PASTE_ALL.txt)
- [선택적으로 새 Git 저장소에 push하는 TXT](GENOS_ROUTED_SOCKET_CHAT_20261007_R2_PUSH_NEW_REMOTE.txt)
- [파일 해시·정확한 선행 코드 허용 목록](CODE_MANIFEST.json)
- [코드·MAIN 44 기준·현장 미확인 상태](HANDOFF.json)

MAIN 44의 290파일 중 기존 시작 helper만 갱신한다. R1 소켓 코드를 잇고 독립
workflow 앱을 더했다. 원문·데이터·DB·키·JS는 포함하지 않는다.
R1 ZIP/TXT/발송 기록과 로컬 활성 포인터는 보존한다. 이번 수정본은 아직 메일을 발송하지 않았다.
