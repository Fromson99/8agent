# GENOS 구축 실행 묶음

Python 3.10 이상 / Linux / 영구 로컬 디스크용. 데이터·모델 가중치·API 키·운영 DB는 포함하지 않는다.
동결 실행기: ADR-0252 source-ids rev-001. 상태 CLI는 읽기 전용이다.

## 현재 확인 범위

Haiku 실제4사례에서 인용좌표 오류0, 수수료1사례만 의미검토부터 RAG답변까지 통과했다.
나머지3사례에는 의미 스키마/연결/coverage 오류가 남았다. GENOS 모델의 실제 성공률과
OpenAI 호환 JSON Schema 지원은 미검증이다. 먼저 소량 실행 후 상태를 확인한다.
이 묶음은 데이터 구축과 DRAFT 인계까지다. 운영 RAG 서버와 자동 MAIN 전환은 포함하지 않는다.

## 1. 설치

```bash
unzip genos-authoring-20260907.zip
cd genos-authoring
python3 verify_package.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

아래 명령은 `bash ./genos.sh`로 실행하므로 unzip의 실행권한 보존 여부와 무관하다.
정상 생성한 `.venv/bin/python`을 자동 사용한다. 별도 가상환경은 `GENOS_PYTHON=/path/to/python`으로 지정한다.

## 2. GENOS 원문과 모델 지정

기존 데이터가 아래 SQLite 형식이어야 한다. 단순 텍스트/JSON 폴더를 자동 변환하지는 않는다.
- `authoring_job`: job_id, document_id, state, input_json (PENDING_EXTRACTION 또는 NEEDS_SEGMENTATION)
- `source_block`: document_id, block_id, text, source_artifact_sha256 및 원문 구조 필드
- 이후 적재용 `document`, `source_unit`도 보존
- input_json의 원문·문서 해시가 source_block과 일치해야 한다.

```bash
export AUTHORING_INPUT='/mnt/data/authoring/store.sqlite'
export AUTHORING_QUEUE='/mnt/persistent/authoring/code-first-v1'
export GENOS_LLM_URL='https://YOUR-INTERNAL-SERVING-ENDPOINT'
export GENOS_LLM_MODEL='YOUR-EXACT-MODEL-ID'
export GENOS_LLM_REVISION='YOUR-IMMUTABLE-DEPLOYMENT-REVISION'
export AUTHORING_AUTHORITY='YOUR-SOURCE-AUTHORITY-GENERATION'
# 필요한 경우 보안 환경설정에서 GENOS_LLM_KEY, GENOS_USER_ID도 주입
```

엔드포인트는 실행기가 받는 OpenAI 호환 chat/completions 요청/응답을 지원해야 한다.
모델 이름만으로 호환된다고 판단하지 않는다. 내부 endpoint와 가중치는 실제 운영자가 지정한다.

## 3. 최초 한 번 준비 — LLM 호출 없음

```bash
bash ./genos.sh prepare \
  --source-db "$AUTHORING_INPUT" --queue "$AUTHORING_QUEUE" \
  --endpoint "$GENOS_LLM_URL" --model "$GENOS_LLM_MODEL" \
  --model-revision "$GENOS_LLM_REVISION" \
  --authority-generation "$AUTHORING_AUTHORITY" \
  --segment-chars 12000 --max-tokens 8192 --max-attempts 3
```

스키마와 시스템 설정은 ZIP에 포함된 동결 파일을 자동 사용한다.
기존 큐를 덮어쓰지 않는다. 구버전 실행기로 만든 큐와는 코드 해시가 달라 직접 호환되지 않는다.

## 4. 실행과 재개

```bash
# 처음에는 최대10회만 호출. 필요하면 다른 터미널에서 status --watch를 함께 실행한다.
bash ./genos.sh run --queue "$AUTHORING_QUEUE" --execute --max-calls 10 --workers 1

