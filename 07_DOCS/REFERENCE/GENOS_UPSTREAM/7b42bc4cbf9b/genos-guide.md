> 출처 보관본: infocz/main @ `7b42bc4cbf9b7ccef6dfea522d20370cedb237ce`의 `docs/genos/genos-guide.md`.
> 날짜·환경·과제별 관찰 기록이며 현재 8-AGENT의 실행 지침이 아닙니다. 먼저 [GENOS.md](../../../../GENOS.md)를 읽습니다.
> 본문은 보존하고 이미지·미포함 자료 링크만 원본 커밋으로 연결했습니다.

# 🧭 GenOS A to Z 실전 가이드

온프렘 GenOS(LLMOps 플랫폼) 위에서 개발·배포하기 위한 개념·구조·원리 + 순서대로 따라 하는 단계별 프로세스.
삼성증권 불완전판매 과제를 실제로 코드서빙·워크플로우·네이티브 채팅 앱으로 배포하며 확인한 내용 기반. **GenOS v1.9.1 데모 실측**.

> 💡 이 문서는 GitHub 웹에서 바로 보이는 Markdown 버전. 오프라인/로컬에서는 [`genos-guide.html`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/genos-guide.html)을 브라우저로 열면 동일 내용이 스타일 입혀 렌더된다.

