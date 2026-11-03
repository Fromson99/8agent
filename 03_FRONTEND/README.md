# 03_FRONTEND

운영·구조 검수·RAG·실험 UI를 둔다.

- `APPS/experiment-studio/`: Sites 기반 실험 스튜디오. 앱 ID는 npm 관례라 소문자다.
- `APPS/legal-knowledge-streamlit/`: Dataiku 지식 운영 콘솔. 설정된 온톨로지 관리/시뮬레이션은 공통 `ontology_console.py`를 통해 기존 승인 대시보드·자유 작업공간·도메인·시나리오 패널에 연결된다. 나머지 배치/구조화/숏컷/Legal Wiki 화면은 기존 시안 범위다. MAIN134와 결속한 별도 배포 묶음은 `08_DEPLOYMENT/DATAIKU/ontology_console_20261103_r1.zip`; 현장 반영은 별도다.
- `ASSETS/`: 여러 프런트엔드가 공유하는 정적 자산

백엔드에 포함된 서버 렌더링 뷰어는 `02_BACKEND/lawrag/api/viewer/`에 둔다.
