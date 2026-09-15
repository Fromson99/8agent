# GENOS 로컬 LLM 전수 구축 실행·복구

이 실행기는 원문별 추출과 별도 모델 검토를 SQLite에 기록한다. 같은 큐로 재실행하면
끝난 단계는 건너뛴다. 준비·상태 조회·재시도 예약·내보내기는 네트워크를 사용하지 않는다.
실제 요청은 `run --execute --max-calls N`에서만 발생한다.

현재 구현 검증은 가짜 모델 응답으로만 수행했다. GENOS 서버, 실제 로컬 모델의 JSON Schema
지원·컨텍스트 크기·추출 품질은 아직 검증하지 않았다. 이 도구는 운영 MAIN의 모델 설정을
변경하지 않으며 추출 결과를 Canonical이나 운영 Projection으로 자동 승격하지 않는다.
사용자의 이번 GENOS 내부 로컬 모델 구축 지시를 해당 오프라인 실행 범위에 기록한다.

## 1. GENOS에 준비할 파일

- `genos_authoring.py`와 `requirements-genos-authoring.txt`
- 읽기 전용 입력 `store.sqlite`: `authoring_job(job_id, document_id, state, input_json)` 테이블 필요
- 해당 입력에 맞는 `authoring-system.txt`, `observation.schema.json`

현재 호환되는 전수 입력은 저장소의 다음 세대다.

`01_DATA/SEMANTIC/GENERATIONS/ssv2-shadow-3dfc5e0c7a33ebf4fa3ea184/`

49,036개 `PENDING_EXTRACTION`과 226개 `NEEDS_SEGMENTATION`을 보유한다. 후자는 호출하지 않고
별도 보류한다. 기존 코스닥 통과분을 자동으로 재사용하지 않는다. 기존 작업 ID와 새 작업,
모델·스키마·원문 지문의 일치 및 검토 계승을 확인하지 않고 완료로 처리할 수 없기 때문이다.
진행 중인 ADR-0245의 통합 저장소도 위 테이블 계약을 유지한 확정 스냅샷일 때 사용할 수 있다.

Python 3.10 이상과 의존성을 GENOS 환경에 준비한다. 폐쇄망이면 wheels를 사전 반입한다.

```bash
python -m pip install -r requirements-genos-authoring.txt
```

큐는 서버 재시작 후에도 남는 **Linux 로컬 영구 디스크/볼륨**에 둔다. SQLite 잠금과 fsync가
필요하므로 NFS/SMB, 일시적인 `/tmp`, 실행 때 초기화되는 코드 서빙 작업 디렉터리는 사용하지 않는다.
이 도구는 GENOS 서버의 배치/터미널 프로세스로 실행한다. 장시간 작업을 HTTP 요청 안에 매달지 않는다.

## 2. 처음 한 번만 준비 — 모델 호출 없음

환경 변수는 실제 GENOS 서빙 정보로 설정한다. 모델 revision은 같은 모델 이름 아래 가중치나
서빙 설정이 바뀌었는지 구분할 수 있는 고정된 운영 배포 ID/지문을 사용한다.
API 키는 큐에 기록하지 않으며 `GENOS_LLM_KEY`에서만 읽는다. 필요하면 `GENOS_USER_ID`도 설정한다.

```bash
# 다음 값은 GENOS 운영자가 실제 값으로 설정한다.
export GENOS_LLM_URL='https://YOUR-INTERNAL-GENOS/api/gateway/rep/serving/YOUR-SERVING-ID'
export GENOS_LLM_MODEL='YOUR-EXACT-SERVED-MODEL-ID'
export GENOS_LLM_REVISION='YOUR-IMMUTABLE-DEPLOYMENT-REVISION'
# GENOS_LLM_KEY는 내부 비밀 설정에서 주입한다.

export AUTHORING_INPUT='/mnt/8-agent/authoring-input'
export AUTHORING_QUEUE='/mnt/8-agent/authoring-runs/corpus-v1'

python genos_authoring.py prepare \
  --queue "$AUTHORING_QUEUE" \
  --source-db "$AUTHORING_INPUT/store.sqlite" \
  --system "$AUTHORING_INPUT/authoring-system.txt" \
  --schema "$AUTHORING_INPUT/observation.schema.json" \
  --endpoint "$GENOS_LLM_URL" \
  --model "$GENOS_LLM_MODEL" \
  --model-revision "$GENOS_LLM_REVISION" \
  --max-tokens 8192 --max-attempts 3

python genos_authoring.py status --queue "$AUTHORING_QUEUE"
```

`8192`는 조정 가능한 출력 상한이며 모든 작업의 완료를 보장하는 값이 아니다. 모델의 출력·
컨텍스트 한도를 확인해 준비 시 지정한다. JSON Schema 강제 출력을 지원하지 않는 서버에서
조용히 프롬프트 방식으로 바꾸지 않는다. 원문·지시문·스키마·모델·revision·엔드포인트·실행기
코드 hash를 큐에 동결한다. 준비가 중단되면 `preparing.sqlite`만 남고 실행 가능한 큐는 발행되지
않는다. 그 폴더를 증거로 보존하고 새 큐 경로에서 prepare를 다시 수행한다.

## 3. 나중에 명시적으로 실행 — 지금 실행하지 않음

먼저 적은 호출 한도로 서버 연결과 출력 호환성을 확인하고, 확인 후 동일 큐의 한도와 worker 수를
늘린다. `max-calls`는 **이번 프로세스 전체**의 상한이며 추출과 검토를 모두 센다.
`workers`는 서버/GPU/토큰 처리 용량에 맞춰 조정한다.

