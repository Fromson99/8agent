# GENOS RAG 세대 교체 시 유지할 서빙 계약

2026-09-22 작업 코드 기준. 이 문서는 **데이터 세대 교체 때 유지할 코드서빙 설정과 검증**의 정본이다. 망분리 GENOS의 적용 결과는 현장 확인 전까지 미확인이다. 현재 구현은 `service.py`와 `00_SYSTEM/PIPELINE.json`의 `legal-rag` 기본 `legal-agent-tools-v5`를 따른다. 새 RAG 구현 버전으로 바꾸는 일은 별도 코드·계약 이행이며 이 문서만으로 자동 적용되지 않는다.

## 데이터 세대와 코드 설정

- `document-release verify`를 통과한 결과를 `document-release publish-shared --shared-root <공유 NFS 루트>`로 발행한다. 출력의 `generation_path`가 코드서빙에서 읽을 **generation 디렉터리**다. 원문·navigation·용어집·참조·manifest를 함께 검증하며 기존 세대와 `CURRENT`는 덮어쓰지 않는다.
- 코드서빙이 한 세대를 명시 선택하면 `GENOS_GENERATION=<generation_path>`를 설정한다. 이 값은 모델 설정이 아니다. 새 데이터 세대로 교체할 때 새 `generation_path`로 바꾸고 새 코드서빙 리비전을 배포한다. 절대경로의 기존 디렉터리이며 심볼릭 링크가 아니고 `manifest.json`을 읽을 수 있어야 한다.
- `GENOS_GENERATION`을 생략한 운영 방식은 `GENOS_DATA_ROOT/generations/CURRENT.json`의 해시 고정 포인터를 읽는다. `GENOS_GENERATION`이 설정돼 있으면 그 명시 경로가 포인터보다 우선한다. 현재 v5 환경 모델 결속은 두 방식 모두에 적용된다. 포인터 변경 후 서빙 프로세스를 다시 시작한다. 로컬 `ACTIVE_RELEASE` fallback을 GENOS 데이터 발행으로 오인하지 않는다.
- 모델과 RAG 출력 설정은 **코드서빙 환경**에 둔다. 워크플로우 환경은 코드서빙 주소·ID·토큰과 선택적 `TEAM_ID`를 보유하며, 답변을 다시 생성하지 않는다. 새 데이터 세대로 바꿔도 코드서빙 환경 설정은 그대로 유지하되 새 리비전에서 실제 값과 요청 결과를 확인한다.

| 코드서빙 설정 | 계약 |
|---|---|
| `SEMANTIC_LLM_BACKEND=genos` | 내부 모델 전송 선택 |
| `GENOS_BASE_URL`, `GENOS_LLM_SERVING_ID`, `GENOS_LLM_KEY` | 내부 서빙 접속. 직접 URL이면 `GENOS_LLM_URL`; 키는 비밀값으로 등록 |
| `GENOS_LLM_MODEL` | 선택. 없으면 `/models`에 단일 모델이 있을 때만 조회 |
| `GENOS_RAG_MAX_OUTPUT_TOKENS` | 선택. v5 모델 호출 **1회당** `max_tokens`; 비우면 프로필 기본 6400. 양의 정수만 허용. 큰 값(예: 80000)의 실제 수용 여부는 내부 모델에서 확인 |
| `GENOS_GENERATION` | 선택 세대의 공유 NFS `generation_path`; 모델 출력 설정과 별개 |

`GENOS_LLM_MAX_INPUT_BYTES`와 `GENOS_RAG_IMPLEMENTATION`은 현재 환경 모델 결속에 필요 없다. v5의 입력 바이트 보호값은 프로필 문맥 길이에서 코드가 계산한다. 이는 실제 모델 토큰 문맥 한도 보증이 아니다. `STRUCTURE_RECIPE_MAX_TOKENS`와 `STRUCTURE_RECIPE_REVIEW_MAX_TOKENS`는 문서 구조화 파이프라인의 별도 출력 설정이며 워크플로우 RAG에 적용되지 않는다.

기존 `LEGAL_AGENT_PROFILE`과 `LEGAL_AGENT_PROFILE_SHA256`을 둘 다 지정한 배포는 파일 프로필이 우선한다. 이 경우 환경 모델 결속과 `GENOS_RAG_MAX_OUTPUT_TOKENS`는 적용되지 않으므로, 출력 설정을 바꾸려면 새 해시 고정 파일을 만들어 배포하거나 두 파일 설정을 제거하고 위 환경 결속으로 전환한다. 로컬 frozen 릴리스는 GENOS 환경변수로 바꾸지 않는다.

## 교체 후 검증과 복구

### 세대와 fulltext 결속 E2E 게이트

