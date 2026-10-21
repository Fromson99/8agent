# 03_FRONTEND

운영·구조 검수·RAG·실험 UI를 둔다.

- `APPS/experiment-studio/`: Sites 기반 실험 스튜디오. 앱 ID는 npm 관례라 소문자다.
- `APPS/legal-knowledge-streamlit/`: Dataiku용 지식 운영 콘솔 시안. 배치 모니터·구조화 누락 승인·숏컷 승인·Legal Wiki·온톨로지 관리·시뮬레이션의 6화면이다. `app.py` 단일 파일, `DESIGN.txt`에 실행·연결 범위를 정리했다. 운영 API는 미연결이며 기존 Oracle 읽기 전용 조회 예시를 포함한다.
- `ASSETS/`: 여러 프런트엔드가 공유하는 정적 자산

백엔드에 포함된 서버 렌더링 뷰어는 `02_BACKEND/lawrag/api/viewer/`에 둔다.
