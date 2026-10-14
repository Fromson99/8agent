# 기존 채팅 + 통합 Socket.IO 채팅 R1

로컬 MAIN generation 44의 누적 코드 290파일을 기반으로
`main_router.py`, `main_integrated.py`, Socket.IO 빌드 설정과 운영 문서를 더한
294파일 코드 ZIP이다. 기존 코드서빙은 유지하고, 새 코드서빙의 환경변수로
기존 HTTP `/chat` 또는 통합 Socket.IO `/chat`을 선택한다.

- [현장 실행 안내](GUIDE_UTF8.txt)
- [코드 ZIP](GENOS_ROUTED_SOCKET_CHAT_20261007_R1.zip)
- [적용·검증·원복 TXT](GENOS_ROUTED_SOCKET_CHAT_20261007_R1_APPLY.txt)
- [새 Git 저장소 별칭 등록·push TXT](GENOS_ROUTED_SOCKET_CHAT_20261007_R1_PUSH_NEW_REMOTE.txt)
- [코드별 해시와 선행 바이트](CODE_MANIFEST.json)
- [코드/기준 세대/현장 상태](HANDOFF.json)
- [로컬 검증과 모의 로그](VALIDATION.json)

로컬 실제 HTTP·Socket.IO 검사 4개, 기존 HTTP 경로 검사 7개,
ZIP 적용·재실행·원복·동일 checkout gate/로컬 Git push 검사 4개를 통과했다.
현장 GENOS의 소켓 경로·Authorization 전달·화면 렌더링은 확인하지 못했다.
설명은 [실행 경로와 입출력 계약](../../../../07_DOCS/REFERENCE/OPERATIONS/GENOS_ROUTED_SOCKET_CHAT_20261007.md)을 따른다.
이번 작업에서는 메일·현장 배포·로컬 활성 포인터 변경을 하지 않았다.