코드 인계본을 배포할 때는 후보 ZIP을 실제 코드서빙 Git checkout에 반영하고
commit한 뒤, 그 checkout에서 다음 결속 게이트를 실행한다. `--code-zip`은
`CODE_MANIFEST.json`이 들어 있는 정확한 인계 ZIP이다. ZIP의 모든 파일이
Git에 추적된 checkout 파일과 바이트 단위로 같아야 하며, 미커밋 코드 변경이
있으면 실패한다. 그 checkout으로 세대 E2E와 `verify_assets`를 실행한다.
`TRANSFER` 후보 폴더의 PASS를 배포 checkout의 PASS로 옮기지 않는다.

```bash
cd -P /실제/코드서빙/Git-checkout
python3 06_TOOLS/COMMANDS/genos_release_gate.py \
  --code-zip /반입/검증한-코드.zip \
  --deploy-root "$PWD" \
  --generation '/실제/GENOS_GENERATION/절대경로'
```

`GENOS_RELEASE_GATE PASS`는 출력된 Git commit과 선택 세대의 배포 **전**
검증이다. 게이트는 Git push·코드서빙 배포·NFS 변경을 수행하지 않는다.
배포 후 실제 리비전의 commit과 generation 설정을 대조하고 원문 조회·근거
질문을 별도로 확인한다. 검증 후 commit이나 코드를 바꿨다면 게이트를 다시
실행한다. ZIP과 checkout의 차이가 있으면 해시 pin만 고치지 말고 누락된
실제 코드 파일을 반영한다.

서빙 코드를 실행할 **같은 코드 리비전과 Python 환경**에서 다음 읽기 전용 검사를 먼저 실행한다.
`--generation`은 코드서빙의 실제 `GENOS_GENERATION` 값으로 지정한다. 환경변수가
같은 셸에도 있으면 서로 다른 경로를 거절한다. 이 검사는 선택된 profile의 fulltext
binding, navigation 해시, fulltext 파일·manifest·SQLite·형태소 분석기 버전, 공유 발행
영수증의 파일 목록을 대조한다. 실패하면 health 200이나 원문 답변 테스트를 성공으로
판정하지 않는다.
단독 E2E는 navigation의 source manifest digest도 확인하지만 ZIP과 Git
checkout의 일치 여부는 위 결속 게이트가 확인한다.

```bash
python3 06_TOOLS/COMMANDS/genos_generation_e2e.py \
  --code-root /workspace --generation "$GENOS_GENERATION"
python3 06_TOOLS/COMMANDS/genos_preflight.py runtime --strict
```

새 코드의 `document-release index`는 navigation을 만든 뒤 같은 세대의 fulltext를
자동 생성·결속하고, `verify_assets`가 두 색인의 해시와 형태소 분석기 버전을 확인한다. 기존에
발행된 세대에는 소급 적용되지 않는다. 해당 세대의 구조화·용어집·navigation을 재구축하지
않으려면 아래 명령으로 별도의 불변 NFS 패키지를 만든다. 원본 세대와 영수증은 수정하지
않으며, 출력된 경로를 새 코드서빙 리비전의 `GENOS_GENERATION`에 지정한다.

```bash
python3 06_TOOLS/COMMANDS/genos_fulltext_repair.py --source-generation "$GENOS_GENERATION"
# 출력의 GENOS_GENERATION=<새 경로>를 코드서빙 환경에 지정하고 새 리비전을 배포
python3 06_TOOLS/COMMANDS/genos_generation_e2e.py --generation '<새 경로>'
```

복제·형태소 색인·SQLite 해시 검증은 큰 NFS 세대에서 오래 걸릴 수 있다. 실행 중
`FULLTEXT` 진행 로그를 확인한다. 서빙 설정의 오래된 fulltext 해시보다 새 세대
manifest의 fulltext 결속이 우선하며, 파일과 navigation 해시가 맞지 않으면 실패한다.
새 패키지의 `share-receipt.json`은 복제된 파일과 fulltext의 해시를 모두 기록한다.
`genos_preflight runtime`은 선택된 세대와 `/health`가 보고한 generation ID도 대조한다.

### 코드스페이스에서 요청별 전체 실행 기록 보기

2026-09-25 작업 코드부터 상세 JSON/TXT 작성과 live 로그 종료는 답변 반환을
기다리게 하지 않는 별도 작업이다. `request.returning`과 보고서 저장 이벤트를
구분하고, 프로세스 종료·보고서 포화 시 사본이 미완료일 수 있다.
[반환 지연 수정·사전 준비 안내](GENOS_RESPONSE_COMPLETION_20260925.md)를 따른다.

