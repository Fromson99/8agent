# 직접 통합 채팅과 SSE 반입 R1

별도 Python 워크플로우 없이 `/chat`에서 기존 RAG를 직접 실행한다.
승호 cicd `388cd392`의 `token → result.data.text` 계약에 맞춘 SSE를 추가했다.
같은 브랜치의 현장 SSE 실패 후 JSON 복귀 기록을 반영해 직접 JSON을 기본으로 둔다.
우리 GENOS 리비전의 SSE 수신·렌더링 성공은 아직 확인하지 않았다.

- [실행·연결·진단·원복 안내](GUIDE_UTF8.txt)
- [코드 ZIP](GENOS_NATIVE_CHAT_SSE_20261007_R1.zip)
- [현장 실행 TXT](GENOS_NATIVE_CHAT_SSE_20261007_R1_APPLY.txt)
- [코드/출처/현장 미확인 상태](HANDOFF.json)
- [파일별 해시](CODE_MANIFEST.json)
- [로컬 검증과 현장 미확인 범위](VALIDATION.json)

관련 계약 26개와 실제 반입 TXT 검사 4개가 통과했다. 로컬 HTTP 조기 답변·heartbeat·
JSON 복귀·기억/AD 인증·기존 RAG 정정/확정 경로를 확인했다. 반입 검사는 적용·재실행·
정확한 원복·데이터 보존·미확인 수정 차단·같은 checkout gate와 로컬 Git push를 확인했다.
내부 모델 호출과 GENOS 현장 실행은 하지 않았다.

조사 제어 R4를 기준으로 현재 작업판의 전송 3파일·엔진 10개/pipeline pin과
기존 작업에서 갱신된 NFS 데이터 ZIP 도구를 같은 바이트로 싣는 287파일 누적본이다.
선택된 로컬 MAIN generation43은 이 반입본의 기준이며, 새 반입본과 같은 코드라고 주장하지 않는다.
원문/DB/CURRENT를 바꾸지 않고 기본 기존 `~/DEV`에 적용한다.
현장 Git push·리비전 배포·채팅앱 연결은 별도 단계다. 메일은 발송하지 않았다.
