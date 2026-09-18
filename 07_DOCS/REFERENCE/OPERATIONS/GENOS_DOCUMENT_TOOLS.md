# GENOS 문서 탐색 도구 반입 — 2026-09-17

사용자 요청은 용어집 재수집이 아니라 문서 목록·폴더·목차·원문과 여러 탐색 도구를 GENOS에 반영하는 것이다.
ADR-0457 portable rev-001 및 고정 부모의 필요한 구현을 유지보수 모듈로 복사해 기존 RAG에 연결했다.
출처와 해시는 `09_ARTIFACTS/AUDITS/20260917-genos-document-tools/source-lineage.json`에 보존한다.
제품은 연구 실행기·실험 폴더·정답 데이터·Gemini 클라이언트를 import하지 않는다.
기능 반입이며 품질 인증이나 실험 Accepted 판정이 아니다. 이 반입 자체는 로컬 ACTIVE_RELEASE와 GENOS CURRENT를 변경하지 않았다.
같은 날 사용자 지시로 로컬 MAIN도 이 모드로 전환했다(`document-navigation-rag-20260917-v1`). [로컬 배선 기록](../../../09_ARTIFACTS/AUDITS/20260917-document-navigation-main-wiring/README.md).
HTTP 매핑 요청의 응답은 "이번 요청 안에서만 확인했습니다. 저장되지 않으므로 다음 질문에서는 재사용되지 않습니다"로 안내한다.
2026-09-17 v2: 내용 질문의 후보는 질문 개념별로 모아 개념 적중 순으로 제시하고(컷 없음), 채택 근거가 있으면 모델의 `SYNTHESIZE` 또는 예산 임계에서 종합한다.
실제 규모 데이터에서 후보 전부 검토를 전제하던 이전 루프는 항상 실패했다. 큰 조문은 블록 단위로 이어 읽는다. [조사·수정 기록](../../../09_ARTIFACTS/AUDITS/20260917-document-navigation-main-wiring/README.md).

## 사용할 수 있는 기능

- 전체 문서 목록, 내규/외규/분류 미확인 구분, 폴더·문서 제목 검색, 폴더 트리.
- 선택 문서의 저장된 목차·조/항 구조 조회, 전체 원문 페이지 조회, 특정 구조 구간 원문 조회.
- 용어/정의/관계/명시 참조와 원문 검색, 복수 후보 일괄 읽기, 근거별 검토, 여러 조문 종합·검증.
- 같은 요청 안의 후보·읽은 원문·판단·도구 결과를 보존하고 다시 조회.

문서 목록과 제목 검색은 본문을 읽었다는 뜻이 아니다. 구조와 폴더는 저장된 세대의 메타데이터만 따른다.
현행 `document_metadata.relative_path/source_category`와 이전의 검증된 `origin`을 지원한다.
기록이 없는 과거 문서는 분류 미확인으로 남는다. 이름만으로 내규/외규를 추정하거나 현장 RAW를 자동 스캔하지 않는다.
현재 HTTP 요청에는 인증된 사용자/대화 ID가 없으므로 표현 매핑은 요청 안에서만 사용한다.
사용자별 영구 별칭 승인·대화 간 선택 문서 자동 유지 기능은 이번 HTTP 반입에 포함하지 않는다.
다음 요청의 문서 선택은 기존 `document_ids`로 전달한다.

## 코드 설치

`genos-document-tools-20260917-v1.zip`을 기존 물리 DEV 루트의 `TRANSFER`에 업로드한다.
실행 중인 구축/서빙 프로세스를 종료한 뒤 설치한다. 전체 실행 코드 교체 방식이므로 이전 부분 패치의 HEAD 일치는 요구하지 않는다.

```bash
cd -P ~/DEV
.venv/bin/python -m zipfile -e TRANSFER/genos-document-tools-20260917-v1.zip TRANSFER/document-tools-v1
.venv/bin/python TRANSFER/document-tools-v1/install.py --apply
```

기존 설치기가 `00_SYSTEM`, `02_BACKEND`, `06_TOOLS`를 통째로 백업하고 현재 유지보수 코드로 교체한다.
이 ZIP에는 현재 구조화·팀별 RAW 등 작업 코드도 포함된다. 누적 부분 패치와 섞지 않기 위한 전체 코드 스냅샷이다.
원문·완료 데이터 세대·사전·실제 `.env`·가상환경·Git 이력은 유지한다. 새 전처리기 서버 설치나 모델 설정 변경은 수행하지 않는다.
설치기는 표준 라이브러리만 사용하며 Python 3.11에서 설치 전 코드 문법을 검사한다.

## 탐색 모드와 데이터 선택

GENOS 코드스페이스의 실제 환경변수와 코드서빙 배포 환경에 다음 두 값을 설정한다.
기존 내부 모델 주소/서빙 ID/키는 그대로 사용한다. 아래 export는 현재 터미널에만 적용된다.

```bash
export SEMANTIC_LLM_BACKEND=genos
export GENOS_RAG_IMPLEMENTATION=document-navigation-v1
```

