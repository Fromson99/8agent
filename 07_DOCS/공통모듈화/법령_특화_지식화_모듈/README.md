# 법령 특화 지식화 모듈

기존 구조화·검색 색인·Oracle 적재·벡터 게시 파이프라인을 하나의 관리 단위로 묶는 API 명세다. 현재 `feature/legal_RAG` 브랜치를 읽는 개발자를 대상으로 한다. 코드 사본과 배포 패키지는 포함하지 않는다.

- [API 명세서 Word](법령_특화_지식화_모듈_API_명세서.docx): 입력·출력, 단계, 통합 API, 기존 GENOS 프로토콜, 오류·재개·취소, 저장 계약.
- [코드 읽기 가이드 Word](코드_읽기_가이드.docx): 현재 브랜치에서 볼 경로·함수·순서와 전달본 차이.
- [API 명세서 HTML](API_명세서.html): 목차와 검색을 지원하는 브라우저 열람본.
- [코드 읽기 가이드 HTML](코드_읽기_가이드.html): 브라우저 열람본.
- [API 명세 원본](법령_특화_지식화_모듈_API_명세서.md), [코드 안내 원본](CODE_READING_GUIDE.md).
- [OpenAPI YAML](openapi.yaml), [입출력 예제](examples/raw_request.json), [코드 위치 명세](SOURCE_MAP.json), [검증 기록](VALIDATION.json).

기존 내부 함수·GENOS API는 구현 근거이고, `/v1/legal-knowledge/builds`는 신규 통합 어댑터의 설계다. 첫 프로필은 native R10과 2테이블 벡터 경로다. PDF skip·부분 성공과 검색 채널/벡터 게시본의 활성 상태를 구분한다. 이 문서 작성으로 pipeline·DB·MAIN·현장 배포를 변경하지 않았다.

API 문서는 [OpenAPI 3.1.0](https://spec.openapis.org/oas/v3.1.0.html) 형식이다. 모든 examples는 합성 값이며 실측·실행 완료 기록이 아니다. Word/HTML/Markdown의 문서 간 링크는 같은 폴더를 기준으로 한다. 코드 링크는 이 저장소의 기존 파일을 가리킨다.
