# GENOS — 질문과 작업의 진입점

확인일: 2026-09-11. 연결 저장소 `infocz`의 main 커밋 `7b42bc4cbf9b7ccef6dfea522d20370cedb237ce`와 현재 8-AGENT 작업 코드를 대조했다.
이 문서는 GENOS 관련 답변의 공통 기준과 자료 안내다. 현장 배포 상태나 최신 설정값을 대신하지 않는다.
출처 전체와 갱신 방법은 [GENOS_SOURCES.md](07_DOCS/REFERENCE/GENOS_SOURCES.md)를 본다.

## 1. 답변 전에 확인할 것

- GENOS 질문이면 이 파일을 먼저 읽고, 아래 표에서 해당 주제의 자료만 추가로 읽는다.
- **사용자에게 확인된 제약**: 최종 서빙은 망분리 GENOS다. **현재 Codex 세션에서는 GENOS 세션·코드스페이스·서빙 API·내부 LLM/임베딩에 접근할 수 없다.** 공개 법령은 외부 처리 가능하고 실제 내부 데이터의 처리·실험은 GENOS에서 내부 모델로 한다.
- 이 접근 불가 상태는 알려진 환경 제약이다. 문서에 주소·설정이 있더라도 현재 Codex에서 GENOS 연결 테스트·로그 조회·배포를 시도하지 않는다. 여기서는 코드·반입 자료를 대조하고 현장 실행 절차를 준비한다. 현장 확인은 사용자가 제공한 환경·버전·리비전·실행 기록에 근거한다.
- `127.0.0.1`/WSL의 **로컬 개발 서버**와 **GENOS 현장 서버**를 구분한다. 로컬 health 성공·시간 초과로 GENOS 상태를 추정하지 않는다. 환경을 밝히지 않은 “상주 서버” 표현을 사용하지 않는다.
- 모의 내부 데이터로 확인한 것은 입력 계약·연결 검증이다. 실제 내부 데이터의 품질·성능은 현장 검증 전까지 미확인이다.
- 플랫폼 사용법은 **같은 버전·같은 실행 환경의 확인 기록**, 우리 구현은 **선택된 코드/배포 리비전과 설정**을 근거로 답한다. 두 근거가 다르면 충돌을 설명한다.
- `상위 저장소의 현장 관찰`, `데모 실측`, `문서상 추정`, `우리 작업 코드`, `우리 현장 검증`을 구분한다. 다른 과제의 성공을 8-AGENT 배포 성공으로 바꾸지 않는다.
- 기존 문서의 “최신”, 파일명 날짜, 로컬 테스트 성공만으로 현장 적용을 단정하지 않는다. 과거 ZIP/패치 명령은 설치된 버전과 맞는 경우에만 안내한다.
- 이미 알려진 정보는 재질문하지 않는다. 버전/리비전/실제 호출 경로처럼 답을 바꾸는 정보가 없으면 저장소와 로그를 먼저 확인하고 필요한 항목만 묻는다. 키 값·비공개 원문은 요구하거나 답변에 복사하지 않는다.
- 답변은 결론 → 해당 환경에서의 절차 → 근거 문서/코드 → 남은 미확인 사항 순서로 짧게 쓴다.

## 2. 질문별로 읽을 자료

