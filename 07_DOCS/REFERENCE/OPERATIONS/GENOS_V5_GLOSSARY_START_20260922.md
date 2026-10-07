# v5 MAIN 코드 반입과 용어집 연결 — 2026-09-22

현행 반입본은 `8agent-genos-v5-stages-generic-llm-20260922.zip`이다. 단계별 구축·v5·모델 ID
자동 조회와 공통 `GENOS_LLM_*` 설정을 함께 포함한다. 아래 최초 전달본 ZIP 이름을 쓰는
명령에서는 현행 파일명으로 바꾼다. 환경변수 이름 변경 시 기존 MODEL ID와 endpoint가
같으면 이미 생성한 v5 프로필을 유지할 수 있다. 대상 모델이나 endpoint가 바뀌면 새 이름으로
프로필을 생성하고 서빙의 프로필 경로·SHA256을 함께 바꾼다.

이전 반입본 `8agent-genos-v5-stages-auto-model-20260922.zip`은 단계별 구축과 Qwen/Gemma
모델 ID 자동 조회를 포함하지만 공통 변수 통일 전 코드다. 아래 r2 ZIP 이름은 최초 전달본
기록이며, 신규 반입에는 위 현행 반입본을 사용한다. r2에는 자동 조회와
`document-release select/merge/prepare/review/index` 분리 실행이 포함되지 않는다.

성능 확인에 사용한 v5 하네스의 현행 작업 코드 전달본이다. 작업 MAIN의 기본 구현은
`legal-agent-tools-v5`이며 로컬 활성 릴리스는 `legal-agent-v5-20260922-r3`(generation 20)다.
번호 선택·질문 요구 추적·판단/행동 검사·원문/초안 검토가 포함된다.
품질 인증은 false이며 Gemma 3문항 실험에서 확인한 조건 누락·적용 판단의 약점은 남아 있다.
GENOS 내부 모델 결속과 현장 코드 리비전 배포는 아래 절차로 별도 수행한다.

## 전달물과 준비물

`8agent-main-v5-20260922-code-r2.zip`은 `genosIgnore`로 만든 코드 전용 작업판 스냅샷이다.
ZIP의 `CODE_MANIFEST.json`이 파일별 해시와 Git 기준 커밋·미커밋 포함 여부를 기록한다.
원문, 사전 DB, knowledge bundle, 로컬 ACTIVE_RELEASE와 고정 릴리스, 실제 `.env`·키는 포함하지 않는다.
Git main 병합이나 GENOS 배포가 완료됐다는 뜻이 아니다.

새 작업 폴더에 코드를 풀고, 기존 현장 원문·용어 데이터를 그 폴더의 `01_DATA`에
동일 상대 경로로 복사하거나 영속 볼륨으로 마운트한다. 심볼릭 링크는 지원하지 않는다.
기존 코드·데이터·CURRENT는 보존한다. 전체 ZIP을 기존 코드 위에 덮어 풀지 않는다.

```bash
sha256sum -c 8agent-main-v5-20260922-code-r2.zip.sha256
mkdir 8agent-main-v5-20260922
python3 -m zipfile -e 8agent-main-v5-20260922-code-r2.zip 8agent-main-v5-20260922
cd 8agent-main-v5-20260922
python3 06_TOOLS/COMMANDS/code_ship.py verify ../8agent-main-v5-20260922-code-r2.zip
```

Python 3.11의 현장 의존성 환경을 사용한다. 새 환경이면 반입 wheelhouse 또는 내부 패키지
저장소에서 `requirements.txt`를 설치한다. 예:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links /현장/wheelhouse -r requirements.txt
```

고정 의존성을 포함한 전체 ZIP에는 과거 코드 세대의 Python 3.11 문법 비호환 파일 1개가
보존돼 있다. 현행 코드와 과거 전체 코드의 호환성은 구분한다. 자세한 범위는
[전체 코드 ZIP 안내](GENOS_FULL_CODE_ZIP.md)를 따른다.

## 1. 용어집 데이터 배치

기본 설정 `00_SYSTEM/GLOSSARY_PIPELINE.json`이 선택하는 두 디렉터리가 필요하다.

```text
01_DATA/
  RAW/                                      현장 내부·외부 원문
  LEXICON/
    glossary-v1/boundary-20260914-v3/
      dictionary.sqlite
      report.json
    knowledge-bundles/genos-full-20260915-v1/
      manifest.json
      (manifest가 지정한 전체 DB·근거 파일)
```

기존 `genos-full-knowledge` 반입본이 있다면 그 안의 해당 데이터 디렉터리를 재사용한다.
이름이 비슷한 예전 glossary ZIP을 임의로 대신 사용하지 않는다. knowledge manifest의
설정 해시는 `b36ebd9c0f427e2e4eb1bc38c60f515befd9fa83fef0982081d1af07d81fddaf`다.
전체 관계·번역 묶음까지 있어야 기본 설정의 검사에 통과한다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py glossary knowledge check
.venv/bin/python -B 06_TOOLS/pipeline.py glossary knowledge lookup --term 증권
```

