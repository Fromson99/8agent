# 명시 참조 해소 운영 계약

## 상태

작업 코드는 `reference-resolution-harness-v1`의 결정론 범위 확장, 폐쇄 후보 snapshot,
모델 observation journal, 자동 승인, 새 navigation generation 적용을 구현한다.
활성 MAIN 릴리스와 GENOS 배포는 자동 변경하지 않는다. 실제 내부 Qwen 품질과 현장 연결은 미확인이다.

2026-09-29 사용자 지시로 `build-all` / `document-release build` 안에 모델 실행과 자동 승인을 배선했다.
이번에 틀린 사례를 막는 별도 후보 필터·의미 규칙·프롬프트 규칙은 추가하지 않았다.
형식과 폐쇄 ID 검증을 통과한 모델 선택은 전부 승인한다. 기권은 UNKNOWN으로 완료한다.
ADR-0553의 12개 결과는 기존 측정 기록이며 이번 배선 후 성능을 다시 측정한 결과가 아니다.

## MAIN에서의 위치

```text
문서 구조화 → 원문 통합 → 용어집 검토·문서–용어 연결
→ 결정론 명시 참조 baseline → LLM 모호한 참조 선택 → 자동 승인
→ 최종 탐색 색인·fulltext 결속 → RAG
```

색인을 구축할 때 실행한다. 질의마다 참조 연결을 다시 생성하지 않는다.
모델은 명시 프로필 또는 `REFERENCE_RESOLUTION_PROFILE`로 선택한다. 미설정 구축은 기존 결정론 경로다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-all \
  --run-id RUN_ID --reference-model-profile PROFILE --execute
```

결정론 baseline은 `TERM_RELEASES/RUN_ID/serving-baseline/generation`, 모델 journal은
`TERM_RELEASES/RUN_ID/reference-review`, 최종 결과는 `TERM_RELEASES/RUN_ID/serving/generation`이다.
모델 프로필·코드·부모 navigation 해시를 고정하고 승인/기권 이력을 journal에 남긴다.
`--max-reference-cases`(기본 10000), `--reference-batch-size`(기본 8)는 실행량을 제한한다.
잔여 후보·실패·전송 결과 불명이 있으면 `REFERENCE_RESOLUTION_PENDING`이며 같은 run ID로 재개한다.
완료한 선택은 재호출하지 않는다. 사람 검토 대기로 중단하지 않는다.

단계별 실행은 용어집 review 완료 후 `document-release references --reference-model-profile PROFILE`로
모델 작업만 수행하고, `document-release index --reference-model-profile PROFILE`로 최종 색인을 만든다.
`index`는 모델을 호출하지 않고 준비된 결과만 소비한다.

## 모델 설정

OpenRouter 프로필은 `00_SYSTEM/LEGAL_AGENT/reference-qwen-openrouter.json`이다.
`qwen/qwen3.8-27b`, Parasail FP8 단독, thinking off, provider/model fallback 없음이며
`.env` 또는 환경의 `OPEN_ROUTER`를 읽고 키는 journal·로그에 저장하지 않는다.
실제 모델·provider·응답·사용량은 물리 호출 journal로 확인한다.
이는 실험 기본 Gemma 정책 및 RAG 답변 모델을 바꾸지 않는다.

공개 반출 범위는 `reference-qwen-public.json`에 source generation/store hash와 145개 문서 ID로
고정한다. 기존 공개 출처 승인 범위에서 모델과 목적만 이번 사용자 지시에 결속했다.
내부 문서나 새 원문 세대에 자동 확장하지 않으며 반출 플래그도 수정하지 않는다.
새 baseline이 승인 hash와 다르면 공개 출처 계보를 새 grant에 결속해야 실행할 수 있다.
GENOS 구축은 `provider=genos`, `trust_zone=internal`인 현장 프로필과 내부 모델을 사용한다.

## 기본 구축

`term_generation.build_generation`의 기본 구축은 계속 모델을 호출하지 않는다. 같은 문서·부모·역할 축에서
양 끝과 중간 좌표가 모두 존재하는 조·항·호 범위만 `EXACT_DETERMINISTIC_RANGE`로 확장한다.
복수 target은 `reference_target`에 target별 source/unit/block 범위를 저장한다. 기존
`target_source_ids`와 `reference_end`는 호환용으로 유지한다.

## 개별 실행

```bash
.venv/bin/python 06_TOOLS/pipeline.py reference-resolution prepare \
  --generation GENERATION --state REVIEW_STATE