새 코드 리비전의 **코드서빙 환경**에 `GENOS_SHARED_LOG_DIR=/nfs-root/diamo/8-agent/rag-request-reports`를 설정하면 요청 한 건마다 날짜별 JSON 파일 하나를 공유 볼륨에 기록한다. 경로는 코드서빙이 쓸 수 있고 코드스페이스가 읽을 수 있는 실제 공유 경로여야 한다. 기존 `GENOS_RUNTIME_DIR`의 journal과 최종 결과는 그대로 유지한다. 워크플로우 환경이나 코드스페이스 셸에만 변수를 설정해서는 코드서빙 기록이 켜지지 않는다. 코드스페이스에서 `service.service()`를 직접 호출하는 개발 테스트에는 그 코드스페이스 프로세스에 같은 변수를 설정하면 된다. 이 직접 호출 결과를 배포된 코드서빙 응답으로 간주하지 않는다.

같은 설정으로 요청 시작 시 `<request_id>-<suffix>.log`를 먼저 만들고 처리 중 이벤트마다 즉시 append/flush한다. 날짜 디렉터리에서 `tail -f`로 실시간 상태를 본다. 이 `.log`에는 질문, 부팅·세대 확인·source store·모델 확인, 용어 색인·용어집 파일별 해시 확인·매칭 구조 준비, 원문 회수·도구 결과 요약, agent 판단·모델 응답과 최종 답변을 기록한다. 각 단계 시작/종료와 소요 시간을 표시하며, 오래 걸리는 단계는 약 10초마다 현재 단계를 heartbeat로 표시한다. 용어집은 요청 때 다운로드하지 않고 선택된 NFS 파일을 확인·연다. 요청별 파일이므로 동시 요청이 섞이지 않는다. 파일명에만 요청 ID를 사용하고 본문에는 반복되는 opaque ID와 큰 도구 JSON을 생략한다. 전체 프롬프트·도구 원본은 완료된 JSON 보고서에 남는다. 인증키는 가리지만 질문과 모델 출력이 포함되므로 내부 공유 권한으로만 보관한다. 파일 권한은 `0640`이며 NFS 쓰기가 실패해도 답변 처리는 계속하고 컨테이너 JSON 로그에 `shared_live.failed` 또는 `shared_live.write_failed`를 남긴다. 완료 후 JSON/TXT 작성은 그대로다.

2026-09-28 작업 코드의 `.log` 에이전트·모델 응답·도구 결과 블록은 JSON 대신
`판단: 핵심 근거 채택 → 찾은 것: 문서명 조문 제목 → 이유: 모델이 반환한 선택 이유`
형태의 텍스트를 쓴다. 실제 전송 view의 후보·근거 번호로 표시 이름을 찾으며,
검색 계획·근거 선별·답변 작성·검토 단계를 표시한다. 블록당 최대 6개,
항목당 180자로 줄이고 생략 수와 전체 기록 위치를 남긴다. 모델이 이유를
반환하지 않은 항목은 그 사실을 표시한다. 판단은 모델 관찰이며 법률 승인이나
서버 검증 통과를 뜻하지 않는다. 질문·최종 응답 블록, 단계 시간·오류·heartbeat,
컨테이너 JSON 로그와 원본 journal/JSON 보고서의 계약은 유지한다.
새 코드서빙 리비전부터 적용되며 데이터 재구축·워크플로우 Python 교체는
필요하지 않다. 기존 `.log`는 바꾸지 않으며 현장 적용은 미확인이다.

```bash
find /nfs-root/diamo/8-agent/rag-request-reports -type f -name '<request_id>-*.log'
tail -f /nfs-root/diamo/8-agent/rag-request-reports/YYYY-MM-DD/risk_team/<request_id>-<suffix>.log
```

2026-09-28 작업 코드부터 한국 시간의 요청 시작일 아래 `risk_team`·`financial_team`
폴더로 나누고, 같은 팀 폴더에 `질문답변.xlsx`·CSV를 갱신한다. JSON/TXT도 `.log`와
같은 파일명 줄기를 사용한다. 두 코드서빙의 공유 폴더 잠금과 기존 기록 요약은
[팀별 요청 로그와 요약표](GENOS_TEAM_REQUEST_LOGS_20260928.md)를 따른다.

`request_id`는 워크플로우 반환값이나 `workflow.request.started` 로그에 있다. 아직 돌아가는 요청에는 `run_id`가 생기기 전일 수 있으므로 먼저 `request_id`로 찾는다. 이 실시간 로그는 새 코드서빙 리비전으로 들어온 요청부터 생성되며, 과거 JSON을 `.log`로 소급 생성하지 않는다.