| 질문 | 먼저 볼 자료 | 확인할 코드/보조 자료 |
|---|---|---|
| GENOS 개념·용어·화면 | [상위 저장소 안내](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/README.md), [용어 사전](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/glossary.md) | [화면 가이드](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/genos-guide.md)는 데모 기준 |
| 버전 차이·현장 제약 | [현장 지식](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md), [버전 차이](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/version-gap.md) | [검증 범위](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/coverage-map.md); 기록된 환경/과제 확인 |
| 코드서빙·워크플로우 역할 | [역할 설명](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/codeserving-vs-workflow-design.md) | [service.py](service.py), [채팅 브릿지](08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py) |
| 코드 배포·Git·키·리비전 | [프로젝트 배포 자료](07_DOCS/REFERENCE/OPERATIONS/GENOS_CODE_SERVING_CURRENT.md) | [현장 지식](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md), [기본 의존성](requirements-serving.txt) |
| 채팅 실패·return/yield·대화 이력 | [채팅 연결](07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md) | 브릿지의 `run`, `_run_once`, `call_code_serving`; 현장 지식의 버전별 응답 규약 |
| 원문 추가·RAW·단계별 구축 | [데이터 위치](01_DATA/README.md), [4단계 구축](07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md) | [pipeline.py](06_TOOLS/pipeline.py), `lawrag.pipeline.raw_prepare`, `genos_stages` |
| ZIP → PDF·전처리기 직접 호출·NFS 경로 | [변환/NFS 현장 기록](07_DOCS/REFERENCE/OPERATIONS/GENOS_ZIP_TO_PDF_NFS.md) | 전처리기 187·NFS 경로, DRM 해제 후 DOC 1건 PDF 확보/후속 NLTK punkt_tab 누락; 전체 변환·품질은 미확인 |
| PDF 변환 장애·유지보수팀 이관 | [유지보수 요청서](07_DOCS/REFERENCE/OPERATIONS/GENOS_PDF_MAINTENANCE_REQUEST.md) | 사용자 전처리기 수정·LibreOffice 설치 불가. DOC NLTK 오류와 DOCX API 성공/PDF 미확보 분리, 기존 로그 수집 |
| 용어집과 내규·외규 통합 구축 | [통합 실행](07_DOCS/REFERENCE/OPERATIONS/GENOS_GLOSSARY_SINGLE_COMMAND.md) | [genos_all_pipeline.py](02_BACKEND/lawrag/pipeline/genos_all_pipeline.py) |
| Wikidata·FIBO·전체 용어 관계 반입 | [기본 관계 묶음](07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_KNOWLEDGE_BUNDLE.md) | `pipeline.py glossary knowledge`, `glossary_linking.project`, `GLOSSARY_PIPELINE.json.knowledge_bundle` |
| 모델 연결·JSON·임베딩 | [현장 지식](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md) | [공통 전송](02_BACKEND/semantic_runtime/genos.py), [RAG provider](02_BACKEND/semantic_runtime/provider.py), [구축 provider](02_BACKEND/semantic_runtime/genos_backend.py) |
| 문서 형식·구조화·진행률·재개 | [세부 자료 목록](07_DOCS/REFERENCE/GENOS_SOURCES.md) | 형식·선택 실행기별 자료를 읽고 옵션/출력 경로를 대조 |
| 플랫폼 지식 준비·벡터DB·Flowise | [플랫폼 RAG 런북](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/rag-runbook/RUNBOOK.md) | 현장 지식의 전처리/벡터DB 보정; 우리 SQLite 파이프라인과 별도 경로 |
| MCP·도구 호출 | [MCP 런북](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/mcp-runbook.md) | 데모 v1.9.2의 검증이며, 현재 프로젝트가 MCP를 사용한다는 뜻은 아님 |

## 3. 환경과 버전 — 서로 섞지 않는다

상위 저장소의 기록 기준이다. 현재 대상의 버전·컨테이너·리비전이 다르면 재확인한다.

| 항목 | 기록된 사실 | 우리 작업에서의 해석 |
|---|---|---|
| 플랫폼 | 데모 v1.9.1~1.9.2 / 현장 V1.8.6 | 데모 사용법을 현장에 무조건 적용하지 않는다 |
| Python | 현장 코드스페이스 3.11.15 / 워크플로우 컨테이너 3.10 기록 | 실행 위치별 호환성을 확인. 우리 코드서빙 기본 의존성 기준은 3.11.15이며 현장 이미지 확인도 필요 |
| Python 워크플로우 | 데모 v1.9.1은 JSON token/end `yield`; 현장 V1.8.6은 `{"text": ...}` dict `return` | 현재 우리 `run(data)`는 dict 반환. 오류 `000200003`이면 반환 규약부터 확인 |
| 진행 상황 | V1.8.6에서 최종 dict 반환과 워크플로우 소켓 emit 병행 사례 존재 | 우리 브릿지에 구현되었다고 가정하지 않는다. `main_socketio`는 해당 워크플로우 런타임의 기능 |
| 코드서빙 주소 | 현장에는 게이트웨이가 앱의 `/chat`, `/json` 등 실제 라우트를 전달한 사례 | `/chat`을 모든 앱의 정답으로 바꾸지 않는다. 배포 방식·앱 라우트·전체 URL을 대조 |
| 모델 인증 | 플랫폼 노드의 인증 주입과 Python 코드의 직접 API 호출은 다름 | 코드 호출의 URL·서빙 ID·키·모델 설정은 해당 provider가 실제 읽는 변수로 지정 |
| 권한/승인 | 승인 절차 관찰; 자기 승인 가능 여부는 일부 환경 미확인 | 다른 환경의 자체승인 사례를 우리 권한으로 간주하지 않는다 |

근거: [knowledge.md](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md), [version-gap.md](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/version-gap.md), [현재 브릿지](08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py).

## 4. 우리 시스템의 GENOS 연결

MAIN은 데이터 입력·구조화·용어집 구축/연결·지식그래프·온톨로지·RAG·피드백 루프 전체다. [전체 MAIN 정의](00_SYSTEM/ARCHITECTURE.md)를 따른다. 아래 코드서빙·채팅 배선과 데이터 CURRENT는 이 중 실행/서빙 부분이며 전체 MAIN 완료를 의미하지 않는다.

