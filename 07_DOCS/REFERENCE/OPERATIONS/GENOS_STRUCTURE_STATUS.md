# GENOS 구조 점수 비차단·태그 확인·문서별 상태표

이 변경은 오프라인 DRAFT 적재에만 적용합니다. 서비스/CURRENT, 원문, 키, URL, LLM 스키마를 변경하지 않습니다.
전체 성공 여부는 GENOS에서 새 코드를 적용한 뒤 확인해야 합니다. 로컬 합성 테스트는 실제 문서 정확도나 전수 통과율이 아닙니다.

## 변경 내용

- 휴리스틱 점수만 낮다는 이유로 구조화 문서를 탈락시키지 않습니다. 원래 `fitness.passed=false`와 점수는 그대로 보존하고, `meta.json`의 `structure_admission`에 별도 구조 무결성 판정을 기록합니다.
- 등록 태그 경로, 배치 수용, source SQLite 작성의 세 점수 차단을 분리합니다. 일반 publisher/운영 router의 기존 정책은 바꾸지 않습니다.
- 원문 해시·문서 ID·본문/마디·부모 연결·블록 좌표·원문 누락 검사는 유지합니다. 빈 본문, DRM/손상, 실제 구조가 없는 파일을 가짜 성공 처리하지 않습니다.
- 신규 구조화와 저장된 구조화 재사용을 구분합니다. 시간은 소수점 1자리, 파일 확장자는 긴 이름에도 표시합니다.
- 파싱/구조화 → SQLite·LLM 작업 준비 → 저장/해시 검증의 현재 작업을 한 줄로 안내합니다. 이 단계에는 LLM 호출이 없습니다.

## 적용 후 실행

기존 작업은 Ctrl+C로 중단한 뒤 새 패치를 설치합니다. 실행 중 코드를 교체하지 마세요.
코드 지문이 변경되므로 새 run-id를 사용합니다. 기존 원문·결과 폴더는 지우지 않습니다.
이번 구조 수용 코드 변경은 파서 캐시 지문에도 반영되어 첫 실행 때 구조화를 다시 할 수 있습니다.
그 다음 동일 코드/입력/설정의 같은 명령은 성공한 구조화와 LLM/임베딩 결과를 검증해 재사용합니다.

GENOS 프로젝트 루트 `/home/genos/DEV` 또는 같은 경로의 `/workspace`에서:

```bash
bash 06_TOOLS/COMMANDS/genos_data_stages.sh \
  --run-id external-status-001 --exclude-internal --stage structure --execute
```

구조화 후 같은 run-id로 `--stage llm`, 이후 `--stage vector`를 각각 실행할 수 있습니다.
전체 구조화 → 전체 LLM·검증 → 통과 문서 임베딩을 연속 실행하려면 `--stage all`을 사용합니다.
메인 진입점 `.venv/bin/python 06_TOOLS/pipeline.py build-data-stages`도 같은 구현을 호출합니다.

## 한눈에 확인하기

별도 터미널에서 실행 중에도 조회할 수 있습니다. 모델/문서 파서를 호출하지 않습니다.

```bash
bash 06_TOOLS/COMMANDS/genos_data_status.sh --run-id external-status-001
# 실패·보류·중단 문서만
bash 06_TOOLS/COMMANDS/genos_data_status.sh --run-id external-status-001 --failed
# 전체 문서 목록과 HTML/CSV 저장
bash 06_TOOLS/COMMANDS/genos_data_status.sh --run-id external-status-001 --limit 0 --export
```

저장 위치는 `01_DATA/LOGS/external-status-001/`입니다.

- `document-status.sqlite`: 문서별 각 단계와 실행 차수 기록. 원문/LLM 응답을 저장하는 DB와 별개입니다.
- `doc-status.html`: 검색·상태 필터 가능한 문서 상태표. 다운로드해서 브라우저에서 열 수 있습니다.
- `doc-status.csv`: 엑셀용 상세 표. 한글 UTF-8 BOM과 수식 주입 방어가 적용됩니다.
- `progress.log`, `current.json`: 상세 경로와 현재 작업. `detail.log`: 필요한 경우의 전체 오류 기록.

HTML은 내보낸 시점의 스냅샷입니다. 최신 표가 필요하면 `--export`를 다시 실행합니다.
각 단계의 완료/실패/대기/진행 기록/보류/중단/이번 실행 대상 아님을 구별합니다.
`진행 중 기록`은 마지막 저장 상태이며 프로세스 생존 보장은 아닙니다. Ctrl+C는 중단으로 남습니다.
입력 실패와 대체 표현 등 의도적 제외는 선택 문서와 별도 집계합니다. 제외한 internal 폴더는 탐색하지 않습니다.
구조화 완료가 LLM 완료나 배포 완료를 의미하지 않습니다. 새 실행 차수를 시작하면 이번 차수의 검증 상태를 표시하며 이전 차수 기록도 보존합니다.
구버전 실행에는 이 원장이 없으므로 완료율을 추정하지 않고 `기록 없음`으로 안내합니다.

## HWP/DOCX 태깅이 실제로 선택되는 규칙

파일 확장자는 파서를 고릅니다. 문서의 특정 양식 규칙을 고르려면 별도의 등록 `doc_type`이 필요합니다.
우선순위는 파일 sidecar `문서.hwp.genos.json` → 명시적 bindings의 문서 ID → exact 폴더 매핑입니다.
`[별표 1]`, `[별지]` 같은 파일명은 자동 양식 태그가 아닙니다. 상위 폴더 매핑을 자식 폴더에 임의 상속하지 않습니다.

sidecar는 다음 형태이며, 값은 **실제 그 문서에 맞는 등록 유형**이어야 합니다:

```json
{"doc_type": "실제 등록된 유형명"}
```

등록된 유형만 사용할 수 있습니다. 점수를 통과시키기 위해 관계없는 유형을 지정하지 마세요.
여러 문서의 매핑 파일은 `--bindings /절대경로/bindings.json` 또는 `FORMAT_BINDINGS_FILE`로 명시합니다.
UI의 `FORMAT_BINDINGS`와 CLI의 설정은 현재 자동 통합되지 않습니다.
DOCX 제목 스타일 구조를 쓰려면 sidecar `{"engine":"docxstyle"}`를 명시합니다. HWP에 적용할 수 없고 `doc_type`과 동시 사용하지 않습니다.
XML/조문 HTML은 원천 태그 기반 전용 파서이며 등록 유형으로 임의 대체하지 않습니다.

2026-09-10 로컬 메타데이터 감사: HWP 1,709개, HWPX 202개, sidecar 0개. 현재 등록 유형은 금소법/금소법시행령/표준투자권유준칙/STT전사 4개이며 자산 경로와 유형 일치는 확인했습니다.
기존 `01_DATA/format_bindings.json`은 새 RAW 경로와 맞지 않는 폴더, 미등록 유형을 포함해 그대로 자동 적용하지 않았습니다.
GENOS 현장 파일/태그가 동일한지는 미확인입니다. 상태표의 구조화 경로와 등록 태그 열에서 실제 선택을 확인하세요.

점수를 제외해도 마디가 전혀 없거나 본문이 어떤 구조에도 속하지 않는 파일은 실패 사유가 남습니다.
그 경우 해당 양식 등록/파서 출력을 수정해야 하며 빈 마디나 가짜 법령 조항을 만들지 않습니다.