```bash
# --execute가 없으면 상태만 출력한다.
python genos_authoring.py run --queue "$AUTHORING_QUEUE"

# 실제 실행을 결정한 이후 사용하는 명령이다.
python genos_authoring.py run --queue "$AUTHORING_QUEUE" \
  --execute --max-calls 10 --workers 1 --timeout 300

# 같은 큐로 계속 진행 / 장애 후 재실행
python genos_authoring.py run --queue "$AUTHORING_QUEUE" \
  --execute --max-calls 1000 --workers 4 --timeout 300
```

run은 끝나도 READY/FAILED가 남으면 종료코드 2를 반환한다. 호출 상한 도달도 이 경우에 속한다.
프로세스 종료코드 0을 전체 의미 데이터 완성으로 해석하지 말고 상태의 NEEDS_REVIEW 및
NEEDS_SEGMENTATION도 확인한다. 네트워크/HTTP 오류는 새 작업 시작을 멈춘다. 이미 전송한 요청은
마무리하여 저장한다. 실패 작업은 30초 이후 재실행 대상이 된다. 자동 무한 재시작 서비스는
등록하지 않으며 클라우드 fallback, 모델 자동 탐색, 프록시 상속, HTTP redirect도 사용하지 않는다.

## 4. 장애별 재개 동작

| 장애 시점 | 다음 실행 |
|---|---|
| 추출 전 중단 | 추출 시작 |
| 추출 응답 저장 후, 검증 전 중단 | 저장 응답을 검증. 추출 재호출 없음 |
| 추출 통과 후 중단 | 검토만 실행 |
| 검토 응답 저장 후 중단 | 저장 응답으로 종료 상태 확정 |
| 검토까지 통과 | 재호출 없음 |
| 서버 timeout/503 | 기록 후 중단, 같은 큐 재실행 |
| JSON 오류·잘린 출력 | 원응답 보존, 단계별 최대 시도 수까지만 재시도 |
| 검토 반려 | NEEDS_REVIEW로 보류. 자동 승인·자동 의미 수정 없음 |
| SIGINT/SIGTERM | 새 요청을 멈추고 진행 중 응답을 저장한 뒤 종료 |
| SIGKILL/정전 | OS 잠금 해제 후 원장 복구. 저장된 응답은 재사용 |
| 실행기·설정 지문 변경 | 혼합 실행 거부. 원래 버전으로 재개하거나 새 큐 생성 |

서버가 처리를 끝냈어도 응답이 큐에 저장되기 전에 연결/전원이 끊기면 성공 여부를 확정할 수
없다. 이 경우 `INTERRUPTED_UNKNOWN`을 남기고 해당 단계만 재호출할 수 있다. 서버의 멱등 API
없이는 요청의 exactly-once 실행을 보장할 수 없다. 사용량도 이때 0이 아닌 unknown으로 집계한다.

같은 큐를 두 프로세스가 동시에 실행하려고 하면 두 번째는 거부한다. 한 프로세스 안의 worker는
트랜잭션으로 서로 다른 작업을 가져간다. 상태와 단계 완료는 트랜잭션 단위로 저장한다.

## 5. 실패한 작업만 추가 시도

원인 확인 후 **정확한 작업 ID**를 지정한다. 과거 시도/실패 기록은 지우지 않는다.

```bash
python genos_authoring.py retry --queue "$AUTHORING_QUEUE" \
  --job-id 'EXACT-JOB-ID' --additional-attempts 1 \
  --reason '서버 복구 확인 후 같은 입력 재시도'

python genos_authoring.py run --queue "$AUTHORING_QUEUE" \
  --execute --max-calls 10 --workers 1
```

FAILED 또는 NEEDS_REVIEW만 재시도 예약할 수 있다. 이미 추출을 통과한 작업은 검토 단계부터
다시 한다. 의미 자체가 틀린 후보는 동일 검토의 반복만으로 고쳐지지 않는다. 프롬프트·스키마·
원문을 수정하는 재구축은 새 큐/세대로 분리하고, 이전 결과를 덮어쓰지 않는다.

## 6. 보관·진척 확인·결과 인계

`queue.sqlite`에는 원문 입력, 고정 설정, 모든 시도의 exact 요청/응답, hash, 토큰 사용량,
시간, 오류와 추가 재시도 사유가 들어 있다. `runner.lock`은 잠금 파일일 뿐이므로 수동으로
삭제해서 중복 실행을 허용하지 않는다.

작업별 상태는 아래 읽기 전용 조회로 확인할 수 있다.

```bash
python - "$AUTHORING_QUEUE" <<'PYCODE'
import sqlite3, sys
from pathlib import Path
p = Path(sys.argv[1], 'queue.sqlite').resolve()
c = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True)
for row in c.execute('select id,document_id,stage,state,error from job where state in (?,?)', ('FAILED','NEEDS_REVIEW')):
    print(row)
PYCODE

python genos_authoring.py export --queue "$AUTHORING_QUEUE" \
  --output '/mnt/8-agent/authoring-runs/corpus-v1-candidates.jsonl'
```

내보내기는 manifest 한 줄 뒤에 후보별 상태와 검토 결과를 기록한다. 통과 후보에도
`production_approved=false`를 명시한다. 별도의 원문 근거·참조·범위 검증과 정본 승인,
Projection 구축이 필요하다. 전체 입력/원응답은 큐를 함께 인계해야 한다.

백업은 실행을 정상 종료한 뒤 큐 디렉터리 전체를 복사한다. 실행 중 단순 파일 복사 대신
SQLite backup API를 사용해야 한다. GENOS 서버의 재시작과 영구 볼륨 복원은 아직 현장 검증하지
않았으므로, 첫 실제 실행에서 소량 작업 저장 후 프로세스 재시작을 확인한다.
