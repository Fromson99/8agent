# GENOS 내규 PDF 입력 — 현장 버전 호환 수정본 v2

사진에서 확인한 세 파일의 SHA256이 genos-four-stage-20260910.zip과 모두 일치했습니다.
v1은 다른 코드 문맥을 기준으로 만들어 적용 검사가 실패했습니다. v2는 확인된
세 파일을 기준으로 만든 수정본입니다. 설치기는 세 파일과 payload 전체의 해시를
확인한 뒤 백업하고 적용합니다. 이미 적용된 경우 그대로 종료합니다.

## 적용

기존 문서 처리 프로세스가 실행 중이면 중단한 후 적용하세요.
첨부 ZIP을 GENOS의 `~/DEV/TRANSFER/`에 넣습니다. 아래 명령을 하나씩 실행합니다.

```bash
cd "$HOME/DEV"
.venv/bin/python -m zipfile -e TRANSFER/genos-internal-pdf-input-20260915-v2.zip TRANSFER
.venv/bin/python TRANSFER/genos-internal-pdf-input-20260915-v2/install.py --root "$PWD" --apply
```

`APPLY OK` 또는 `Already in requested state`가 나오면 적용된 상태입니다.
`STOP`이면 처리 실행으로 넘어가지 말고 해당 오류를 확인합니다.
`--apply`를 생략하면 코드 변경 없이 사전 검사만 합니다.
새 의존성 설치나 모델/키 설정 변경은 없습니다. 기존 파서·OCR 자산을 사용합니다.

## PDF 위치와 문서 처리 실행

내규 PDF는 `~/DEV/01_DATA/PDF/internal/` 아래에 넣습니다. 하위 폴더도 읽습니다.
대소문자를 구분하므로 `PDF`는 대문자입니다. 내규 ZIP·DOC·DOCX·XML은 이 입력에서
제외합니다. 기존 `RAW/internal` 원본은 보존합니다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id internal-pdf-002 --check-only
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id internal-pdf-002 --stage structure --execute
```

첫 명령에서 `ok: true`와 처리 대상 수를 확인한 뒤 두 번째 명령을 실행합니다.
`structure`는 현장 설치본의 문서 구조화까지만 실행합니다. 후속 LLM 의미 추출·검토와
벡터 구축, RAG 활성화는 실행하지 않습니다. 기존 RAW 외규 폴더가 있으면 외규도 함께
선택하며, 그 폴더의 기존 manifest 등록·해시 검증을 유지합니다. 외규 RAW가 없어도
내규 PDF만으로 입력 검사가 가능합니다. 내부 PDF 폴더 누락/빈 PDF는 오류입니다.

실행/재개: 같은 명령·설정·run-id로 다시 실행하면 유효한 기존 구조화 결과를 재사용합니다.
진행 로그: `01_DATA/LOGS/internal-pdf-002/progress.log`
입력 상세: 같은 폴더의 `inventory-*.json`, `detail.log`
실행 결과: 같은 폴더의 `result-*.json`
구조화 산출물: `01_DATA/STRUCTURE/<문서/설정 지문>/`

## 버전 범위

이 패키지는 확인된 3개 파일의 입력 경로와 입력 오류 반환, 출처 메타데이터만 수정합니다.
현장의 나머지 엔진·의존성 버전은 사진으로 확인하지 못했습니다.
최신 작업 코드의 VLM 검수·용어집 연결을 추가하는 전체 업그레이드는 아닙니다.
v1 안내에 있던 최신 VLM/용어 연결/HTML 상태표 설명은 이 현장 호환본에 적용하지 않습니다.
실제 내부 PDF 파싱 품질과 GENOS 실행 성공은 현장 실행 결과로 확인해야 합니다.

## 복구

설치 시 출력된 `BACKUP:` 경로가 원본 세 파일과 receipt의 보관 위치입니다.
다음의 `<BACKUP 경로>`를 실제 출력 경로로 바꿔 실행합니다.

```bash
.venv/bin/python TRANSFER/genos-internal-pdf-input-20260915-v2/install.py --root "$PWD" --rollback '<BACKUP 경로>'
```

복구는 백업·현재 코드의 해시를 먼저 검사합니다. 설치 후 별도로 수정한 코드가 있으면
중단합니다. 입력 원본·구조화 산출물·실행 로그는 삭제하지 않습니다.
