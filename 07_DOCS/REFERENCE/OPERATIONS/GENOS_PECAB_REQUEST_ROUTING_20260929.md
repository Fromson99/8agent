# PeCab 통일과 요청 분류 검증 — 2026-09-29

후속 사용자 지시로 ADR0555 rev-002 제품 분기를 구조 우선 RAG와 병합하고 새 로컬 MAIN 릴리스를 선택한다.
ADR0555는 전송 전 오류로 중단되어 품질 결과가 없으며 동결 후보·실패 이력을 보존한다.
아래 활성 포인터·후보 격리 설명은 초기 작업 시점이다. [현재 통합 상태](RAG_USER_DIRECTED_MAIN_20260929.md).

사용자 요청은 법률 내용 검색, 허용 자료의 목록·제목·목차 탐색, 인사·역할 안내,
비법률 질문의 서비스 범위 안내다. 첫 모델 판단에서 행동을 정하며, 문서 추천은
실제 목록과 목차를 관찰한 뒤 한다. 검색어가 없다는 이유만으로 빈 답변을 발행하지 않는다.

현재 작업 코드의 형태소 분석은 `pecab==1.0.8`이다. fulltext 구축·질의와 원문 용어
후보 추출이 같은 분석기를 사용한다. PeCab fulltext의 계약은 `semantic-fulltext-v2`다.
이전 Kiwi 색인은 바이트와 이력을 보존하지만 새 서비스 진입점에서 실행하지 않는다.
형태소를 사용하지 않는 원문, 승인 용어 라벨, literal occurrence, 정의·명시 참조는 보존한다.

## 실제 연결 상태

- `service.application`은 선택된 fulltext의 PeCab v2 계약을 frozen runtime import 전에 확인한다.
- `genos_fulltext_repair.py --rebuild`는 원본 세대를 검증하고 새 세대의 fulltext만 다시 만든다.
- 로컬 재구축은 반출이 승인된 공개 145문서만 처리한다. 포함되지 않은 문서 검색은 오류다.
- GENOS에서는 같은 생성기에 문서 범위 옵션을 지정하지 않아 실제 내규까지 현장에서 처리한다.
- `ProgressCapture`의 `REQUEST_ROUTED`가 workflow `_ChatProgress.progress`로 전달되어 판단과
  짧은 사유를 표시한다. 문서 목록의 기존 모델 미사용 경로도 `BROWSE` 판단을 기록한다.
- 최상위 네 가지 모드 후보는 ADR0555의 frozen candidate다. 작업 코드의 기존 두 방향
  판단과 같은 PeCab 세대·모델·예산으로 비교하며 운영 registry에서 자동 선택하지 않는다.

이 문서 작성 시 로컬 활성 포인터는 `legal-agent-navigation-storage-20260929-r3`다.
해당 frozen 릴리스와 세대에는 Kiwi 코드·색인이 있어 새 서비스에서 실행이 거부된다.
포인터를 고치거나 과거 frozen 파일을 덮어써서 검증을 우회하지 않는다.
새 릴리스 준비·MAIN 승격과 GENOS 현장 적용은 각각 별도 상태다.

## 실험과 근거

[ADR0555](../../../04_EXPERIMENTS/ADR/ADR-0555-pecab-only-catalogue-routing/README.md)에
법률 핵심 8문항과 안내·현황·범위 밖 6문항, 동일 질문의 과거 결과, 사전 기준,
원문 전달 원장, 실제 모델 호출·사용량·시간을 둔다. Qwen3.8 27B Parasail FP8은
이 실험만의 사용자 승인 모델이며 공통 Gemma 기본과 GENOS 내부 모델 설정을 바꾸지 않는다.
과거 Qwen3.5/Kiwi 결과는 질문·원문을 대조하는 기록이고, 동일 조건의 주 비교는
두 PeCab arm의 새 실행이다. 내부 자료의 검색 품질과 현장 SSE는 GENOS에서 확인해야 한다.

## 현장 적용과 검증

[PeCab 세대 구축·검증](GENOS_PECAB_FULLTEXT_20260924.md)의 기존 `~/DEV` 적용 경로를 사용한다.
코드 ZIP은 현재 checkout에서 생성하고 백업을 남긴다. 정확한 새 generation을 E2E로
검증하고 commit 후 `genos_release_gate.py`로 ZIP·checkout·generation을 결속한다.
push한 커밋으로 새 코드서빙 리비전을 만들고 그 리비전에 동일한 `GENOS_GENERATION`을 지정한다.
workflow Python은 별도 편집기에 반영한다. 실제 질의는 workflow 테스트 화면에서만 한다.

복구는 이전 코드·검증된 generation 쌍으로 수행한다. 현재 정책에서는 Kiwi로 재실행할 수
없으므로 PeCab으로 검증한 쌍을 사용해야 한다. 이전 원본 파일은 감사·재구축 근거로 보존한다.
외부 Codex에서는 GENOS에 접근할 수 없어 ZIP 생성이나 로컬 검사 성공을 현장 성공으로 보고하지 않는다.