.venv/bin/python 06_TOOLS/pipeline.py reference-resolution status \
  --state REVIEW_STATE
```

`prepare`는 선택 generation과 navigation/index/compiler/protocol 해시를 고정하고 모델을 호출하지 않는다.
문서·별표·구조가 없는 사례는 `DATA_GAP`, 폐쇄 후보가 없는 사례는 `NO_CANDIDATES`, 기존 결정론 해소는
`DETERMINISTIC`으로 분리한다. 폐쇄 후보가 있는 사례만 `CANDIDATES_READY`다.

실제 모델 실행에는 `model_binding`이 있는 별도 profile이 필요하다. 내부 binding은 `provider=genos`,
`trust_zone=internal`, `adapter_version=genos-single-send-v1`이다. 외부 binding은 위의 공개 범위
OpenRouter 프로필이다. 다른 provider fallback은 없다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py reference-resolution run \
  --state REVIEW_STATE --profile INTERNAL_QWEN_PROFILE --max-cases 32 --batch-size 8
```

모델은 제공된 `T`/`E` ID만 선택하거나 기권한다. 서버가 검증·중복 제거된 선택 수로
`0=UNKNOWN`, `1=RESOLVED`, `2+=MULTI_TARGET`을 계산한다. timeout과 전송 결과 불명은 journal에
`MODEL_UNKNOWN`으로 남고 자동 승인되지 않는다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py reference-resolution apply \
  --state REVIEW_STATE --generation GENERATION --output NEW_GENERATION
```

기본 `run`과 `apply`는 `VALIDATED` observation의 비어 있지 않은 선택을 모두 `APPROVE`한다.
빈 선택은 `UNKNOWN`으로 완료한다. 자동 승인자는 `pipeline:auto-approve`이며 원문·선택·검증·승인 이력을
보존한다. 존재하지 않는 ID·스키마 오류·전송 실패를 성공한 연결로 바꾸지는 않는다.
`apply`는 미완료 model case가 하나라도 있으면 중단한다. 원본 generation은 수정하지 않고
새 generation을 만들며, 승인 target만 `reference_end`에 넣는다.
미승인 폐쇄 후보는 `reference_candidate`와 `reference_candidate_end`에 분리한다. raw model journal은
서빙 bundle에 복사하지 않고 apply receipt와 journal 해시만 넣는다.

기존 별도 reference state를 document release에 결속하려면 `document-release build`에
`--reference-review-state REVIEW_STATE`를 명시한다. 검증된 선택은 자동 승인한다.
모델 프로필과 기존 state를 동시에 선택하지 않는다. 기존 state에 미실행/실패 사례가 있으면
`REFERENCE_REVIEW_PENDING`을 반환한다.

통합 MAIN 후보 구축 진입점도 같은 상태를 전달한다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-all \
  --run-id RUN_ID --base-generation BASE_GENERATION \
  --reference-review-state REVIEW_STATE --execute
```

`build-all`은 상태를 구조화나 용어 검토 단계에 섞지 않고 최종 `document-release build`에만 전달한다.
review state의 parent generation과 release가 다시 만든 `serving-baseline/generation`은 manifest와 navigation
해시가 정확히 같아야 한다. 따라서 review는 같은 원문 선택·검토 사전·컴파일러로 만든 결정론 baseline에서
준비해야 하며, 입력이 달라졌으면 state를 재사용하지 않고 새 경로에서 다시 `prepare`한다.

## 검증과 롤백

- overlay는 부모 v4/v5 schema와 scope contract를 보존한다. v2/v3 부모만 v4로 올린다.
- `reference-resolution-apply.json`, navigation manifest, release receipt가 parent index와 review state를 결속한다.
- 활성화는 기존 `document-release activate --confirm-main`의 별도 CAS 단계다.
- 오류 시 이전 release pointer로 롤백한다. review journal과 실패 generation은 감사 목적으로 보존한다.
- 계약 테스트 통과는 모델 의미 정확도나 현장 GENOS 성능을 인증하지 않는다. 실제 Qwen 비교는 별도 ADR에서
  첫 호출 전에 기준과 holdout을 동결한다.
