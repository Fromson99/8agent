# 현재 구조화 문서에 용어집 다시 연결

2026-09-22. `Document version ID reused with changed content`로 prepare가 멈추고,
업로드한 용어집의 과거 문서 연결 대신 현재 선택 문서를 사용하려는 경우다.

`document-release --glossary-corpus-policy replace`는 원본 용어집을 보존하고 새 초안에서
과거 corpus_document, corpus_definition, occurrence와 문서 근거에 의존한 검토·의미 후보를
제거한다. 현재 통합 원문에서 정의·출현 위치·해시를 다시 계산한다. 사전 출처의 용어,
정의와 공식 관계를 유지하며, 독립적인 용어 검토는 근거가 정확히 같은 경우 재사용한다.
삭제한 연결의 부모 해시·문서 목록·건수는 새 report.json의 document_update에 남는다.
실제 법적 의미 적용이 자동 승인되는 것은 아니다. 기본 append의 충돌 검사는 유지한다.

## 입력과 출력

- 기존 구조화: `LOGS/full-80k-002/structure-selection.json`과 연결된 STRUCTURE 캐시.
- 용어집: GLOSSARY_PIPELINE.json의 current_draft 또는 명시적인 --glossary-dir.
- 새 작업: `full-80k-002-linked`. 기존 성공분 2,105건·제외 21건은 현장 사진 기준이다.
- 새 산출물: `TERM_RELEASES/full-80k-002-linked/{sources,glossary-draft,review,glossary-reviewed,serving}`.
- 기존 구조화·RAW·용어집·실패 기록·활성 포인터는 변경하지 않는다.

## 실행

기존 DEV에서 패치를 적용한 뒤 실행한다. 아래 경로는 모두 DEV 기준 상대 경로다.
코드 해시와 연결 정책이 달라지므로 기존 `full-80k-002-success`를 덮어쓰지 않고
새 run ID를 사용한다. select/prepare의 재검증·통합은 파일 작업이며 구조화 모델을 호출하지 않는다.

```bash
cd ~/DEV
python3 06_TOOLS/pipeline.py document-release select --from-run-id full-80k-002 --run-id full-80k-002-linked --allow-incomplete --reason '완료된 구조화를 재사용하여 새 용어집을 현재 문서에 연결; 실패 문서는 보류'
python3 06_TOOLS/pipeline.py document-release prepare --run-id full-80k-002-linked --glossary-corpus-policy replace
```

PREPARED가 나오면 기존 GENOS_LLM_SERVING_ID, GENOS_LLM_KEY, GENOS_BASE_URL 설정을
같은 터미널에서 사용한다. MODEL은 자동 조회할 경우 생략한다. 새 키나 별도 모델 종류 변수는 필요 없다.

```bash
python3 06_TOOLS/pipeline.py document-release review --run-id full-80k-002-linked --glossary-corpus-policy replace --max-review-jobs 100
```

REVIEW_PENDING이면 같은 review 명령으로 다음 100개를 이어서 검토한다. 완료된 작업은 다시 호출하지 않는다.
REVIEWED이면 다음을 실행한다. PARTIAL은 의미 미확정/보류가 남았다는 뜻이며 승인으로 바꾸지 않는다.

```bash
python3 06_TOOLS/pipeline.py document-release index --run-id full-80k-002-linked --glossary-corpus-policy replace
python3 06_TOOLS/pipeline.py document-release verify --release 01_DATA/TERM_RELEASES/full-80k-002-linked
```

완성된 RAG 입력 세대는 `01_DATA/TERM_RELEASES/full-80k-002-linked/serving/generation`이다.
서빙에서 이 세대를 명시 선택하는 작업은 별도이며 CURRENT는 자동 변경되지 않는다.
상태 확인은 `document-release status --run-id full-80k-002-linked`로 한다.
코드 롤백은 반입 패치의 백업 경로로 수행하고 새 초안은 감사용으로 보존한다.

## 검증 범위

로컬 모의 문서와 모의 GENOS 응답으로 해시 충돌, 오래된 좌표/누락 문서 제거, 독립적인
용어 검토 재사용, 원본 불변, 정책 고정, prepare→review→index→verify를 검사한다.
GENOS 현장 설치·2,105문서 처리·실제 Gemma 검토 품질은 현장 실행 전 미확인이다.

## 의미 비교를 보류하고 색인만 생성

사용자가 현재 정의 간 의미 검토를 생략하도록 선택한 경우, 준비된 입력을 바로 색인한다.
다음 옵션은 추가 패치가 필요하며 이전 rebind 패치만 설치한 코드에는 없다.

```bash
python3 06_TOOLS/pipeline.py document-release index --run-id full-80k-002-linked --skip-meaning-review --skip-review-reason '정의 간 의미 비교를 보류하고 원문·용어 연결 색인만 생성'
python3 06_TOOLS/pipeline.py document-release verify --release 01_DATA/TERM_RELEASES/full-80k-002-linked/serving-unreviewed
```

`select/prepare/review`를 재실행하지 않는다. 준비된 원문·용어집 및 선택 영수증의 결속을
검증하고 기존 `term_generation.build_generation`으로 생성한다. 구조화·검토 모델 호출은 없다.
이미 시도한 검토 및 부모 계획은 변경하지 않는다. 이 실행은 검토 결과를 소비하지 않으며
원문 정의·표기 출현·공식 관계는 유지한다. 문서 간 정의를 같은 의미로 승인하거나 합치지 않는다.

결과는 `TERM_RELEASES/full-80k-002-linked/serving-unreviewed/serving/generation`이다.
`document-release-unreviewed-v1` 영수증은 `review_status=SKIPPED`,
`canonical_approval=false`, `quality_certified=false`, 생략 사유와 원본 선택 계보를 기록한다.
선택 범위 2,105건과 제외 21건은 계속 부분 범위로 남는다. CURRENT는 바꾸지 않는다.
일반 index의 검토 완료 조건과 일반 verify-glossary는 유지한다.

재실행은 같은 명령을 사용한다. 성공 결과를 재사용하며, 입력/코드/사유가 달라지면 중단한다.
이 패치는 document_release.py 코드 해시를 변경하므로 예전 작업의 일반 review/build 재개와
혼용하지 않는다. 나중에 예전 검토를 재개하려면 패치의 코드 백업으로 원복하거나 새 작업으로
입력을 결속한다. 기존 검토 SQLite와 구조화 결과는 보존되어 있다.
