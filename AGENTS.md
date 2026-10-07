# 8-AGENT 작업 가이드

**MAIN = 용어집 구축·갱신을 공통 기반으로, Document Ingestion(데이터 입력 → 구조화) → 문서–용어 연결 → 용어·정의·명시 참조 색인 → 용어 기반 RAG → 피드백 루프**다.
전체 단계의 책임·계약·현재 연결 상태는 [ARCHITECTURE.md](00_SYSTEM/ARCHITECTURE.md)의 MAIN 정의를 따른다. 로컬 RAG 릴리스와 그 활성 포인터는 MAIN의 서빙 부분이며 전체 MAIN을 대신하지 않는다.
목표는 **재현 가능한 전체 파이프라인에서 실험을 분기하고, 검증한 결과를 MAIN에 반영하는 것**이다. 최종 서빙 환경은 망분리 GENOS다.

## 신규 외부 실험 모델

2026-09-30 사용자 변경에 따라 ADR-0583 이후 신규 외부 실험의 기본값은
**Qwen3.8 / qwen/qwen3.8-27b**다. OpenRouter Parasail FP8 단독,
reasoning effort none, fallback 없음으로 고정한다. 정본은
`00_SYSTEM/EXPERIMENT_MODEL_POLICY.json`, 공통 호출은
`lawrag.research.experiment_client.ExperimentClient`다. 이전 Gemma 기본 정책과
완료된 기록은 역사적 정본으로 보존한다. 로컬 공개 RAG 활성 릴리스는
`investigation-control-v6-20261007-r1`(포인터 generation 43)이며 선택 정본은
`01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`이다. GENOS 내부 모델·배포는 별도다.

### 이전 정책 기록

2026-09-23 사용자 지시에 따라 ADR-0538~0581 신규 외부 실험의 기본값은 **Gemma / google/gemma-4-31b-it**였다.
ADR-0582는 예약 후 사용자 변경으로 실제 공개 사례 호출에 Qwen3.8을 명시적으로 사용한 전환 사례다.
정본은 [EXPERIMENT_MODEL_POLICY.json](00_SYSTEM/EXPERIMENT_MODEL_POLICY.json), 공통 호출은
`lawrag.research.experiment_client.ExperimentClient`다. OpenRouter Parasail FP8과 thinking off를
고정하며 `.env`의 `OPEN_ROUTER`를 읽되 키는 출력·기록하지 않는다. 생성·VLM·중간처리·평가에
적용하며 다른 모델/provider 자동 fallback은 없다. 이전 Qwen·Gemini·Haiku 완료 기록은 보존한다.
GENOS 내부 모델·활성 MAIN 릴리스는 별도이며 외부 Gemma 결과를 현장 성능으로 간주하지 않는다.

## 작업을 시작할 때

- 요청과 관련된 아래 진입점부터 읽고, 필요한 문서·코드만 따라간다. 파일명·날짜·검색 결과만으로 현행 구현을 정하지 않는다.
- 대상 환경, 실제 실행 명령/API, 선택된 코드·데이터 세대, 호출되는 함수와 산출물의 소비자를 확인한 뒤 수정한다.
- 설계상 목표, 현재 작업 코드, 선택된 릴리스, 현장 검증 결과를 구분한다. 작업 코드 수정만으로 실행 중인 릴리스가 바뀌었다고 보고하지 않는다.
- 문서와 구현이 다르면 실제 연결 상태와 차이를 밝힌다. 미연결 기능·과거 실험을 현행 기능으로 설명하지 않는다. `research`·보관 경로도 실제 의존성이 있으면 사용 중이므로 이름만 보고 삭제하지 않는다.

