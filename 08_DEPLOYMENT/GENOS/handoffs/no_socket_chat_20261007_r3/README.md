# 통합 직접 JSON / 분리 워크플로우 SSE R3

사용자 보고에 따른 현장 R2 `apply` 상태를 입력으로 받는 누적 코드 ZIP이다.
`GENOS_MAIN_MODE=integrated`는 기존 `main.py`의 직접 `/chat` JSON,
`workflow`는 별도 Python `run(data)`가 `/stream` HTTP SSE를 읽는 방식이다.
새 Socket.IO 서버·의존성을 사용하지 않으며, R3 워크플로우 단계의 플랫폼
`main_socketio` 송신도 비활성화했다. 기존 R2 백업과 데이터 generation은 보존한다.

- [현장 실행 안내](GUIDE_UTF8.txt)
- [297파일 누적 ZIP](GENOS_NO_SOCKET_CHAT_20261007_R3.zip)
- [해시 검사·적용·검증·원복 TXT](GENOS_NO_SOCKET_CHAT_20261007_R3_APPLY.txt)
- [분리 워크플로우 Python 단계 전체 TXT](GENOS_NO_SOCKET_CHAT_20261007_R3_WORKFLOW_PASTE_ALL.txt)
- [별도 Git 원격 push TXT](GENOS_NO_SOCKET_CHAT_20261007_R3_PUSH_NEW_REMOTE.txt)
- [코드 해시/허용 선행 상태](CODE_MANIFEST.json)
- [선택 MAIN·현장 상태](HANDOFF.json)
- [입출력·모드 계약](../../../../07_DOCS/REFERENCE/OPERATIONS/GENOS_NO_SOCKET_CHAT_MODES_20261007_R3.md)

현장 R2 적용 해시·NFS generation 경로는 확인되지 않았다. R3 `check`가
통과할 때만 `apply`한다. 플랫폼 리비전·채팅앱 연결은 별도 단계다.