# 결과를 확인한 뒤 운영자가 호출 예산을 정해 같은 명령으로 이어간다.
# --max-calls는 이번 실행 상한이며, status 호출 횟수는 큐 전체 누적이다.
```

같은 버전·모델·revision·큐로 실행하면 완료된 작업은 건너뛴다. 저장된 응답은 재호출하지 않고
검증부터 이어간다. 응답 저장 전 종료는 원격 결과가 불명확하여 다시 호출될 수 있다.
미완료/실패가 남으면 run 종료코드2를 반환한다. 호출 상한 도달도 여기에 해당하며 반드시 서버 장애라는 뜻은 아니다.
인증·네트워크 장애 시 상태를 보존하고 멈춘다. 서버 복구 후 재개한다.

## 5. 진행상황 CLI — 추가 설치와 LLM 호출 없이 조회

```bash
# 한 번 보기
bash ./genos.sh status --queue "$AUTHORING_QUEUE"

# 5초마다 갱신, Ctrl+C로 조회만 종료
bash ./genos.sh status --queue "$AUTHORING_QUEUE" --watch 5

# JSON / JSON Lines로 수집
bash ./genos.sh status --queue "$AUTHORING_QUEUE" --json
bash ./genos.sh status --queue "$AUTHORING_QUEUE" --watch 10 --json

# Python만 직접 실행할 수도 있음
python3 06_TOOLS/OFFLINE/genos_progress.py --queue "$AUTHORING_QUEUE"
```

화면에 전체/시도한 작업/미시도/성공/실패/검토보류/남음/호출시도/응답저장/단계별호출/토큰을 표시한다.

- 작업 단위는 조문에서 분할한 조각이며 조문 수와 다를 수 있다.
- `남음 = 전체 활성 작업 - 성공`; 실패·검토보류를 포함한다.
- 실패 건수는 실패한 **작업 수**, 응답 검증 실패는 실패한 **시도 수**다.
- `호출 시도`는 이 큐의 추출/검토 요청 기록이며 실제 provider 실행과 항상 같지는 않다.
  RAG 검색선택/답변 호출과 다른 큐의 호출은 포함하지 않는다.
- `RUNNING`은 DB에 기록된 상태다. 죽은 프로세스의 기록도 재개 전까지 남을 수 있다.
- rework로 대체된 과거 작업은 전체에서 제외하고, 과거 호출과 토큰은 누적 합계에 남긴다.
- 조회는 원문·큐·실행 상태를 변경하지 않는다. watch 종료는 작업 실행에 영향을 주지 않는다.

## 6. 실패한 작업만 지정 재처리

자동 재추출은 단계별3회까지 진행한다. 상한 소진은 자동 무한 재시도하지 않는다.
status에 표시된 정확한 ID를 사용한다. 성공 건은 아래 명령으로 선택할 수 없다.

```bash
# 동일 단계에 오류 피드백과 함께 추가1회 허용 (LLM 호출은 다음 run에서만 발생)
bash ./genos.sh retry --queue "$AUTHORING_QUEUE" \
  --job-id 'EXACT-FAILED-JOB-ID' --reason '실패 원인 확인 후 제한된 재시도' --additional-attempts 1

# 의미 검토 반려 등은 수정 작업 생성. 과거 기록과 성공 건은 보존.
bash ./genos.sh rework --queue "$AUTHORING_QUEUE" \
  --job-id 'EXACT-FAILED-JOB-ID' --reason '정의 연결과 누락 근거 재검토'

bash ./genos.sh run --queue "$AUTHORING_QUEUE" --execute --max-calls 10 --workers 1
```

주의: run은 READY 상태의 다른 미처리 작업도 처리한다. 완료 건은 건너뛰지만,
대기 작업이 있는 전수 큐에서 이 명령을 '지정 실패 건만 실행'으로 해석하면 안 된다.

## 7. 통과분 인계 — LLM 호출 없음

```bash
bash ./genos.sh handoff --queue "$AUTHORING_QUEUE" \
  --output '/mnt/persistent/authoring/handoff-v1' --allow-partial
```

manifest에 실패/미완료 수가 남으며 결과는 DRAFT다. 모두 끝났다면 --allow-partial을 생략한다.
최신 semantic_runtime이 있는 별도 저장소에서 `load-handoff --runtime-root ...`로 적재할 수 있다.
이 ZIP에는 RAG 서버를 넣지 않았으므로 ZIP만으로 load-handoff까지 설치되지는 않는다.

실행 결과 큐와 인계 폴더는 영구 디스크에서 함께 보존한다. 원문 데이터가 바뀌거나 코드/스키마/모델이
바뀌면 기존 결과를 덮어쓰지 않고 새 세대로 구분한다.