`knowledge check`는 파일·해시 검사이며 용어 의미 검토 완료를 뜻하지 않는다.
사전 파일을 놓는 것만으로 문서 연결과 서빙 색인이 바뀌지는 않는다. 아래 구축을 수행한다.
구축의 논리 data root는 현재 코드 폴더의 `01_DATA`다. `GENOS_DATA_ROOT`만 다른 경로로
설정해도 구축 입력 경로가 바뀌지는 않는다.

## 2. 현장 내부 Gemma 설정

현장의 실제 내부 URL·서빙 ID·인증키를 비밀 환경 설정에 지정한다.
API 모델 ID는 Qwen과 같은 `/models` 조회로 자동 선택한다. 모델이 하나일 때만 자동 선택하며,
여러 개이면 `GENOS_LLM_MODEL`로 명시한다. 모델을 바꿀 때 자동 조회하려면 남아 있는
MODEL 값을 제거한다. 구조화·용어 검토·RAG는 모델 종류와 무관하게 `GENOS_LLM_*`를 읽는다.
이전 `GENOS_QWEN_*`, `GENOS_GEMMA_*`, `GENOS_LLM_PROFILE`은 더 이상 사용하지 않는다.
외부 실험의 `google/gemma-4-31b-it` 문자열을 내부 API 모델 ID로 자동 복사하지 않는다.
기존 PDF 전처리기·VLM 설정도 유지한다. 문서 구조 검수와 RAG의 출력 예산은 별도다.

```bash
export SEMANTIC_LLM_BACKEND=genos
export LLM_BACKEND=genos
# 현장 비밀 설정에 다음 항목을 채운다:
# GENOS_BASE_URL
# GENOS_LLM_SERVING_ID
# GENOS_LLM_KEY
# GENOS_LLM_MODEL  (선택값: /models에서 모델이 여러 개일 때 지정)
# GENOS_GATEWAY_API_PREFIX=none  (실제 게이트웨이가 /v1을 요구하면 /v1)
```

직접 URL 방식이면 `GENOS_LLM_URL`, `GENOS_LLM_API_PREFIX`, `GENOS_LLM_KEY`,
`GENOS_LLM_MODEL`을 사용할 수 있다. 게이트웨이 방식으로 전환할 때는 직접 URL이 우선하지
않도록 `GENOS_LLM_URL`을 제거한다. 키를 명령 출력이나 공유 문서에 남기지 않는다.
파일에 설정했다면 현장 파일을 `set -a; source .env.genos.local; set +a`로 환경에 로드한다.

## 3. 문서와 용어집을 통합 구축

새 코드·입력에는 새 run ID를 사용한다. 아래의 `main-v5-001`은 예시이며 완료된 run은 재사용하지 않는다.

```bash
# 입력·사전 검사. 모델 호출 없이 계획/로그를 작성한다.
.venv/bin/python -B 06_TOOLS/pipeline.py build-all \
  --run-id main-v5-001 --check-only

# 전체 원문 구조화 → 기존/신규 정의 통합 검토 → 전체 용어 연결·색인·서빙 후보
.venv/bin/python -B 06_TOOLS/pipeline.py build-all \
  --run-id main-v5-001 --max-review-jobs 100 --execute
```

기존 서빙 문서를 함께 유지하려면 **두 명령에 모두**
`--base-generation /현장/기존/serving/generation`을 추가한다. 여러 세대는 옵션을 반복한다.
기존 세대는 자동 검색·병합하지 않는다. 내규를 제외하려면 `--exclude-internal`을 붙인다.

이전에 검토 완료한 사전을 재사용할 때만
`--glossary-dir /현장/이전/TERM_RELEASES/<run>/glossary-reviewed`를 추가한다.
이 옵션은 완료 영수증을 요구한다. 미검토 기본 초안을 이 옵션으로 지정하지 말고
위 기본 선택 경로에 반입한다.

exit 3은 용어 검토 작업이 남았다는 뜻이다. 입력·모델·코드를 유지한 채 같은 실행 명령을
반복하면 완료 검토를 건너뛰고 이어 간다. 실패 작업의 재호출은 원인을 고친 뒤
`--retry-review-failed`를 명시한다. 로그는 `01_DATA/LOGS/<run>/doc-status.html`,
검토 상태는 `01_DATA/TERM_RELEASES/<run>/review`에 남는다.

이미 **현행 코드에서 전체 구조화가 완료된 run**은 후속 연결부터 실행할 수 있다.
기존 `LOGS/<run>/structure-selection.json`과 그 파일이 참조하는 구조화 경로·해시가 필요하다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py document-release build \
  --run-id 구조화완료_run --max-review-jobs 100
