# GENOS 전체 실행 코드 교체 — 2026-09-16

사용자가 반복되는 부분 패치 충돌 대신 현재 로컬 작업 코드 전체로 교체를 요청했다.
대상은 코드스페이스의 물리 DEV 루트이며, 설치·현장 파싱 성공은 아직 미확인이다.

## 확인한 현장 상태

- 최신 전처리기 부분 패치의 기준 HEAD와 현장 HEAD가 달라 `base commit mismatch`로 중단됐다.
- Git status에 다수의 별도 반입 파이프라인 파일이 untracked로 표시됐다. Git HEAD만으로 설치본을 재현할 수 없다.
- 로컬 Docling 모델 초기화/다운로드 실패 로그가 있었다. 새 전처리기 경로로 실행됐다는 증거는 없다.
- 마지막 해시 명령은 `genos_stages.py`를 `genos-stages.py`로 입력해 해당 파일을 찾지 못했다. 파일 소실로 판단하지 않는다.

## 반입 범위

`code_ship.py`의 유지보수 실행 코드 허용목록을 사용한다. `00_SYSTEM`, `02_BACKEND`,
`06_TOOLS`를 디렉터리 단위로 백업 후 새 코드로 교체한다. 나머지 ZIP의 루트 파일·선택
문서·배포 설정은 파일 단위로 백업/교체한다. 미등록 예전 실행 모듈이 새 코드와 섞이지 않는다.
연구/실험 전체 저장소나 프런트엔드 개발환경은 이 실행 코드 패키지의 대상이 아니다.

`01_DATA`, `GENOS_DATA`, 실제 `.env`/키, `.venv`, `.git`, `TRANSFER`는 변경하지 않는다.
기존 코드 트리 안의 별도 파일은 통째로 백업에 보존된다. 실행 중인 파이프라인은 중단한 뒤 설치한다.
기존 소스 트리에 심볼릭 링크/특수 파일/별도 마운트가 있으면 자동 처리하지 않고 중단한다.
DEV 자체 링크는 `cd -P`로 물리 경로를 사용한다.

## 설치 — 기존 코드스페이스 터미널

메일 첨부 `genos-current-v2.zip`을 `~/DEV/TRANSFER`에 업로드한다.

```bash
cd -P ~/DEV &&
.venv/bin/python -m zipfile -e TRANSFER/genos-current-v2.zip TRANSFER/current-v2 &&
.venv/bin/python TRANSFER/current-v2/install.py --apply
```

`INSTALL OK`는 파일 교체·해시 확인 완료다. 의존성 설치·전처리기 배포·실제 PDF 처리·Git
커밋/push·MAIN/CURRENT/서비스 리비전 변경은 수행하지 않는다. 코드스페이스의 현재
환경변수는 보존되지만 새 프로세스에서 선택된 주소와 필수 설정을 확인해야 한다.

```bash
.venv/bin/python -B TRANSFER/current-v2/check.py
```

이 검사는 네트워크 없이 import·설정·공유 폴더·선택 용어집을 확인한다. 빠진 항목을 모두
표시한다. 전처리기 서버가 `data.document`를 반환하는지는 현장 실제 요청으로 별도 확인한다.
PDF 경로는 `GENOS_PDF_PARSER=preprocessor`, ID 또는 URL, REVISION, SHARED_ROOT가 필수다.
전처리기에는 `parser_processor`, `output.format: docling`, `enrichment: []`가 필요하다.
기존 187의 지원 여부는 미확인이다. 모델 ZIP은 이 경로에서 사용하지 않는다.

## 데이터·의존성과 새 실행

이번 ZIP은 코드 전용이다. 기존 RAW/PDF와 사전/지식 묶음은 현장에 유지한다.
설정이 선택하는 사전 또는 지식 묶음이 없는 경우 확인기가 알려준다. 코드 교체만으로
사전 데이터가 생성되지는 않는다. 이미 전달된 사전/지식 패키지는 **필요한 데이터 경로만**
반입하며 그 안의 예전 코드를 다시 덮어쓰지 않는다.

