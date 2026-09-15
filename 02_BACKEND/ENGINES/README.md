# 명시적으로 등록하는 엔진

`<name>/<version>/engine.json`에 포트·구현 파일 hash·종류·매개변수를 고정한다.
실제 선택은 `00_SYSTEM/PIPELINE.json`에서만 한다. 디렉터리 자동 탐색은 없다.
실험 후보는 `02_BACKEND/lawrag/research/candidates/`에 유지한다. 등록 manifest는
code snapshot을 대신하지 않으며 candidate/revision/ADR hash를 참조한다.
현재 semantic_contract는 TOOL이며 법적 정본/제품 답변 엔진이 아니다.