| 작업 | 먼저 볼 곳 |
|---|---|
| 전체 MAIN·단계 책임·엔진 연결 | [ARCHITECTURE.md](00_SYSTEM/ARCHITECTURE.md) → [PIPELINE.json](00_SYSTEM/PIPELINE.json), [WORKSPACE.json](00_SYSTEM/WORKSPACE.json) |
| 실행·서빙 경로 | [service.py](service.py), [파이프라인 CLI](06_TOOLS/pipeline.py); 선택된 릴리스/세대의 manifest와 코드까지 확인 |
| 데이터 추가·재구축 | [데이터 안내](01_DATA/README.md), [DATA_MODEL.md](00_SYSTEM/DATA_MODEL.md), [LEGAL_SCHEMA.json](00_SYSTEM/LEGAL_SCHEMA.json) |
| 실험·품질 비교·MAIN 승격 | 아래 실험 절차와 연결된 두 표준 문서 |
| 용어집 구축·정의·관계·수집 재개 | [용어집 파이프라인](07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_ALIGNMENT.md) → `pipeline.py glossary`; 목록 완료와 정의·관계 수집 완료를 구분 |
| 후속 작업·실험 아이디어 | [백로그](07_DOCS/BACKLOG.md); 등록과 실제 실행을 구분 |
| GENOS 관련 모든 질문·작업 | [GENOS.md](GENOS.md)를 먼저 읽고, 질문별 출처만 추가로 읽기 |
| 법령 해석·규정 적용 | [위키 인덱스](01_DATA/wiki/wiki/index.md)로 해석 지식을 찾고, 적용 대상의 원문·버전으로 검증 |

## 파이프라인과 구조 변경

- 전체 흐름의 단계별 입력·출력·스키마·실행 순서를 명시한다. 모듈은 나누되, 한 실행 명세로 어떤 경로를 재현하는지 추적할 수 있게 한다.
- 새 기능은 담당 단계, 호출 진입점, 산출물 소비자, 필요한 설정과 검증 방법을 함께 연결한다. 기존 연결을 확인하지 않고 별도 실행기·중복 파이프라인을 늘리지 않는다.
- `PIPELINE.json`의 선언과 실제 CLI/API 배선을 대조한다. 비어 있거나 이행 중인 단계는 미구현/미연결 상태로 표시하고, 파일이나 문서가 있다는 이유로 완료 처리하지 않는다.
- 단계 내부 구현은 입력·출력 계약을 유지하며 교체한다. 계약 변경 시 소비자·스키마 버전·데이터 이행·영향받는 하위 단계의 재구축 범위를 함께 다룬다.
- 현행 원문·용어 RAG 계약은 `DATA_MODEL.md`와 `term-runtime-v1.schema.json`을 따른다. `LEGAL_SCHEMA.json`의 구 의미 스키마는 폐기 이력이며 신규 생성·RAG에서 사용하지 않는다. 용어집 검토는 `GLOSSARY_SCHEMA.json`을 따른다.
- 경로는 `lawrag.platform.workspace`의 논리 root ID로 해결한다. 새 최상위 디렉터리는 `NN_UPPERCASE` 형식을 따른다. 활성화·이행은 workspace의 receipt와 선택 세대를 확인한다.
- 원문 근거·버전·감사·롤백·접근권한을 보존한다. 기존 작업 변경과 완료된 실험·릴리스 이력은 덮어쓰지 않는다.

## 실험 → 검증 → MAIN

실험·평가·A/B·ablation·probe·holdout·replay·regrade 또는 모델/프롬프트/검색 효과 비교를 할 때만 다음 두 문서를 **끝까지 읽고** 따른다.
단순 문서 정리, 읽기 전용 진단, 일반 단위 테스트는 새 실험으로 취급하지 않는다.

- [EXPERIMENT_AGENT_PROMPT.md](04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md)
- [STANDARD.md](04_EXPERIMENTS/LEGACY_ADR/STANDARD.md)