데이터는 기존 `GENOS_GENERATION` 또는 `GENOS_DATA_ROOT/generations/CURRENT.json`이 명시한 세대다.
`GENOS_GENERATION`이 CURRENT보다 우선한다. 새 모드로 로컬 ACTIVE_RELEASE를 우회해서 선택할 수는 없다.

```bash
.venv/bin/python -B 06_TOOLS/COMMANDS/genos_document_tools_check.py
```

이 명령은 설치 코드·엔진 해시, 환경 설정의 존재, 선택된 원문/색인/용어집·캐시 해시를 확인한다.
네트워크나 모델을 호출하지 않고 키 값을 출력하지 않는다. `ready: true`는 반입 자원 준비 확인이며 실제 내부 모델의 성공이나 답변 품질 인증이 아니다.

호환되는 `term-source-generation-v1` + navigation v2/v3 + glossary/cache가 있으면 **코드 업데이트만으로 같은 데이터를 재사용**한다.
이번 도구 때문에 용어집 1,793건을 먼저 재검토하거나 원문을 다시 구조화할 필요는 없다.
기존 데이터에 색인/용어 묶음이 없으면 그 경우에만 기존 `build-all`/`document-release` 경로로 새 서빙 세대를 준비한다.
[데이터 연결·구축·검증·활성화](GENOS_DOCUMENT_CONNECTIONS.md)를 따른다. 누락 파일을 기존 불변 세대에 임의로 추가하지 않는다.

## 실제 서빙 배포와 확인

코드스페이스 설치 후에도 플랫폼 코드서빙은 기존 리비전일 수 있다.
현장 내부 Git의 변경 파일을 검토하고 코드만 커밋/push한 뒤 그 커밋을 GENOS 코드서빙 리비전으로 배포한다.
코드서빙에 같은 환경 설정과 영속 데이터 경로를 지정하고 프로세스를 재시작한다.
[플랫폼 배포 계약](GENOS_CODE_SERVING_CURRENT.md)에 따라 서비스 루트의 `service(config, data)`를 사용한다.

게이트웨이의 기존 JSON 호출로 다음을 확인한다.

```json
{"API_TYPE":"HEALTH"}
```

응답의 `rag_mode`가 `document-navigation-v1`이고 `generation_id`가 선택한 현장 세대여야 한다.

```json
{"op":"call","method":"GET","path":"/v1/rag/documents","params":{"offset":0,"limit":100}}
```

```json
{"op":"call","method":"GET","path":"/v1/rag/document/outline","params":{"doc_id":"목록에서 받은 실제 문서 ID"}}
```

```json
{"op":"call","method":"GET","path":"/v1/rag/document/read","params":{"doc_id":"목록에서 받은 실제 문서 ID","offset":0,"limit":50}}
```

`next_offset`이 있으면 다음 페이지를 요청한다. 전체 원문을 한 번에 잘라서 전체를 보았다고 표시하지 않는다.
`read`에 `unit_id`를 넣으면 저장된 그 구조의 블록 구간만 조회한다. 이 세 API는 모델 호출이 없다.
`documents`는 `category`, `folder`, `title_query`도 받는다. 제목 검색 결과가 비어도 본문 검색으로 확대하지 않는다.

채팅은 기존 ELS_QUERY/워크플로우를 그대로 사용한다. 다음 호출부터는 GENOS 내부 모델을 실제로 호출한다.

```json
{"API_TYPE":"ELS_QUERY","question":"전체 문서 목록 보여줘"}
```

이어서 `금투협 폴더 트리 보여줘`, `문서명 목차 보여줘`, 실제 원문에 근거가 있는 질문을 확인한다.
문서 하나에 한정하려면 `document_ids: ["실제 ID"]`를 함께 보낸다.
여러 문서 답변은 `retrieval.term_agent.work_state`, `read_source_ids`, `selected_ids`, `answer.claims`로 확인한다.
실제 현장 모델의 JSON Schema 수용·응답 품질·지연은 현장 확인 전까지 미확인이다.

## 원복

기존 용어 탐색 루프로만 돌아가려면 배포 환경의 `GENOS_RAG_IMPLEMENTATION=navigation-loop-v1`로 변경하고 재시작한다.
파일까지 원복하려면 설치 출력의 백업 경로로 실행한다.

```bash
.venv/bin/python TRANSFER/document-tools-v1/install.py --rollback /설치출력의/백업경로
```

플랫폼 코드서빙을 새 리비전으로 배포했다면 이전 리비전도 다시 선택한다. 환경변수 변경은 파일 원복과 별도로 되돌린다.
데이터 포인터는 이번 설치로 바뀌지 않는다.

## 로컬 확인 범위

작은 모의 원문을 실제 생성기·용어 연결·색인·서빙 묶음으로 만든 뒤 HTTP 문서 목록/목차/원문,
모의 내부 provider의 질문 해석·복수 원문 읽기·종합·답변·피드백을 검사한다.
정상 페이지와 빈 제목 검색, 분류 미확인, 잘못된 ID, 문서 범위, 모델 없는 조회와 게이트웨이 배선을 포함한다.
기존 탐색·provider·관측 로그·코드 설치/반복/원복 회귀도 별도 검사한다.
GENOS 접속, 실제 내부 모델 호출, 원격 Git push, 플랫폼 배포는 이 외부 세션에서 수행하지 않았다.