```

이 명령에도 유지할 원문은 `--base-generation`, 이전 검토 사전은 `--glossary-dir`로 명시한다.
기존 구조화 영수증이 없거나 현재 입력/코드와 맞지 않으면 `build-all`부터 실행한다.
과거 `--knowledge-zip`, `build-all-legacy`, `--publish`는 이 경로에서 사용하지 않는다.

## 4. 후보 검증 후 v5로 실행

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py document-release verify \
  --release "$PWD/01_DATA/TERM_RELEASES/main-v5-001"
```

완료 산출물은 `serving/generation`이다. 원문·navigation·전체 용어 번들·사전·캐시가
함께 포장된다. `review_status=PARTIAL`이면 남은 실패/미확인을 확인한다. DRAFT 생성과
품질 인증은 별도다.

모델 프로필은 기본 미결속이다.
코드서빙의 GENOS 세대를 선택한 v5는 모델 설정을 코드서빙 환경변수에서 직접 읽는다.
MODEL을 생략하면 내부 `/models`의 단일 모델 ID를 선택한다. 시작 시 모델 ID가
같은 endpoint에 게시돼 있는지 확인하며 임의로 바꾸지 않는다.

```bash
export GENOS_GENERATION="$PWD/01_DATA/TERM_RELEASES/main-v5-001/serving/generation"
export SEMANTIC_LLM_BACKEND=genos
# 선택: 코드서빙 v5 모델 호출 1회당 max_tokens. 비우면 기본 6400.
# export GENOS_RAG_MAX_OUTPUT_TOKENS=80000
```

`GENOS_RAG_IMPLEMENTATION`은 현재 MAIN의 `PIPELINE.json` 기본 v5를 사용하므로
설정하지 않는다. 예전 override가 있으면 제거한다. `GENOS_GENERATION`으로
검증된 후보를 명시하는 방법이다. 기본 v5 예산은 요청당 14회,
300초, 출력 6,400토큰이며 내부 Gemma 설정·용량의 실제 적합성은 현장에서 확인한다.
위 `export`는 같은 셸에서 직접 시험할 때만 적용된다. 워크플로우에서 호출하는
코드서빙에는 GENOS 화면의 코드서빙 환경 설정에 같은 값과 `GENOS_BASE_URL`,
`GENOS_LLM_SERVING_ID`, `GENOS_LLM_KEY`를 각각 등록하고 새 리비전을 배포한다.
`GENOS_LLM_MODEL`은 필요할 때만 지정한다. 기존 기본 프로필·엔진 해시·
개발 PC의 데이터 경로는 바꾸지 않는다. 기존 `LEGAL_AGENT_PROFILE` 파일과 해시를
명시한 배포는 그 파일 결속을 우선 사용하므로 환경변수 방식에서는 둘 다 제거한다.
출력 토큰 설정은 워크플로우가 아니라 코드서빙 환경에서 읽으며, 새 데이터 세대에도
같은 설정을 사용한다. [세대 교체 서빙 계약](GENOS_RAG_GENERATION_HANDOFF.md)을 따른다.

코드스페이스에서 직접 실행할 때:

```bash
.venv/bin/python -m uvicorn service:application --factory --host 127.0.0.1 --port 8000
```

새 터미널에서 원문 조회와 모델 답변을 각각 확인한다.

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/v1/rag/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"자료 목록","document_ids":[],"use_llm":false}'
curl -sS http://127.0.0.1:8000/v1/rag/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"확인할 업무 질문","document_ids":[],"use_llm":true}'
```

이 주소는 명령을 실행한 코드스페이스 프로세스다. 실제 GENOS 코드서빙은 선택 코드
리비전·데이터 볼륨·환경변수·채팅 워크플로우 연결을 따로 배포한다. 현재 외부 세션에서
GENOS 연결·모델 호출·배포를 확인한 것은 아니다.

## 5. CURRENT 방식과 원복

위 직접 세대 지정 방식 대신 CURRENT로 관리하려면 verify 통과 후 다음을 사용한다.
기존 포인터가 있으면 그 SHA256, 없을 때만 `absent`를 사용한다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py document-release activate \
  --release "$PWD/01_DATA/TERM_RELEASES/main-v5-001" \
  --active-data-root "$PWD/01_DATA" \
  --expected-current <확인한_CURRENT_SHA256_또는_absent> --confirm-main
unset GENOS_GENERATION
export GENOS_DATA_ROOT="$PWD/01_DATA"
```

변경 후 서빙 프로세스를 재시작한다. `GENOS_GENERATION`을 남기면 CURRENT보다 우선한다.
원복은 기존 코드 리비전·프로필과 이전 `GENOS_GENERATION`으로 돌아가거나,
CURRENT 활성화 영수증으로 `document-release rollback`을 실행한다.
이전 데이터·새 검토 기록을 삭제하지 않는다. 상세 활성화/원복 계약은
[문서 연결 안내](GENOS_DOCUMENT_CONNECTIONS.md), v5 계약은 [v5 운영 안내](LEGAL_AGENT_V5.md)를 따른다.