1. 진행 중인 동일 scope의 reservation을 먼저 확인한다. 실험을 위한 구현 수정·첫 호출 전에 `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py new --adr-root 04_EXPERIMENTS/ADR`로 ADR을 선점한다. 생성된 owner·task/session·시각·상태·append-only 이벤트를 보존한다.
2. 기준 전체 파이프라인과 정확한 부모 `experiment_id/arm_id`를 정한다. 가설·성공 기준·허용 회귀·평가 데이터·arm·run과 코드/데이터/스키마/프롬프트/모델/설정 버전을 결과 확인 전에 동결한다.
3. 후보는 표준의 snapshot·register·freeze 절차로 격리한다. 변경하지 않은 단계도 기준 버전에 결속하고, 후보가 운영 registry나 기본 경로에서 자동 선택되지 않게 한다. Git 브랜치만으로 데이터·모델·실행 계보가 고정되었다고 보지 않는다.
4. 같은 조건에서 기준과 후보를 비교하고 변경 단계의 계약·하위 단계 연결·전체 결과를 확인한다. 실제 backend/model ID·입출력·사용량·지연·산출물 경로를 남긴다. offline evaluator는 표준의 역할별 allowlist를 따르며 제품 context나 답변을 바꾸지 않는다.
5. 결과를 본 뒤 만든 후속 후보·재실행·재채점은 새 ADR로 남긴다. 완료된 arm만 부모로 쓰고, 여러 결과를 합치면 새 ADR의 `merged_from`에 정확한 부모와 채택/제외·충돌 해결·롤백 기준을 기록한다. 단순 의존 관계는 `relationships`로 남긴다.
6. 완료 전 stable runner의 `adr_structure.py validate --final`과 `graph` 검사를 수행한다. 표준의 과거 `scripts/`·`docs/adr` 예시는 현행 runner·ADR 경로로 해석하며 옛 디렉터리를 재생성하지 않는다.
7. Accepted·out-of-sample·`decision_eligible=true`·complete인 arm만 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py`의 hash 고정 plan과 명시적 `--confirm-main` 절차로 승격한다. 코드·데이터 세대와 apply/rollback receipt를 보존하고 롤백 경로를 둔다. 기존 품질 우회를 새 실험의 통과 근거로 재사용하지 않는다.

Git main 병합, ADR merge, 데이터 CURRENT 변경, 제품 MAIN 승격, GENOS 리비전 배포는 각각 별도 상태다. 어느 상태까지 완료했는지 정확히 보고한다.

### 개발 연속성과 실제 MAIN 배선 — 사용자 지시 2026-10-06

- 기존에 개발한 기능 위에서 이어서 개발한다. 실험 후보에만 있는 수정과 현재 MAIN 작업 코드의 차이를 먼저 대조하고, 필요한 수정은 기존 개발 경로에 통합한다. 후보 snapshot 전체를 작업 코드에 덮어써 다른 최신 수정들을 잃지 않는다.
- 후보에서 성공한 기능을 작업 코드·활성 릴리스의 기능으로 설명하지 않는다. 특히 검색/정렬 정책, 선택 도구, 행동·이유 체인, 복귀/재개, 답변 소비자의 실제 배선을 코드와 해시로 확인한다.
- 사용자가 전체 구현과 MAIN 반영을 요청한 작업의 완료 범위는 통합 코드 작성 → 동일 코드 검증 → MAIN 배선/승격 → 선택 포인터 확인 → 실제 로컬 서비스 진입점 확인까지다. 설계 요청에서는 이 전 과정을 설계에 포함한다. 실험 격리·품질 기준·승격 계약은 유지하며, 미충족 단계는 완료로 보고하지 않는다.
- 완료 기록에는 작업 코드, 검증 후보, 선택 릴리스의 코드/프로필/데이터/검색 정책 지문을 연결하고 실제 서비스에서 선택한 실행 binding을 남긴다. 로컬 MAIN 반영과 GENOS 현장 반입·배포·검증은 별도로 기록한다.

### 판단 오류와 저장공간 — 사용자 지시 2026-10-07

- 실험 질문의 세부 답변이 전부 맞아야 MAIN에 반영하는 것은 아니다. 일반화 부족과 판단 미스는 별도 기록하고 후속 실험으로 개선한다. 세부 의미 채점 실패만으로 MAIN 반영을 자동 차단하지 않는다.
- 인용·권한·코드/데이터 해시·상태 보존·실제 서빙 연결의 심각한 문제는 계속 검증한다. 새 판정 기준은 후속 ADR의 호출 전에 동결하며, 이전 실험의 기준과 결과를 소급 변경하지 않는다.
- 저장공간 사용을 최소화한다. 같은 해시의 읽기 전용 원문·캐시는 공유하고, 원시 기록은 무손실 압축과 해시·복원 방법으로 보존한다. 본문·모델 입출력·전체 회수 목록을 보고서마다 반복 복사하지 않는다. 원본 데이터와 실패 이력은 임의 삭제하지 않는다.

## 데이터와 법률 근거

- 새 데이터는 데이터 안내의 RAW 반입·검증 경로로 넣는다. 출처·문서 ID·버전·해시·공개/내부 구분·실제/모의 구분을 남기고, 임의 폴더의 최신 파일을 자동 선택하지 않는다.
- 외부·GENOS 내부 생성 데이터는 같은 `DatasetPackage` 계약을 사용하고 `SourceSet`이 명시적으로 조합한다. 합성으로 접근·반출 제한을 완화하지 않는다. 원문·완료 세대는 보존하고 변경은 새 세대와 계보로 남긴다.
- 규칙 기반 hint는 원문의 단서·span·명시 참조를 다룬다. LLM의 의미 추출은 검증·검토를 거칠 observation이며 추출 성공만으로 정본으로 승인하지 않는다. 근거가 부족하면 미확인 상태를 보존한다.
- 법령 원문과 해석 위키를 구분한다. 수치·인용은 해당 원문에서 확인해 원문 표기대로 쓴다. 위키 수정 시 index·log를 갱신하고 원문 불변층을 보존한다. 낡은 해석은 Outdated/Disputed로 표시한다.
- 피드백은 근거와 세대에 연결된 수정 후보로 만든다. 검증한 검색 경로를 재사용하되 과거 답변을 정답 데이터로 자동 승격하지 않는다.

## GENOS와 외부 개발 환경

- 사용자 확인(2026-10-01): GENOS 현장 실행 명령은 `python3`를 사용한다. 현장 인계 TXT에 로컬 저장소 전용 `.venv/bin/python` 경로를 넣지 않는다. 실제 `sys.executable`과 Python 버전은 현장 로그로 확인한다. 아래 WSL 로컬 개발·테스트의 `.venv/bin/python` 규칙과 구분한다.

- 현장 질의·warmup 검증은 **워크플로우 테스트 화면에서만 가능**하다. 코드서빙 직접 테스트 UI/API 실행을 요구하지 않는다. 워크플로우 Python 단계 변경은 코드 ZIP 적용·Git push와 별도로 편집기에 반영해야 한다.

- GENOS 코드 ZIP을 현장에 인계할 때 기본 실행 경로는 기존 Git checkout인 `~/DEV`에 검증한 파일을 백업 후 적용하는 방식이다. 별도 후보 폴더에만 해제하는 방식은 사용자가 명시적으로 요청한 경우에 쓴다. 실행 TXT는 첫 단계부터 지속 로그와 실패 상태를 남기고, 재실행 시 이미 적용된 파일을 안전하게 확인한다. 코드 적용과 NFS generation 생성, Git push, 코드서빙 리비전 배포는 각각 별도 상태로 확인한다.

- 환경별 사용법·모델 설정·배포 절차의 진입점은 [GENOS.md](GENOS.md)다. **현재 Codex 세션에서는 망분리 GENOS 세션·코드스페이스·서빙·내부 모델에 접근할 수 없다.** 현장 연결 확인을 재시도하지 않고 코드·반입 자료·사용자가 제공한 현장 기록으로 확인한다. 최종 GENOS 실행은 내부 LLM·임베딩을 사용한다.
- `localhost`/WSL의 로컬 개발 서버와 GENOS 현장 서버를 명시적으로 구분한다. 로컬 응답·실패로 GENOS 상태를 판단하거나 환경을 밝히지 않은 “상주 서버” 표현을 쓰지 않는다.
- 공개 법령은 외부에서 처리할 수 있다. 외부 모델 전송은 [허용 설정](08_DEPLOYMENT/CONFIG/legal-source-export.json)의 source fingerprint·문서·대상·모델 범위를 확인한다. 이 승인을 비공개 질문·계약서·증거자료·인증키로 확대하거나 immutable 반출 플래그를 바꾸지 않는다.
- 실제 내부 데이터의 처리·성능 실험은 GENOS에서 한다. 외부에서는 계약이 같은 모의 데이터를 명시적으로 사용하고, 실제 내부 데이터 품질은 현장 검증 전까지 미확인으로 보고한다.
- 현장 인계에는 코드 리비전·의존성·설정 이름·입출력 계약·실행/재개/검증/롤백 방법을 포함한다. 외부 테스트 성공과 현장 배포 성공을 구분한다.

## 개발과 완료 확인

- Git·Python·테스트·저장소 스크립트는 WSL의 `/home/jin/8-AGENT`에서 Linux 도구로 실행한다. Windows Git/PowerShell로 UNC 경로를 조작하거나 `safe.directory`로 우회하지 않는다.
- 환경 관련 작업 전에 `06_TOOLS/check_wsl_dev_environment.sh`를 실행한다. Python은 저장소 `.venv/bin/python`을 사용한다.
- 변경 범위에 맞는 계약·회귀·연결 검사를 수행한다. 완료 보고에는 무엇을 바꿨는지, 실제 확인 결과, 영향받는 실행 경로와 남은 미확인 사항을 짧게 남긴다.
