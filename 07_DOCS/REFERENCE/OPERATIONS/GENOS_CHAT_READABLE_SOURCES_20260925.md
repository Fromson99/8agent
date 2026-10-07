# GENOS 채팅 출처 경로 노출 수정 인계

현장 사진에는 `출처` 목록이 `/v1/rag/source?...` 경로 네 줄로 보였다. 사진만으로
정확한 워크플로우 리비전을 식별할 수는 없지만, 현재 작업 코드가 만드는
`핵심/보완 · 문서명 · 위치` 형식과 다르다. 저장된 워크플로우 Python 단계가
이전 코드일 가능성이 있다.

## 검증한 인계 파일

- 붙여 넣을 전체 코드: `06_TOOLS/COMMANDS/GENOS_CHAT_READABLE_SOURCES_WORKFLOW_PASTE_ALL_20260925.txt`
- 동일한 저장소 파일: `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`
- 두 파일의 SHA-256: `d790ad10279838517f849eca56f49f83e9d93fbbdedf616aa2d2186da18cae0b`
- 로컬 코드 루트: `/home/jin/8-AGENT`; Python: `.venv/bin/python`
- 로컬 검사: `test_genos_rag_chat.py`와 `test_source_tiers_v4.py` 합계 51 PASS;
  붙여 넣기 파일 파싱과 모의 `개인정보 보호법 · 제16조` 표시 PASS

이번 변경은 워크플로우의 채팅 본문 렌더링에만 적용된다. 코드서빙의
`source_bundle.sources[].open_url`, 선택 원문 검증, 데이터 generation은 변경하지 않는다.
채팅 본문에는 실제 채택 출처의 문서명과 위치를 텍스트로 표시하고
`/v1/rag/source?...`를 쓰지 않는다.

## 현장 적용과 확인

1. 전체 코드 TXT를 기존 GENOS 워크플로우 Python 단계에 붙여 넣고 저장·배포한다.
   DEV checkout의 파일만 바꾸거나 코드서빙을 재배포해도 저장된 Python 단계는
   바뀌지 않는다.
2. 채팅 앱이 새 워크플로우 리비전을 선택하는지 확인한다.
3. **워크플로우 테스트 화면**에서 실제 근거 질문을 실행한다. `출처`에
   `핵심 · 문서명 · 조문 위치`가 보이고 `/v1/rag/source?` 문자열이 없으면
   채팅 표시 경로가 적용된 것이다. 원문 열람은 별도 인증 라우팅 확인이 필요하다.

현장 워크플로우 리비전, 코드서빙 커밋·리비전, 선택 generation 절대경로와
manifest SHA-256, 현장 질문 결과는 이 세션에서 확인할 수 없다. 이 변경을 위해
코드서빙이나 generation을 교체할 필요는 없지만, 기존 현장 코드가 동일한
`source_bundle` 문서명·위치 필드를 내보내는지는 테스트 화면 결과로 확인한다.
