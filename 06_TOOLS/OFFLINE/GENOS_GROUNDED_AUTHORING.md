# GENOS 원문 검증 구축 → 최신 RAG 적재

자동 재추출을 포함한 최신 실행 묶음은 [ADR-0250 안내](GENOS_AUTO_REEXTRACT.md)를 따른다. 아래 ADR-0248 기록은 이전 버전 재현용이다.

ADR-0248 rev-003의 동결된 오프라인 실행기를 사용한다. 이전 ADR-0246 실행기는 중단 복구만
담당했으므로 새 전수 구축에는 이 묶음을 사용한다. 실제 LLM 호출은 아직 수행하지 않았다.

## 연결한 흐름

```text
원본 SQLite와 작업 목록 대조
 → 원문 좌표를 유지한 분할
 → LLM graph/coverage 추출
 → 호스트가 문서 범위·해시·호출 provenance 생성
 → 원문 인용·조문 범위·타입·참조·단서 계약 검증
 → 별도 LLM 의미 검토
 → 모델 검토를 통과한 DRAFT 묶음과 검토 영수증
 → 최신 semantic_runtime의 load
 → 새 DRAFT DB + Projection + 검색 색인
```

정본 모양의 `CANONICAL_BUNDLE`은 뒷단의 적재 형식이다. 이 작업에서는 반드시 DRAFT이며
사람 승인·법률적 완성·APPROVED로 표시하지 않는다. 운영 릴리스는 자동 전환하지 않는다.

## 준비 및 실행

인계 tar를 GENOS의 영구 Linux 디스크에 풀고 그 루트에서 실행한다. 원문 DB와 모델 가중치는
묶음에 포함하지 않는다. 입력 DB에는 authoring_job뿐 아니라 원래 source_block 테이블도 있어야
하며, 적재에는 document/source_unit/source_block 전체가 필요하다.

```bash
python -m pip install -r requirements-genos-authoring.txt

# 실제 내부 서빙 정보/배포 revision을 설정한다. 키는 내부 비밀 설정으로 주입한다.
export GENOS_LLM_URL='https://YOUR-INTERNAL-GENOS/api/gateway/rep/serving/YOUR-SERVING-ID'
export GENOS_LLM_MODEL='YOUR-EXACT-MODEL-ID'
export GENOS_LLM_REVISION='YOUR-IMMUTABLE-MODEL-REVISION'
export AUTHORING_INPUT='/mnt/8-agent/authoring-input'
export AUTHORING_QUEUE='/mnt/8-agent/authoring-runs/grounded-v1'
export AUTHORING_AUTHORITY='YOUR-SOURCE-AUTHORITY-GENERATION'

python 06_TOOLS/OFFLINE/genos_authoring.py prepare \
  --queue "$AUTHORING_QUEUE" --source-db "$AUTHORING_INPUT/store.sqlite" \
  --system "$AUTHORING_INPUT/authoring-system.txt" \
  --schema "$AUTHORING_INPUT/observation.schema.json" \
  --endpoint "$GENOS_LLM_URL" --model "$GENOS_LLM_MODEL" \
  --model-revision "$GENOS_LLM_REVISION" --authority-generation "$AUTHORING_AUTHORITY" \
  --segment-chars 12000 --max-tokens 8192 --max-attempts 3

# 준비·조회는 LLM을 호출하지 않는다.
python 06_TOOLS/OFFLINE/genos_authoring.py status --queue "$AUTHORING_QUEUE"

# 나중에 실행할 때만 --execute를 넣는다. 처음에는 소량으로 서버 지원을 확인한다.
python 06_TOOLS/OFFLINE/genos_authoring.py run --queue "$AUTHORING_QUEUE" \
  --execute --max-calls 10 --workers 1 --timeout 300
```

서버 중단 후 같은 명령으로 재개한다. 단계별 응답을 보존하므로 추출 완료분은 검토부터 진행한다.
모델/설정/코드 변경은 같은 큐에 섞지 않는다. 서버가 완료했지만 저장 전에 끊긴 요청은 결과 불명으로
기록되고 재호출될 수 있다. 동시에 같은 큐를 여러 프로세스로 실행하지 않는다.