가상환경은 자동 변경하지 않는다. `requirements-pipeline.txt`는 로컬 검증 기준이며,
현장 Docling 2.126.0과 핀 버전 차이가 있다. 먼저 기존 환경에서 검사하고, 누락 의존성만
현장 패키지 저장소로 설치한다. pip로 모델 가중치가 준비됐다고 간주하지 않는다.

현행 엔진은 원문·용어 색인이다. 구 의미 추출/벡터 세대와 신규 세대를 혼합하지 않는다.
내규 PDF는 기존 `01_DATA/PDF/internal`, 외규는 `01_DATA/RAW/<source>`에서 선택한다.
기존 완료 결과를 보존하고 **새 run ID**로 DRAFT를 구축한다. 용어집 선택·연결과 구조
VLM 설정도 현재 코드의 계약을 사용하므로 현장 사전 검사 후 실행한다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id current-001 --check-only
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id current-001 --stage all --execute
```

## 복구

설치 출력의 `BACKUP/RECOVERY`가 복구 폴더다. 교체 도중 예외는 자동 원복한다.
프로세스 강제 종료/전원 중단 시 해당 폴더로 명시 복구한다.

```bash
.venv/bin/python TRANSFER/current-v2/install.py --rollback /설치출력의/복구폴더
```

설치 이후 코드가 바뀌었거나 백업 해시가 달라졌으면 덮어쓰지 않고 중단한다. Python이
자동 생성하는 __pycache__/pyc는 코드 변경으로 보지 않는다. 복구는 데이터 세대나
환경변수 변경을 되돌리지 않는다. 현장 코드서빙 배포를 별도로 했다면 그 리비전과
데이터 바인딩도 별도로 복구해야 한다.

## v1 설치 전 문법 검사 실패와 v2 수정

현장 Python 3.11에서 `f-string expression part cannot include a backslash`로 설치가
중단됐다. `02_BACKEND/lawrag/core/casereview/pipeline.py:1365`의 정규식 표현식이 원인이다.
패키지 검사 중이므로 해당 실행에서는 코드 백업/교체가 시작되지 않았다.

Python 3.14의 `ast.parse(feature_version=(3,11))` 검사만으로는 이 f-string 제한을
검출하지 못했다. v2는 문자열 가공을 f-string 밖으로 옮겨 출력은 보존하고, **실제
Python 3.11.15**로 패키지 전체 .py를 컴파일한다. 설치기 오류에도 전체 파일 경로를
표시한다. `code_ship.py verify --python <대상 Python>`으로 같은 검사를 재현할 수 있다.
기존 v1 ZIP과 영수증은 보존하며 새 v2에는 해당 수정만 반영한다.

## v2 현장 설치 성공 — 사용자 화면 확인

2026-09-16 사용자 화면 `134AFC6A-9BB8-4185-977A-572BAF3D21DA`에서
`INSTALL OK: genos-current-20260916-v2`, 설치 코드 798개 파일 검증 및 전처리기/
파서/단계 실행기/서비스 import 성공을 확인했다. 실행 위치 `/workspace`, Python
3.11.15다. 이는 코드스페이스 설치 확인이며 코드서빙 배포나 PDF 처리 성공이 아니다.

현재 터미널에는 `GENOS_PREPROCESSOR_REVISION`이 없고, 선택된
`01_DATA/LEXICON/glossary-v1/boundary-20260914-v3/dictionary.sqlite`도 없다.
리비전 검사에서 먼저 중단하므로 공유 폴더 접근 및 서버 계약은 아직 확인되지 않았다.
서비스 부팅 로그의 `llm_backend=anthropic`은 SEMANTIC_LLM_BACKEND 미설정 시 기본
표시이며 외부 모델 호출 증거는 아니다. GENOS 실행에는 `genos`를 명시해야 한다.
기존 반입 사전 위치/해시를 확인한 뒤 연결하며 임의의 사전을 자동 선택하지 않는다.
기존 전달 v2 ZIP/해시/설치 영수증은 이 기록 추가로 재작성하지 않는다.
