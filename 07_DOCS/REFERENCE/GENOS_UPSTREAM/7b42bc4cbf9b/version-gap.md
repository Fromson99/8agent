> 출처 보관본: infocz/main @ `7b42bc4cbf9b7ccef6dfea522d20370cedb237ce`의 `docs/genos/version-gap.md`.
> 날짜·환경·과제별 관찰 기록이며 현재 8-AGENT의 실행 지침이 아닙니다. 먼저 [GENOS.md](../../../../GENOS.md)를 읽습니다.
> 본문은 보존하고 이미지·미포함 자료 링크만 원본 커밋으로 연결했습니다.

# GenOS 버전별 기능 매트릭스 — 실환경 V1.8.6 갭

작성일: 2026-08-13 / 소스: https://genos-docs.gitbook.io (llms.txt 전수 조사). 데모(**v1.9.1~1.9.2** — 가이드·런북 본문은 v1.9.1 실측, MCP 런북·용어 사전은 v1.9.2 실측. [`README.md`](README.md)) 실측과 다른 축의 근거 — **문서 기준** 기능 유무 지도다.

> **⚠️ 이 문서의 "X / 사용 불가 예상"은 문서 트리 diff에서 나온 추정이다.** 9/1 정식 투입으로 V1.8.6
> 실물을 보기 시작했다 — **실측으로 확정된 항목은 아래 [§②-0](#-0-실측-덮어쓰기-2026-09-01-정식-투입-1일차)에 모았고,
> 그 표가 §②보다 우선한다.** 나머지는 계속 [`../onprem/day1-runbook.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/day1-runbook.md)
> Phase 0의 버전·메뉴 정찰에서 §②를 체크리스트 삼아 확인하고 §②-0에 덮어써라.
> **self-approve 정책**과 **크레딧 시스템 탑재 여부**는 9/1에도 기록이 남지 않았다 — 문서로는 끝까지
> 판정이 안 되는 항목이라 현장 확인이 유일한 경로다.
>
> 📌 **첫 실측의 교훈**: 이 문서가 예측하지 **못한** 축에서 최대 갭이 나왔다. §②는 "기능의 유무"를
> 다루는데, 9/1의 최대 갭은 **있는 기능의 호출 규약이 뒤집힌 것**(워크플로우 응답)이었다.
> 기능 존재 여부만 체크하고 넘어가지 말고 **규약은 최소 코드로 직접 찍어 볼 것**.

## 조사 방법·한계 (먼저 읽을 것)

- 현재 llms.txt 인덱스는 **v1.7.5.1 ~ v1.9.0 버전 트리 + 무버전 최신 트리(v1.9.1 표기)**를 제공한다. 버전별 문서는 `https://genos-docs.gitbook.io/default/{버전}/{경로}.md`, 최신(v1.9.1)은 버전 없이 `default/{경로}.md`.
- **v1.7.5.1 이전(v1.3.3~v1.7.4) 트리는 현재 삭제됨.** `v1.4.0/...` 등은 HTTP 200을 반환하지만 본문이 "Page Not Found"다 (직접 확인). 따라서 v1.7.5.1 이전의 최초 등장 시점은 **문서 근거 없음** — 아래 표의 "≤ v1.7.5.1"은 "현존 문서상 v1.7.5.1 트리부터 이미 존재"라는 뜻이며 실제 도입은 더 이전일 수 있다.
- 버전 트리 간 페이지 집합을 diff하고(전 버전 165±10페이지), 핵심 페이지는 원문(.md)을 받아 내용 비교로 검증했다. 원문 캐시는 외부망 로컬에 보관(동국).
- 인덱스 자체에 노이즈가 있다: v1.8.7 트리는 A2A/MCP노출/Spring AI MCP/AI회의록 페이지가 인덱스에서 빠졌다가 v1.9.1에서 재등장(문서 큐레이션 이슈로 보임). v1.8.6 트리에는 모두 존재하므로 삼성 환경 판단에는 영향 없음.
- 릴리즈 노트 페이지는 존재하지 않음(문서 근거 없음). "최초 등장"은 전부 문서 트리/내용 기준.

URL 표기: 아래 근거 링크는 v1.8.6 트리 기준. 다른 버전은 경로의 `v1.8.6`만 교체하면 된다.

## ① 기능 × 최초 등장 버전 매트릭스

| 기능 | 문서상 최초 등장 | v1.8.6 | 근거 |
|---|---|---|---|
| **코드 서빙** (uvicorn 시작 커맨드 예시 `uvicorn main:app`; "FastAPI"라는 단어 자체는 가이드 본문에 없음) | ≤ v1.7.5.1 | O | [create_code_serving](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/development/code_serving/create_code_serving.md) |
| 코드 서빙 게이트웨이 `/api/gateway/code_serving/{id}/json` + 인증키 Bearer 호출 | ≤ v1.7.5.1 | O | [usage_code_serving](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/development/code_serving/usage_code_serving.md) (v1.7.5.1 원문에도 동일 curl 예시 확인) |
| FastAPI 앱 ↔ GenOS 채팅 연동 가이드 ("파이썬 코드 기반 FastAPI 앱과 GenOS 채팅 연동하기") | ≤ v1.7.5.1 | O | [mocking-flowise](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/workflow/mocking-flowise.md) |
| 코드 서빙 이관 / 컨테이너 서비스 | v1.8.5 | O | [migration](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/development/code_serving/migration.md), [container_service](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/development/code_serving/container_service.md) |
| 코드 서빙 프로모션 | v1.8.8 | **X** | `v1.8.8/basic-tutorials/guides/development/code_serving/promotion_code_serving.md` |
| **코드 스페이스** (볼륨 할당량/공유 볼륨 포함) | ≤ v1.7.5.1 | O | [code_space](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/development/code_space.md) |
| **MCP 도구/서버 만들기** (+ 웹크롤링/시각화 예시) | ≤ v1.7.5.1 | O | [mcp-tool-server](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/mcp/mcp-tool-server.md) |
| 워크플로우를 MCP 도구로 노출 | v1.8.3 | O | [workflow/mcp](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/workflow/mcp.md) |
| Spring AI MCP 서버 연동 | v1.8.3 | O | [spring-ai-mcp](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/mcp/spring-ai-mcp.md) |
| A2A 에이전트 (워크플로우를 A2A로 노출) | v1.8.3 | O | [a2a](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/workflow/a2a.md) |
| MCP 도구 카탈로그 | v1.9.0 | **X** | `v1.9.0/basic-tutorials/guides/mcp/mcp-tool-catalog.md` |
| **가드레일** 필터 생성/적용 + 탐지 로그 | ≤ v1.7.5.1 | O | [guardrail_guide](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/guardrail/guardrail_guide.md), [detect-log](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/guardrail/detect-log.md) |
| 가드레일 **플러그인** (워크플로우·LLM 서빙의 플러그인 탭에서 적용, 저장 후 재배포 필요) | ≤ v1.7.5.1 | O | guardrail_guide 본문: "가드레일 필터는 워크플로우와 LLM 서빙에 적용할 수 있으며, 플러그인 탭에서 지원합니다" |
| **워크플로우 = Flowise 기반** (Flowise 2.2.3 / 3.0.0 병행, ChatMNC 노드 등) | ≤ v1.7.5.1 | O | [workflow](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/workflow.md), [multi_agentflow_flowise300](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/workflow/create_multi_agentflow/multi_agentflow_flowise300.md) |
| Agentflow 3.0 (Flowise 3.0.0 신규 캔버스) | ≤ v1.7.5.1 | O | [agentflow3-1-intro](https://genos-docs.gitbook.io/default/v1.8.6/flowise-nodes/components/agentflow3-1-intro.md), agentflow3-2-rag/3-multiturn/3-4-faq |
| 커스텀 워크플로우 **전처리 코드(Python)** | ≤ v1.7.5.1 | O | [preprocess](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/workflow/preprocess.md) |
| 워크플로우 API **`run/v2`** (JWT + 인증 키, 스트리밍 포함) | ≤ v1.7.5.1 | O | [api/workflow](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/api/workflow.md) — v1.7.5.1 원문에도 `run/v2` 확인 |
| 워크플로우 상세 **인증 키 탭** (만료 일자 등) | ≤ v1.7.5.1 | O | 위 api/workflow 문서 "인증 키 탭에서 인증 키 생성" |
| 워크플로우 **APIM (API Monitoring) 탭** | ≤ v1.7.5.1 | O | 위 api/workflow 문서 "워크플로우 APIM 모니터링" 섹션 (v1.7.5.1 원문에도 존재) |
| **파일 기반 대화 플러그인** (워크플로우 상세 > 플러그인 탭, 파일/이미지 업로드 대화) | ≤ v1.7.5.1 | O | [plugin](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/workflow/plugin.md) |
| **파일 업로드 전처리**: 음성 mp3/m4a/wav → 내부 배포 `whisper-large-v3` STT | ≤ v1.7.5.1 | O | [preprocess_for_upload](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/workflow/preprocess_for_upload.md) |
| 파일 업로드 전처리: **csv/xlsx** (csv=싱글시트, xlsx=멀티시트, `[DA]` 접두어로 데이터분석 에이전트 라우팅) | ≤ v1.7.5.1 | O | 동일 문서 |
| **채팅 앱 생성** + 테마 선택(문서 뷰 / 챗봇 / 검색 바 타입) | ≤ v1.7.5.1 | O | [dev-chat](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/application/dev-chat.md) |
| 채팅 "**배포까지 한번에 진행하기**" 버튼 (배포 신청까지 자동) | ≤ v1.7.5.1 | O | 동일 문서 (v1.8.6~v1.9.0 원문 동일 확인) |
| 채팅 앱 **CoT 태그** 설정(열림/닫힘 태그 쌍) | **v1.9.1 (최신 문서)** | **X (문서상)** | [최신 dev-chat](https://genos-docs.gitbook.io/default/basic-tutorials/guides/application/dev-chat.md) — v1.8.6/v1.8.7/v1.8.8/v1.9.0 원문에는 CoT 언급 0회 |
| 채팅 앱 테마 명칭 "**챗봇형/문서형**" + 부정 피드백 수집 + 음성 입/출력(STT/TTS/TTS 스트리밍) 설정 | v1.9.1 (최신 문서, 채팅 앱 리뉴얼) | **X (문서상)** | 동일 문서. 단 v1.8.6에도 [SST/TTS 활용하기](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/application/dev-chat/sst-tts.md) 페이지는 별도 존재 → 음성 기능 자체는 v1.8.6에 있음 |
| **모델 서빙** 6유형: LLM / VLM / **임베딩 / 리랭크** / I2I / T2I | ≤ v1.7.5.1 | O | [model-serving](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/llm/model-serving.md) (v1.7.5.1 원문 동일) |
| 모델 서빙 **인증키 발급** + 게이트웨이 `/api/gateway/rep/serving/{serving_id}` (OpenAI 호환) | ≤ v1.7.5.1 | O | [api/llm](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/api/llm.md) (v1.7.5.1 원문에 동일 endpoint 확인) |
| 모델 서빙 스케일 아웃 / 멀티테넌트 서빙 | ≤ v1.7.5.1 | O | [serving-scaleout](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/llm/serving-scaleout.md), [multitenancy](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/serving/multitenancy.md) |
| 외부 API 모델 추가 (모델 서빙에 외부 LLM API 등록) | v1.8.4 | O | [model-serving/api](https://genos-docs.gitbook.io/default/v1.8.6/basic-tutorials/guides/llm/model-serving/api.md) |
| **배포 승인 절차** (승인 권한자가 승인해야 Online; 승인 > 승인 메뉴) | ≤ v1.7.5.1 | O | model-serving 문서 "승인 권한을 가지고 있는 사용자가 배포 승인을 해주어야 배포가 완료됩니다" |
| **self-approve(본인 승인) 정책 언급** | — | — | **문서 근거 없음** (IAM 정책 문서·서빙 문서 전체에서 미발견) |
| **서비스 라우터** (가중치/카나리/Shadow/서킷브레이커, LLM·VLM·Rerank·Embedding·코드서빙 대상) | **v1.8.7** | **X** | [v1.8.7 service-router](https://genos-docs.gitbook.io/default/v1.8.7/advanced-tutorials/guides/serving/service-router.md) — v1.8.6 트리에 페이지 없음, "라우터" 언급 0회. 참고: v1.9.1 인덱스에서는 다시 빠져 있음(무버전 URL 404) |
| 크레딧 시스템 | v1.8.0 | 부분 근거 | `v1.8.0/credit/manual.md` — v1.8.0 트리에만 인덱스됨(이후 트리에서 제외). v1.8.6 탑재 여부 문서로 단정 불가 |
| AI 회의록 서비스 | v1.8.4 | O | [chat-use/ai](https://genos-docs.gitbook.io/default/v1.8.6/getting-started/application-use/chat-use/ai.md) |
| 태스크플로우 (빌더/발화/슬롯/액션/플로우) | ≤ v1.7.5.1 | O | [taskflow/manual](https://genos-docs.gitbook.io/default/v1.8.6/taskflow/manual.md) |

## ②-0 실측 덮어쓰기 (2026-09-01 정식 투입 1일차 ~ **9/7 갱신**)

아래 §②는 **문서 트리 diff에서 나온 추정**이다. 실물을 직접 본 항목만 여기에 실측으로 덮어쓴다.
전체 기록: [`../onprem/day1-runbook.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/day1-runbook.md) "Day-1 실행 결과" · [`knowledge.md`](knowledge.md).

| 항목 | 문서 기반 추정 | **9/1 실측** |
|---|---|---|
| 코드 서빙 게이트웨이 경로 | `/api/gateway/code_serving/{id}/**json**` | ❗ **다름** — **FastAPI 경로가 그대로 프록시**된다: `…/code_serving/<서빙ID>/**chat**`. 추정이 틀린 게 아니라 **문서 예시가 특정 엔트리 이름이었을 뿐**으로 읽힌다 |
| 워크플로우 Python 단계 응답 규약 | (문서로는 판정 불가 — `run/v2` 스트리밍 지원만 확인) | ❗ **데모 v1.9.1과 정반대**: **dict `return`** (`{"text": …}`). generator yield는 `000200003` 실패 → [`knowledge.md` §★](knowledge.md) |
| 파일 기반 대화 플러그인 | 사용 가능 | ✅ 확인 (텍스트/txt e2e). 오디오 STT·`.xlsx` 직접 업로드는 **미확인** |
| 채팅 앱 "배포까지 한번에 진행하기" | 사용 가능 | ✅ 확인 |
| 배포 승인 워크플로 | 사용 가능 | ✅ 절차 정상 진행. ⚠️ **self-approve 여부는 여전히 미기록** — 아래 "주의"의 그 항목은 해소되지 않았다 |
| 모델 서빙 (LLM/VLM/임베딩) + 인증키 | 사용 가능 | ✅ 3종 사전 발급 실물 확인 — VLM 2(`gemma-31b-full-context` 325, `Qwen3.5-122B-A10B-FP8` 226) + 임베딩 1(`kure-v1` 19) |
| 내장 Git | "외부 Git 연동 포함" | ✅ 내장 = **Gitea** (`llmops-gitea-service:3000`, 계정ID + accessToken). 저장소가 초기 커밋과 함께 생성돼 **첫 push `--force`** |
| 코드 스페이스 | 사용 가능 | ✅ 이미지 `template-code space-slim:v1.8.6-cve-260820`, small = 1 CPU / 8GB. **python 3.11.15** (워크플로우 컨테이너는 **3.10**) |

**9/2 이후 추가 실측** (같은 규칙 — 문서 추정을 실물로 덮어쓴 것만):

| 항목 | 문서 기반 추정 | **실측** |
|---|---|---|
| 문서 전처리기(커스텀) | "**도커 이미지로 패키징해 admin 등록**" | ❗ **다름(9/2, 과제2)** — 실환경은 **파이썬 단일 파일**이고 admin 도커 등록이 **불요**. 대신 **벡터 청크만 반환할 수 있다**(RDB 반환 경로 없음) |
| 임베딩 · 벡터DB | LLM/VLM/임베딩/리랭크 서빙 + 벡터DB 자동 적재 | ✅ **열림(9/2, 과제2)** — 임베딩은 **`kure-v1` 단일**(bge-m3 없음). 컬렉션 이름이 곧 **인증키**, 본문·`name`은 **AES-256-GCM 암호화**(평문 배포도 있음), `chunk_id`·`content_hash` 속성 없음, 기본 속성 이름 **복수형** → [`knowledge.md` §정석 경로](knowledge.md) |
| 벡터DB 검색 방식 | (문서로는 판정 불가) | ✅ **`vector`·`keyword`·`hybrid` 모두 동작(9/7, 과제2)**. hybrid는 **거리 없이 융합 점수만** 주므로 절대 임계 불가 → 코사인 별도 계측 |
| 워크플로우 진행 상황 표시 | (문서상 `run/v2` 스트리밍 지원) | ✅ **dict 반환 + 소켓 `emit` 병행으로 가능(9/7, 과제8)** — 렌더 4조건(token 청크 · `nodeId`+`status:FINISHED` · 반환 dict에도 `agentFlowExecutedData` · 마지막 `end`). ⚠️ **emit은 워크플로우 런타임 전용**(코드서빙엔 `main_socketio` 없음) |
| 코드 스페이스 직접 구동 | (문서 언급 없음) | ✅ **게이트웨이·배포를 건너뛰고 진입점을 직접 호출 가능(9/6, 과제2·7)** — 한 줄 고치고 보는 시간이 수 분 → 수 초. ⚠️ 배포 경로에서만 드러나는 문제(env·권한)는 못 잡는다 → [`knowledge.md`](knowledge.md) |

**여전히 미확인** (§② 추정이 그대로 남아 있는 것): 크레딧 시스템 탑재 여부 · self-approve 정책 ·
서비스 라우터 부재 · 채팅 앱 CoT/테마 명칭 등 v1.9.1 신규분 · **Chatflow(Flowise) RAG 템플릿**
(우리 RAG형 과제는 전처리기+코드서빙 경로로 갔다) · 파일 기반 대화 플러그인의 **오디오 STT·`.xlsx`
직접 업로드** · 채팅 앱 **업로드 payload 키 모양**(과제7이 9/7에 임시 대응, 첫 실행 로그로 확정 예정).
~~벡터DB·전처리기~~ → 9/2 실측 완료(위 표).

## ② V1.8.6이라면: 사용 가능 / 불가 예상 (문서 기반 추정 — 실측은 위 §②-0)

### 사용 가능 (문서 근거 있음)
- 코드 서빙 전체 스택: 생성(외부 Git 연동 포함)·배포·게이트웨이 호출(`/api/gateway/code_serving/{id}/json` + Bearer 인증키)·이관·컨테이너 서비스
- 코드 스페이스 (+ 볼륨 할당량/공유 볼륨)
- MCP: 도구/서버 생성, 워크플로우의 MCP 도구 노출, Spring AI MCP, A2A 에이전트
- 가드레일: 필터 생성/적용(워크플로우·LLM 서빙 플러그인 탭), 탐지 로그
- 워크플로우: Flowise 2.2.3/3.0.0(Agentflow 3.0), Python 전처리 코드, `run/v2` API(스트리밍), 인증 키 탭, APIM 탭
- 플러그인: 파일 기반 대화(파일/이미지 업로드), 가드레일 플러그인
- 파일 업로드 전처리: mp3/m4a/wav → whisper-large-v3 STT, csv/xlsx(`[DA]` 라우팅)
- 채팅 앱: 생성 위저드, 테마(문서 뷰/챗봇/검색 바), "배포까지 한번에 진행하기", SST/TTS 활용
- 모델 서빙: LLM/VLM/임베딩/리랭크/I2I/T2I, 인증키 발급, `/api/gateway/rep/serving/{id}`, 스케일아웃, 멀티테넌시, 외부 API 모델 등록
- 배포 승인 워크플로(승인 권한자 승인), IAM(사용자/그룹/정책/역할/라이선스)
- 태스크플로우, AI 회의록, 데이터 분석 애플리케이션

### 사용 불가 예상 (v1.8.6 이후 최초 문서화)
- **서비스 라우터** (v1.8.7~) — 리비전 무중단 교체/카나리/Shadow가 필요하면 대안: 대표 리비전 교체 방식
- 코드 서빙 프로모션 (v1.8.8~)
- 카탈로그, AI 드라이브, 파이프라인 관리, 커스텀 대시보드 (v1.8.8~)
- IAM 보안 등급, HAMi vGPU, 리소스 리비전, 용어사전 (v1.9.0~)
- MCP 도구 카탈로그 (v1.9.0~)
- **채팅 앱 CoT 태그 설정, 챗봇형/문서형 테마 명칭, 부정 피드백 수집, 음성 입/출력 토글, 예시 질문 강제 시작** (v1.9.1 문서에서 최초) — v1.8.6 채팅 생성 화면은 구형(워크플로우+테마+사용자 지정 수준)

### 주의 (근거 불충분)
- self-approve 정책: 문서 근거 없음. 문서상 확실한 것은 "승인 권한자의 승인 없이는 배포 불가"라는 절차뿐.
- 크레딧: v1.8.0 문서에만 존재. v1.8.6 환경 탑재 여부는 현장 확인 필요.

## ③ v1.9.1(데모 환경) ↔ V1.8.6 차이 요약

문서 트리 diff 기준 (v1.8.7, v1.8.8, v1.9.0, v1.9.1 신규 페이지 누적):

1. **서비스 라우터** (v1.8.7): 여러 서빙 리비전을 고정 엔드포인트로 묶어 가중치/카나리 라우팅, Shadow 병행 검증, 서킷 브레이커, 라우터 전용 인증키·이용 로그. 데모에서 이걸 보여주면 삼성 환경엔 없다는 점 주의.
2. **채팅 앱 리뉴얼** (v1.9.1 문서): "채팅 앱" 명칭, 챗봇형/문서형 테마, **CoT 태그(열림/닫힘 쌍)**, 부정 피드백 수집(주관식/선택지), 음성 입/출력(STT/TTS/TTS 스트리밍) 설정, 예시 질문 6개·예시 질문으로만 시작 옵션, 프로필 사진/인사말. v1.8.6은 구형 위저드(테마 3종 + "배포까지 한번에").
3. **데이터 계층 확장**: AI 드라이브 + 용어사전 (v1.8.8 admin, v1.9.0~v1.9.1 사용자 문서), 벡터DB 자동 적재는 양쪽 다 있음.
4. **운영/거버넌스**: 카탈로그, 파이프라인 관리, 커스텀 대시보드, 코드 서빙 프로모션 (v1.8.8), IAM 보안 등급·HAMi vGPU·리소스 리비전 (v1.9.0).
5. **MCP 도구 카탈로그** (v1.9.0): MCP 도구 검색/공유 카탈로그. 개별 MCP 도구/서버 기능 자체는 v1.8.6에도 동일.
6. 핵심 개발 축(코드 서빙, 워크플로우 Flowise/Agentflow, run/v2, 가드레일, 플러그인, 파일 전처리, 모델/임베딩/리랭크 서빙)은 **v1.7.5.1 이후 문서상 변화 없음** → 데모 시연 대부분은 v1.8.6에서 재현 가능.

## ④ 문서 근거 없음 (추측 금지 항목)

- **v1.7.5.1 이전 버전별 도입 이력**: v1.3.3~v1.7.4 트리는 현재 문서 사이트에서 삭제됨(200이지만 Page Not Found 본문). "≤ v1.7.5.1" 표기는 상한일 뿐.
- **v1.9.1 전용 버전 트리**: llms.txt의 "v1.9.1" 섹션은 무버전 최신 URL을 가리킴. v1.9.1 고유 버전 경로는 없음.
- **릴리즈 노트/변경 이력 문서**: 존재하지 않음.
- **self-approve(본인 승인 가능/불가) 정책**: 어떤 버전 문서에도 언급 없음.
- **"FastAPI"라는 명시적 프레임워크 지정**: 코드 서빙 가이드에는 uvicorn 커맨드 예시만 있음(사실상 FastAPI/ASGI지만 문서가 프레임워크를 강제하지 않음). FastAPI 명칭은 mocking-flowise 가이드 제목에서만 등장.
- **크레딧 시스템의 v1.8.6 탑재 여부**: v1.8.0 문서 트리에만 인덱스됨.
- **CoT 태그의 실제 플랫폼 도입 버전**: 문서상 v1.9.1 최초일 뿐, v1.8.x 후반 제품에 이미 있었을 가능성은 문서로 확인 불가.