`segment-chars`는 원문 문자 기준이며 모델 토큰 한도가 아니다. 상위 구조 문맥과 schema가 추가된다.
GENOS 모델의 컨텍스트·출력 한도·JSON Schema 지원을 실제 소량 실행으로 확인해야 한다.
긴 원문 블록도 문자 구간으로 나누고 원래 start/end를 유지한다. 조각 밖 근거나 외부 조문은
모델이 임의로 완결하지 않고 미해결로 기록한다. 이는 법률 의미의 전수 완성을 보장하지 않는다.

## 검토 반려를 수정 작업으로 이어가기

네트워크/일시적 형식 오류에 같은 단계만 더 시도하려면 `retry`, 의미 누락·검토 반려를 고쳐서
재추출하려면 `rework`를 쓴다. rework는 원문·이전 후보·검토 이유를 새 작업으로 넘기고 이전
시도/응답은 보존한다. 수정 작업도 다시 원문 검증과 별도 모델 검토를 통과해야 한다.

```bash
python 06_TOOLS/OFFLINE/genos_authoring.py rework --queue "$AUTHORING_QUEUE" \
  --job-id 'EXACT-FAILED-JOB-ID' --reason '검토에서 지적한 조건 누락을 원문에 맞게 수정'
python 06_TOOLS/OFFLINE/genos_authoring.py run --queue "$AUTHORING_QUEUE" \
  --execute --max-calls 10 --workers 1
```

누락된 coverage나 UNRESOLVED 구간이 있으면 완료로 인계하지 않는다. 반려 작업을 무한히 자동
재시도하지 않는다. 실패/보류를 포함한 진척 상태를 확인하고 수정 대상만 지정한다.

## DRAFT 인계와 적재 — LLM 호출 없음

```bash
python 06_TOOLS/OFFLINE/genos_authoring.py handoff --queue "$AUTHORING_QUEUE" \
  --output '/mnt/8-agent/authoring-runs/grounded-v1-handoff'

python 06_TOOLS/OFFLINE/genos_authoring.py load-handoff \
  --runtime-root '/mnt/8-agent/repository' \
  --source-store "$AUTHORING_INPUT/store.sqlite" \
  --handoff '/mnt/8-agent/authoring-runs/grounded-v1-handoff' \
  --output '/mnt/8-agent/repository/01_DATA/SEMANTIC/GENERATIONS/grounded-v1-draft'
```

`runtime-root`는 ADR-0245 최신 semantic_runtime이 설치된 저장소 루트다. source-store는 prepare에
사용한 원본 DB와 해시가 같아야 한다. 수만 개 bundle 파일을 명령행 인수로 나열하지 않고
manifest에서 읽는다. DRAFT 상태와 영수증·bundle 해시를 검증한 뒤 적재한다.

미완료 작업이 있으면 handoff는 기본적으로 실패한다. 검토 통과분만 명시적으로 부분 인계할 때만
`--allow-partial`을 추가한다. 이때 manifest에 미완료 건수가 남는다. manifest.json이 없는 인계
디렉터리는 중단된 것이므로 적재하지 않는다. 기존 인계/세대 폴더를 덮어쓰지 않는다.

handoff에는 묶음·모델 검토 영수증·manifest가 있고, queue.sqlite에는 원본 입력과 모든 실제
요청·응답·실패 이력이 남는다. 둘을 함께 보존한다. 신규 DRAFT를 만들 뿐 MAIN/ACTIVE는 바뀌지 않는다.

## 확인한 범위

- 최종 동결 실행기: 합성 응답 기반 검증 14/14 통과.
- 실제 전수 원문: 207개 문서, 기존49,262개 작업을49,747개 조각 작업으로 준비.
- 원문27,291,618문자 보존. 기존226개 분할 보류 작업도 준비됨.
- 원문과 작업 입력의 불일치, 잘못된 인용·문서·조문 범위·참조·coverage 거절.
- 응답 저장 후 강제 종료/재시작, 검토 반려 후 수정, DRAFT 적재와 Projection 생성 확인.
- 실제 모델·GENOS endpoint·영구 볼륨 재시작·답변 품질·자동 운영 전환은 미실행.

로컬 확인용 `ADR-0248-full-prepare-v3-NOT-FOR-EXECUTION` 큐는 가짜 모델명을 사용한 준비 감사
산출물이다. GENOS 실행용으로 옮기지 말고 실제 서빙 정보로 prepare를 수행한다.