파일에는 요청/최종 응답, 단계별 서비스 이벤트, legal-agent journal의 이벤트 순서 `timeline`과 종료 시점 `state`가 들어간다. 모든 journal 행을 중복 없이 포함한다. `model_attempt`에는 실제 전송한 시스템·사용자 프롬프트와 수신한 모델 응답, `observation`에는 도구 요청·결과, `entity_version`과 `event`에는 판단 및 상태 변화가 들어간다. 오류로 journal이 만들어지지 않은 요청은 그 사유를 `journal.status`에 남긴다. 인증키 이름과 알려진 환경 비밀값은 가리고, 모델이 제공하지 않는 숨은 사고 과정은 기록할 수 없다. 파일은 내부 질문·원문·모델 출력까지 포함하므로 Git/외부 전송 대상이 아니다. 파일 권한은 `0640`, 새 날짜 디렉터리는 `0750`이며 현장의 umask와 공유 그룹/ACL이 코드스페이스 읽기를 허용해야 한다. 공유 쓰기에 실패해도 요청 응답은 유지하고 컨테이너 로그에 `shared_report.failed`와 오류 종류를 남긴다.

새 코드 리비전에서는 같은 파일명 줄기의 `.txt`도 만든다. JSON의 서비스 이벤트와 journal 이벤트를 시각순으로 나열하고 모델의 도구명·검색 모드·대상, `WORKFLOW_REPAIR` 오류, observation, 최종 상태를 한 줄씩 보여준다. 프롬프트·모델 응답 전체는 TXT에 복사하지 않는다. TXT도 내부 질의와 오류 문구를 포함할 수 있으므로 JSON과 같은 공유 권한으로 보관한다. TXT 기록 실패는 `shared_trace.failed`로 별도 기록하고 JSON 및 사용자 응답을 유지한다. 기존 요청에는 자동 소급 생성되지 않는다.

코드스페이스에서 같은 요청의 `run_id`를 파일명 앞부분으로 찾는다.

```bash
find /nfs-root/diamo/8-agent/rag-request-reports -type f -name '<run_id>-*.json'
python3 -m json.tool /nfs-root/diamo/8-agent/rag-request-reports/YYYY-MM-DD/<run_id>-<suffix>.json | less -S
less -S /nfs-root/diamo/8-agent/rag-request-reports/YYYY-MM-DD/<run_id>-<suffix>.txt
```

이 경로는 작업 코드 변경이므로 코드서빙에 새 리비전을 배포한 뒤 들어온 요청부터 기록된다. 기존 컨테이너 로그를 소급해 파일로 만들지 않는다.

코드서빙 컨테이너 로그는 요청의 `request_id`와 RAG의 `run_id`로 묶어 확인한다.
v5 모델 호출은 `model.attempt.started` → `model_http.started` →
`model_http.finished` 또는 `model_http.failed` → `model.attempt.received` 또는
`model.attempt.failed` 순서다. HTTP 오류에는 `http_status`, 재시도 여부,
응답 바이트 수·해시, 가능한 경우 오류 `type`·`code`·`param`과 고정된 오류 힌트가
남는다. 오류 본문, 질문, 프롬프트, 원문, 인증키는 출력하지 않는다.
`/v1/rag/ask`가 200이어도 `claim_count=0`과 `model.attempt.failed`가 있으면
근거 답변 성공으로 보지 않는다. 컨테이너 로그는 새 코드서빙 리비전 배포 후의
요청부터 생성되며 이전 요청의 journal을 로그로 소급 출력하지 않는다.

1. 새 세대의 `verify`와 `publish-shared` 영수증, 실제 `generation_path/manifest.json`, 코드서빙의 읽기 권한을 확인한다. 새 코드 리비전을 배포한 뒤 로그의 `binding.resolved`, `generation.validate`, `runtime.ready`와 선택된 세대 경로를 확인한다. 503의 본문 힌트만으로 원인을 단정하지 않고 `runtime.bootstrap.failed` traceback을 본다.
2. 워크플로우 테스트에서 `{"question":"자료 목록","use_llm":false}`로 데이터 연결을 확인한다. 이어 짧은 근거 질문에 `use_llm:true`를 보내 실제 모델 응답과 코드서빙 로그의 모델 ID·요청 상태를 확인한다. 출력 토큰 값을 크게 바꿨다면 내부 모델이 요청을 수용했는지도 확인한다.
3. 실패하면 앞서 검증한 `GENOS_GENERATION` 경로와 코드서빙 리비전·환경 설정으로 되돌려 배포한다. 공유 NFS의 이전 세대와 기존 원장은 삭제하지 않는다. 데이터 세대 선택, 코드 push, 리비전 배포, 워크플로우 성공은 각각 별도 상태로 기록한다.

새 **RAG 코드 버전**을 만들 때는 이 문서의 NFS 세대 선택, 모델 결속, 출력 토큰 설정, 소스 전용 테스트와 모델 답변 테스트를 해당 구현에 다시 연결하고 계약 테스트를 추가한다. `PIPELINE.json`의 기본 구현과 실제 `service.py` 선택 분기를 함께 확인한다.