```text
외부: 공개 원문 처리·실험 → 코드/공개 데이터/실행 명세 인계
GENOS 코드스페이스: 실제 내부 데이터 + 내부 모델로 구축·실험
GENOS 코드서빙: 선택한 코드 리비전 + 데이터 세대 → RAG
채팅 앱 → 워크플로우 브릿지 → 코드서빙 ELS_QUERY → /v1/rag/ask
```

- `service.py`는 `async def service(config, data)`와 로컬 ASGI factory `application()`을 제공한다. 현장 플랫폼이 어느 방식을 적재하는지 별도로 확인한다.
- 워크플로우는 입력·응답을 중계한다. 이미 RAG에서 생성한 답변을 별도 LLM으로 재생성하지 않는다. 현재 `session_id`는 추적에 쓰며 대화 이력은 저장하지 않는다.
- 코드스페이스의 직접 실행으로 로직과 내부 모델 연결을 확인할 수 있다. 게이트웨이 인증, 채팅 연결, 배포 자원 한도, 영속 볼륨은 배포 환경에서 별도 확인한다.
- 한 코드서빙 내부의 Python 모듈화는 가능하다. 서로 다른 배포가 코드·파일·패키지를 자동 공유한다는 보장은 없다. 상위 문서의 “런타임 공유 없음”은 당시 현장 관찰 범위다.
- ZIP 반입/압축 해제, 내부 Git 커밋·push, 플랫폼 리비전 배포, 실제 요청의 리비전 선택은 각각 별도 상태다. 배포 시 선택 커밋·환경변수·트래픽·워크플로우/채팅 앱 바인딩을 확인한다.
- 기존 저장소를 clone하고 이력을 보존하는 절차를 기본으로 한다. 상위 문서의 첫 push `--force`는 특정 초기화 사례이며 일반 배포 명령으로 복사하지 않는다.

### 데이터 세대 선택

현재 `service.py._resolve_binding()`의 순서:

1. `GENOS_GENERATION`의 명시된 세대 디렉터리.
2. `GENOS_DATA_ROOT/generations/CURRENT.json`이 선택한 세대.
3. 로컬 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`의 릴리스.

GENOS에서는 1 또는 2를 현장 경로로 명시하고, 준비되지 않았을 때 로컬 릴리스를 현장 정본으로 취급하지 않는다.
세대와 런타임 캐시 때문에 CURRENT 변경 후 새 프로세스가 필요할 수 있다. 실제 선택 결과로 확인한다.
데이터 파일은 코드스페이스와 코드서빙 양쪽에서 읽을 수 있는지 확인한다. 경로 문자열이 같다는 것만으로 공유·쓰기·재배포 후 보존을 보장하지 않는다.

### 서로 다른 구축 명령

| 진입점 | 목적/산출물 | 활성화 의미 |
|---|---|---|
| `pipeline.py prepare-data` | RAW 준비·입력 검증, `--apply`로 반입 | SourceSet/서빙 자동 변경 아님 |
| `pipeline.py build-data-stages` | 내규 `PDF/internal` + 외규 `RAW/<source>` → 구조화 → LLM/검토 → 임베딩, 문서별 DRAFT | `--stage structure`는 구조화·용어 연결까지; 통합 CURRENT를 선택하지 않음 |
| `pipeline.py build-all` | 전체 관계 묶음 검증 → v3 용어 검토 완료 → 관계/번역을 소비하는 `build-data-stages`; 문서별 DRAFT | 검토 미완료 시 exit 3, 문서 구축 중단. 통합 CURRENT 선택 없음 |
| `pipeline.py build-all-legacy` / `genos_pipeline.sh` | 과거 용어 ZIP + 내규·외규 + 벡터 + 통합 세대; v3 검토 미소비 | `--publish`는 GENOS CURRENT 변경. 품질 승인/로컬 MAIN 채택과 다름 |
| `service.py`의 `PIPELINE_*` | `genos_unified`의 raw/common batch 구축 | `PIPELINE_PUBLISH`는 source-only DRAFT 선택; 의미 구축 전체 완료와 다름 |

모든 명령을 하나의 동일 구현이라고 답하지 않는다. 전체 실행은 선택한 명령의 기본값과 실제 코드 경로를 확인한다.
`--check-only`도 파일/목록/계획을 만들 수 있다. “모델 호출 없음”과 “변경 없음”은 다르다.
구조화도 PDF recipe/VLM 설정에 따라 모델을 호출할 수 있다. [GENOS_RECIPE_VLM.md](07_DOCS/REFERENCE/OPERATIONS/GENOS_RECIPE_VLM.md)를 먼저 대조한다.

## 5. 모델·키·데이터 경계

- GENOS RAG는 `SEMANTIC_LLM_BACKEND=genos`를 명시한다. 현재 코드 기본값이 `anthropic`이므로 자동 선택으로 두지 않는다.
- RAG와 구축 provider의 설정 해석이 다르다. `GENOS_GATEWAY_API_PREFIX`, `GENOS_LLM_API_PREFIX`, `SEMANTIC_LLM_API_PREFIX`를 서로 바꾸어 안내하지 않는다. `/v1` 추가/제거는 실제 호출하는 함수와 게이트웨이 규약을 확인한다.
- RAG provider는 현재 `GENOS_BASE_URL`, `GENOS_QWEN_SERVING_ID`, `GENOS_QWEN_KEY`를 요구한다. 전체 모델 프로파일·직결 URL 지원은 각 provider 코드에서 확인한다.
- Git 인증, 코드서빙 API 인증, LLM 인증, 임베딩 인증, 벡터DB 인증을 구분한다. 과거 문서의 모델명/서빙 ID는 현장 당시 기록이며 현재 배정값을 대신하지 않는다.
- 적재와 질의의 임베딩 모델·버전·전처리는 일치해야 한다. 차원이 같아도 모델이 다르면 검색 품질이 무너질 수 있다. 설정 누락 시 다른 모델로 자동 대체하지 않는다.
- 내부 원문·질문·계약서·모델 출력·실제 키를 외부 실험 입력이나 지식 문서에 넣지 않는다. 공개 산출물은 출처/버전/해시를 보존하고, 모의 내부 데이터는 실제 데이터와 구분한다.
- 플랫폼 채팅 첨부, 플랫폼 벡터DB 업로드, 우리 RAW 파서의 지원 형식은 서로 다르다. V1.8.6의 다른 과제에는 `uploadFiles[].path`로 NFS 경로를 받은 기록이 있지만, 우리 `_upload_paths`와 허용 루트에 자동 호환된다고 가정하지 않는다.

용어집 의미 검토 v3는 `pipeline.py glossary review complete`가 준비·GENOS LLM 실행·새 초안 생성까지 이어서 호출한다. 개별 `review run`도 같은 내부 LLM 전용 경로다.
임베딩이나 외부 모델 fallback은 사용하지 않는다. `prepare`는 외부에서도 모델 없이 가능하고,
실제 실행·재개·초안 반영은 [용어집 운영 가이드](07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_ALIGNMENT.md)의
LLM 검토 배선을 따른다. 현재 배선은 모의 응답으로 검증했으며 현장 모델 검증은 미실행이다.

## 6. 장애 질문에 답하는 순서

| 증상 | 먼저 확인할 것 |
|---|---|
| 채팅 실패, 이용 로그 Success | 버전별 return/yield 규약, 반환 `text`, 브라우저 응답 코드, 브릿지가 반환한 실패 상태 |
| 401/403 | 어떤 요청의 인증인지, 해당 리소스 키와 호출자 허용 범위; 키를 출력하지 않음 |
| 404/405 | 코드서빙 ID, 전체 API 경로, HTTP 메서드, 리비전 환경변수. `/chat`이나 `/json`을 추측해 고정하지 않음 |
| 새 코드가 적용되지 않음 | Git 커밋 → 배포 리비전 → 트래픽 → 워크플로우/채팅 앱 바인딩 |
| health/검색 초기화 실패 | 실제 선택 세대, manifest/코드 해시, 영속 볼륨 접근, 필수 설정 |
| 검색 0건/엉뚱한 결과 | 활성 데이터·필터·적재/질의 임베딩 일치·선택 인덱스. 플랫폼 VDB라면 암호화/속성 규약도 확인 |
| 구조화/LLM/임베딩 정체 | 선택 실행기의 단계별 로그·run ID·재시도·한도·문서별 상태. 과거 실행기와 재개 옵션 혼용 금지 |
| 코드스페이스 성공, 서빙 실패 | 컨테이너 Python/의존성/메모리/파일시스템/환경변수 차이 |
| 첨부 실패 | 테마/권한 → 허용 확장자 → 수신 payload → 파일 접근 → 우리 파서 순서 |

단일 Success 표시나 `/health`만으로 실제 모델 호출·정답률·전수 구축 성공을 보고하지 않는다. 요청 ID로 워크플로우/코드서빙/모델 로그를 연결한다.
진단용으로 내부 원문·키를 통째로 echo하지 말고 필요한 키 이름·자료형·크기·오류 분류만 확인한다.

## 7. 지식 갱신

현장 확인이 생기면 `환경/플랫폼 버전/실행 위치/배포 커밋·리비전/관찰일/확인 내용/근거/미확인 범위`를 함께 기록한다.
새 정보가 기존 규칙을 대체하면 관련 항목과 질문별 안내를 함께 수정한다. “최신 패치” 절을 계속 맨 위에 쌓지 않는다.
상위 main 갱신은 출처 인덱스의 절차를 따른다. 보관본은 과거 증거로 유지하고 현재 읽을 버전은 이 파일에서 하나를 선택한다.