**목차**: [1. 한눈에](#1-genos란--한눈에) · [2. 화면 지도](#2-화면-지도--좌측-메뉴가-곧-플랫폼) · [3. 3대 배포 단위](#3-3대-배포-단위--무엇을-언제-쓰나) · [4. 공통 개념](#4-공통-개념--리비전배포승인인증키게이트웨이) · [5. AI 연결 원리](#5-ai-연결-원리--서빙-vs-외부-llm-키) · [6~7. 코드서빙](#6-코드서빙--전체-흐름) · [8~13. 워크플로우+채팅앱](#8-워크플로우--개념) · [14~15. 운영·디버깅](#14-승인결재-처리) · [16. 함정 모음](#16-흔한-함정-모음) · [17. 온프렘 체크리스트](#17-온프렘-vs-데모--투입-체크리스트)

---

## 1. GenOS란 — 한눈에

GenOS는 **LLM 애플리케이션을 만들고 → 배포하고 → 서비스하는 온프렘 플랫폼**이다. 내 코드/모델/플로우를 컨테이너로 띄우고, 인증·승인·모니터링을 붙여, 최종 사용자에게 채팅/API로 제공하는 전 과정을 콘솔 클릭으로 한다.

**핵심 멘탈 모델 3가지**

1. **모든 것은 "리비전 → 배포 → 컨테이너"** — 코드/설정의 버전(리비전)을 만들고, 배포하면 쿠버네티스 컨테이너(Pod)로 뜬다.
2. **서비스는 인증·승인 뒤에 있다** — 배포/중지는 "승인(결재)"을 거치고, 외부 호출은 "인증키 + 게이트웨이"로만 된다.
3. **LLM은 직접 부르지 않고 "서빙"으로 붙인다** — 플랫폼이 관리하는 모델 서빙에 연결하면 raw API 키 없이 LLM을 쓴다.

## 2. 화면 지도 — 좌측 메뉴가 곧 플랫폼

[원본 이미지: GenOS 홈/사이드바](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/01_genos_home.png)

| 묶음 | 메뉴 | 무엇 |
|---|---|---|
| 개발 | 데이터 · 개발 · 모델 · 트레이너 · 평가 · 가드레일 | 데이터셋·코드스페이스·모델 학습·평가·안전필터 |
| 배포 | 도구 · **서빙** · 문서 전처리 · 서비스 라우터 | 모델/코드를 서비스로 배포. **코드서빙·모델서빙**이 여기 |
| 서비스 | **에이전트**(워크플로우/A2A) · **앱**(채팅·보고서·데이터분석) | 워크플로우 파이프라인, 최종 사용자용 채팅 앱 |
| 운영 | **승인** · 크레딧 · 할당량 | 배포/중지 결재, 사용량·자원 관리 |

## 3. 3대 배포 단위 — 무엇을 언제 쓰나

| 단위 | 무엇을 올리나 | 진입점(코드 규약) | 언제 |
|---|---|---|---|
| **코드 서빙** | 임의의 Python 코드를 **HTTP API**로 | `async def service(config, data)` | 판정/전처리/후처리 등 **로직 서비스**. 게이트웨이로 호출 |
| **워크플로우** | **단계(step) 파이프라인**. 채팅 앱에 연결 가능 | Python 단계 `async def run(data)` / Flowise 단계 | 채팅형 서비스, 여러 단계 조합, 스트리밍 출력 |
| **(모델) 서빙** | LLM·임베딩 **모델**을 추론 엔드포인트로 | 모델 이미지/설정 | 플랫폼 내부 LLM 제공. 워크플로우 노드가 여기 붙음 |

> 💡 **우리 과제의 조합**: **코드서빙**(전체 판정 파이프라인) + **워크플로우**(채팅 입력을 코드서빙으로 브릿지 + 스트리밍) + **채팅 앱**(사용자 화면). 판정 로직은 코드서빙에, 채팅 배선은 워크플로우에 두는 2층 구조.

## 4. 공통 개념 — 리비전·배포·승인·인증키·게이트웨이

| 용어 | 뜻 |
|---|---|
| 리비전(Revision) | 코드+설정의 한 버전. "이 도커 이미지 + 이 커밋 + 이 환경변수". 코드/설정을 바꿔 저장하면 **새 리비전** |
| 배포(Deploy) | 특정 리비전을 **컨테이너(Pod)로 띄움**. "배포 완료 · 메인 프로세스 실행" = 서비스 중 |
| 재배포 | 현재 리비전을 다시 띄움(중지→시작). 코드 바꾼 뒤 반영하려면 필수 |
| 승인(결재) | 배포/중지는 **운영>승인**에서 결재. 권한이 있으면 **자체 승인** (모달 버튼: **예**) |
| 인증키 | 이 서비스를 외부에서 부를 자격. `Authorization: Bearer <키>`. **커밋 금지** |
| 게이트웨이 | 외부 호출 진입점. 코드서빙은 `POST /api/gateway/code_serving/{id}/json` |
| 트래픽 분배 | 여러 리비전에 호출 비중(%) 배분. **새 리비전을 100%로 올려야 실제 호출됨** |

## 5. AI 연결 원리 — 서빙 vs 외부 LLM 키

[원본 이미지: 서빙 - 모델 목록](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/02_serving_models.png)

| 방식 | 어떻게 | 주의 |
|---|---|---|
| **GenOS 서빙** | 워크플로우 LLM/Agent 노드를 **모델 서빙**에 연결. 키 불필요 | 플랫폼-네이티브. 채팅 스트리밍의 정석 |
| **외부 LLM 키** | 내 코드에서 외부 API를 직접 호출 (키를 환경변수로) | 데모에서 내부 LLM 키가 없을 때. 키는 **환경변수로만** |

> ⚠️ **데모 함정**: 데모(공용) 환경은 내부 LiteLLM에 키가 없어 직접 호출이 **401**. 그래서 코드서빙에서 외부 OpenAI를 썼다. **온프렘 실환경에선 내부 LLM 서빙 제공** → `LLM_API_BASE/KEY/MODEL` 세 줄만 내부 값으로 바꾸면 코드 수정 없이 전환.

---

## 6. 코드서빙 — 전체 흐름

임의의 Python 로직을 인증된 HTTP API로 만든다. 진입점은 `async def service(config, data)` — 요청 body가 `data`, 리턴 dict가 응답.

```mermaid
flowchart LR
  A[코드서빙 생성] --> B[내장 Git에 코드 push]
  B --> C[리비전: 도커+커밋 선택]
  C --> D[환경변수 주입 LLM_*]
  D --> E[배포 + 자체승인]
  E --> F[트래픽 100%]
  F --> G[인증키 발급]
  G --> H[게이트웨이 호출]
```

## 7. 코드서빙 — 단계별 배포

1. **코드서빙 생성** — 배포>서빙에서 생성. 내부 Git 저장소(Gitea, `llmops/<id>.git`)가 함께 생긴다.
   [원본 이미지: 코드서빙 생성](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/04_cs_create.png)
2. **코드 push** — 진입 파일에 `async def service(config, data)`를 두고 폴더째 push. (의존성은 도커 이미지에 있는 것만)
   [원본 이미지: 코드서빙 - repo 주소](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/05_cs_detail_repo.png)
3. **리비전 만들기** — 도커 이미지·인스턴스 타입·복제본 선택.
   [원본 이미지: 리비전 설정](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/06_cs_revision.png)
4. **환경변수(AI 열쇠) 주입** — `LLM_API_BASE / LLM_API_KEY / LLM_MODEL` 등. ⚠️ **배포 중인 리비전은 잠겨 편집 불가** — 미배포 리비전에서.
   [원본 이미지: 환경변수](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/07_cs_env_empty.png)
5. **배포 + 자체 승인** — 배포 → 승인 대기 → **운영>승인**에서 자체 승인 → 컨테이너 기동.
   [원본 이미지: 승인](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/09_approval.png)
6. **트래픽 100%** — 방금 배포한 리비전에 100%. (안 하면 옛 리비전으로 감)
7. **인증키 발급 + 게이트웨이 호출**
   [원본 이미지: 인증키](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/08_authkey_form.png)

```bash
# 게이트웨이 호출 예 (코드서빙 id=337)
curl -X POST https://<host>/api/gateway/code_serving/337/json \
#      ⚠️ V1.8.6 실측(9/1): `/json`이 아니라 FastAPI 경로가 그대로 프록시된다 → `.../337/chat`
  -H "Authorization: Bearer <인증키>" \
  -H "Content-Type: application/json" \
  -d '{"API_TYPE":"check","transcript_text":"..."}'
```

> ✅ **라이브니스 팁**: LLM을 안 부르는 요청(잘못된 `API_TYPE`)을 보내면 즉시 `{"ok":false,...}` — 비용 없이 생존 확인.

---

## 8. 워크플로우 — 개념

워크플로우는 **"단계(step)를 이어붙인 파이프라인"**, 여기에 **채팅 앱**을 얹으면 대화 서비스가 된다.

| 단계 종류 | 무엇 | 스트리밍 |
|---|---|---|
| Python 단계 | `async def run(data)`. **전처리/브릿지 로직** | 값 반환만으론 ❌ → generator+JSON yield 필요(§10) |
| Flowise 단계 | Chatflow/Agentflow. LLM·임베딩 노드를 서빙에 연결한 그래프 | 서빙-LLM 노드로 끝나면 자동 스트리밍 ✅ |

```mermaid
flowchart LR
  U[사용자 채팅] --> APP[채팅 앱]
  APP --> S1[워크플로우<br/>Python 단계]
  S1 --> CS[코드서빙<br/>판정 파이프라인]
  CS --> S1
  S1 -. 토큰 스트리밍 .-> APP
```

## 9. 워크플로우 패키지 만들기 (Python 단계)

1. **워크플로우 생성** → 리비전 수정 → 도커 `llmops-workflow-api:latest` + **인스턴스 타입** (⚠️ 빼먹으면 저장이 조용히 거부됨)
   [원본 이미지: 워크플로우 리비전](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/21_wf_revision.png)
2. **단계 추가 → Python 단계** — 코드 에디터(ACE)에 `async def run(data)` 작성
   [원본 이미지: 워크플로우 Python 단계](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/20_workflow_python.png)

> ⚠️ **입력 키**: 채팅/테스트가 넘기는 사용자 메시지는 `data["question"]`. 파일 업로드는 `genosUploaded` 등 — 여러 키를 방어적으로 확인할 것.

## 10. ★ Python 단계 채팅 스트리밍 규약 (가장 중요)

> ## ⚠️ 실환경 V1.8.6에서는 이 절이 **정반대**다 (2026-09-01 실측)
> 아래 내용은 **데모 v1.9.1 기준**이다. 삼성증권 실환경 **V1.8.6은 스트리밍이 아니라 dict를 `return`** 한다:
> `async def run(data): return {"text": report}`. 여기 적힌 대로 yield하면 `error_code 000200003`으로 실패하고,
> **판정은 성공하는데 채팅만 실패**하며 컨테이너 로그에는 단서가 남지 않는다(브라우저 네트워크 탭에서만 보인다).
> 대가로 스트리밍이 사라져 응답이 끝날 때까지 화면이 조용하다. 상세: [`knowledge.md` §★](knowledge.md) ·
> [`../onprem/day1-runbook.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/day1-runbook.md) Day-1 실행 결과.
> **환경이 어느 쪽인지는 2분이면 갈린다** — Python 단계에 `async def run(data): return {"text":"hello"}`만
> 넣고 배포해 hello가 뜨는지 보면 된다.

채팅 앱은 **스트리밍(SSE) 응답**만 렌더한다. Python 단계가 값을 `return`만 하면 파이프라인이 성공해도 채팅엔 **"답변 생성 실패"**.

[원본 이미지: 컨테이너 로그 - token_stream](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/19_token_stream_log.png)

컨테이너 로그로 규명한 메커니즘: 프레임워크 `token_stream()` → `_process_generator_item()` → **`json.loads(res)`** — 즉 **yield한 항목을 JSON으로 파싱**한다.

**정답 = async generator로 Flowise SSE 이벤트를 yield:**

```python
import json

async def run(data):            # ← async generator (yield 있음)
    text = _extract(data)        # data["question"] 등에서 추출
    report = _call_337(text)     # 코드서빙 게이트웨이 호출
    for i in range(0, len(report), 24):
        yield json.dumps({"event": "token", "data": report[i:i+24]}, ensure_ascii=False)
    yield json.dumps({"event": "end", "data": ""})
```

- 평문 문자열 yield ❌ (JSONDecodeError) / `sio_server.emit` 방식 ❌
- **Flowise 단계는 이 작업이 필요 없다** (네이티브 SSE)
- ⚠️ V1.8.6에서는 **`run()` 안에 `yield`가 하나라도 남으면** 파이썬이 통째로 제너레이터로 만들어
  `return`이 사라진다 — 규약을 바꿀 때 `_token()`·청크 루프까지 전부 걷어내야 한다

## 11. 워크플로우 배포 & 테스트

- 코드 저장(새 리비전) → 배포/재배포 → "배포 완료 · 메인 프로세스 실행"
- **테스트 다이얼로그**: 입력 JSON 예 `{"question": "..."}` — 채팅 없이 로직 검증
  [원본 이미지: 테스트 다이얼로그](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/22_wf_test_dialog.png)

## 12. 채팅 앱 — 워크플로우에 연결·배포·승인

[원본 이미지: 채팅 앱 목록](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/23_chatapp_list.png)

1. **채팅 앱 생성(또는 새 버전)** — 인사말·테마(**문서형=근거 문서 표시**)·**워크플로우 선택**
   [원본 이미지: 새 버전 마법사](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/25_new_version_wizard.png) [원본 이미지: 워크플로우 선택](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/26_wf_dropdown.png)
2. **신규 앱은 생성 확인 모달의 "배포까지 한번에 진행하기" 체크** → 승인 1회로 끝
3. 버전 배포 — 각 버전은 특정 워크플로우 **리비전 ID에 핀 고정**
   [원본 이미지: 버전 카드](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/27_version_cards.png)
4. 연결 상태 **Online** 확인 → "채팅 앱 열기"
   [원본 이미지: 워크플로우 바인딩](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/24_chatapp_binding.png) [원본 이미지: Online](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/18_chatapp_online.png)

최종 동작 (과제6 불완전판매, 커스텀 경로):
[원본 이미지: 채팅 스트리밍](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/17_native_chat_stream.png)

## 13. ⚠️ 재배포 사이클 — 연결 잠금 함정

[원본 이미지: 재배포 잠금](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/29_redeploy_lock.png)

채팅 앱이 연결(운영)돼 있으면 워크플로우 재배포가 막힌다 ("연결된 애플리케이션을 중지해야…"). **워크플로우 코드 수정 → 반영 순서**:

1. 단계 코드 수정 → **저장**(새 리비전)
2. 채팅 앱 **배포 중지** → 승인(예)
3. 워크플로우 **재배포**
4. 채팅 앱 **새 버전 생성** → 워크플로우 재선택(현 리비전 바인딩)
5. 새 버전 **배포** → 승인(예)
6. 채팅 **테스트**

---

## 14. 승인(결재) 처리

배포·중지 요청은 모두 **운영>승인**으로 모인다. 대기 건의 **승인** 클릭 → 모달 **예**. 여러 건이면 최신(맨 위)부터.

[원본 이미지: 승인 목록](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/28_approval_list.png)

## 15. 디버깅 3종 세트

| 도구 | 용도 |
|---|---|
| **이용 로그** | 요청별 Success/Failed + **소요시간**. 0.1초 Success=조기 리턴(입력 못 읽음) · 수십 초 Success=로직 실행됨(화면만 실패면 출력 형식 문제) · 0.1초 Failed=전송 전 오류 |
| **컨테이너 로그** | **진짜 스택트레이스**. (스트리밍 json.loads 규약도 이걸로 발견) |
| **테스트 다이얼로그** | 채팅 없이 로직만 빠르게 검증 |

[원본 이미지: 이용 로그](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/img/30_usage_log.png)

> 🧭 사고 순서: "실패" 표시 → 이용 로그(Success? 소요시간?) → 로직은 됐는데 화면만 실패면 컨테이너 로그에서 출력/스트리밍 오류. 예외를 넓은 try/except로 삼키면 로그에 안 남는다.

## 16. 흔한 함정 모음

| 증상 | 원인 | 해결 |
|---|---|---|
| 환경변수 편집 안 됨 | 배포 중 리비전 잠김 | 미배포 리비전에서 수정 |
| 새 리비전이 호출 안 됨 | 트래픽이 옛 리비전에 | 새 리비전 트래픽 100% |
| LLM 직접 호출 401 | 데모에 내부 키 없음 | 서빙 연결 또는 외부 키(env) |
| 채팅 "답변 생성 실패"인데 이용로그 Success | Python 단계가 값 return | generator로 `json.dumps({"event":"token"…})` yield |
| 워크플로우 재배포 막힘 | 채팅 앱 연결 중 | 앱 먼저 중지→승인 (§13) |
| 채팅 URL 404 | 앱이 배포 중지 상태 | 배포+승인 → Online 확인 |
| 워크플로우 저장 조용히 거부 | **인스턴스 타입 미선택** | 리비전에서 인스턴스 타입 지정 |
| 새 버전이 엉뚱한 워크플로우에 연결 | 드롭다운에서 남의 것 선택 | 이름 검색 후 정확 선택·값 확인 |
| JSON body에 원문 주입 시 깨짐 | 줄바꿈·따옴표 | `json.dumps`로 인코딩 |
| STT 붙여넣기 "발화 파싱 실패" | 붙여넣기로 **탭·줄바꿈 소실**(한 줄 뭉개짐) | '숫자+발화자+시각' 경계 전역 추출 정규식 |

## 17. 온프렘 vs 데모 · 투입 체크리스트

> **2026-09-01 — 투입 첫날 체크리스트는 실행됐다.** 아래 표에 실측 열을 채웠고, 전체 결과는
> [`../onprem/day1-runbook.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/day1-runbook.md) "Day-1 실행 결과"가 정본이다.

| 항목 | 데모(공용) v1.9.1 | 온프렘 실환경 V1.8.6 (9/1 실측) |
|---|---|---|
| LLM | 내부 키 없음 → 외부 OpenAI | ✅ 내부 LLM 서빙 → `LLM_*` 내부값(코드 무수정). 사전 발급 3종 = VLM 2 + 임베딩 `kure-v1` |
| **Python 단계 응답** | SSE 이벤트 **yield** | ❗ **dict `return`** — 정반대 (§10 경고) |
| **게이트웨이 경로** | `…/code_serving/{id}/json` | ❗ `…/code_serving/{id}/chat` — FastAPI 경로 그대로 프록시 |
| **Python 버전** | (개발기 3.14) | 코드스페이스 **3.11.15** / 워크플로우 컨테이너 **3.10** |
| 권한 | 일부 등록이 관리자 전용 | ✅ 정식 권한 배정 — 배포 승인 정상 진행 |
| 망 | 인터넷 가능 | 폐쇄망 — 외부 호출·CDN 불가 |
| 데이터 | 합성/공개만 | 실데이터 반출 금지 |

**투입 첫날 체크리스트 — 9/1 실행 결과**

1. 콘솔 접속 + 권한 확인 (코드서빙/워크플로우/앱 생성 버튼이 보이나) — ✅
2. 모델 서빙 목록 (내부 LLM 이름·엔드포인트) — ✅ 3종 사전 발급(`gemma-31b-full-context` 325 · `Qwen3.5-122B-A10B-FP8` 226 · `kure-v1` 19). **인증키는 저장소에 담지 않는다**
3. 도커 이미지에 `llmops-workflow-api` 있는지 — ✅ (코드스페이스 = `template-code space-slim:v1.8.6-cve-260820`, small 1 CPU/8GB)
4. 승인 권한 (자체 승인 or 결재선) — ✅ 승인 절차 정상. ⚠️ self-approve 여부는 미기록
5. 게이트웨이 호스트·인증키 발급 절차 — ✅. ⚠️ 인증키 허용 IP는 개별 IP가 아니라 **내부 대역(CIDR)**
6. 폐쇄망 대비 오프라인 자료 준비 (이 저장소가 그 답) — ✅

---

*인포시즈 · GenOS v1.9.1 데모 실측 (2026-08-04~06) · 실환경 V1.8.6 재확인 = **2026-09-01 투입 첫날 실행 완료** — [`../onprem/day1-runbook.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/day1-runbook.md) Day-1 실행 결과*
*지식준비·RAG 경로는 [`rag-runbook/RUNBOOK.md`](rag-runbook/RUNBOOK.md) · 검증 범위는 [`coverage-map.md`](coverage-map.md)*
