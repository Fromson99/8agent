> 출처 보관본: infocz/main @ `7b42bc4cbf9b7ccef6dfea522d20370cedb237ce`의 `docs/genos/README.md`.
> 날짜·환경·과제별 관찰 기록이며 현재 8-AGENT의 실행 지침이 아닙니다. 먼저 [GENOS.md](../../../../GENOS.md)를 읽습니다.
> 본문은 보존하고 이미지·미포함 자료 링크만 원본 커밋으로 연결했습니다.

# GenOS 플랫폼 지식

> 📌 **문서 보는 법**: GitHub 웹은 HTML을 렌더하지 않는다(소스로 보임) → **웹에서는 `.md` 버전**을 보고, **클론/반입 후에는 `.html`을 브라우저로** 열면 스타일·다이어그램이 렌더된다 (mermaid 로컬 번들 동봉, 인터넷 불필요).

과제와 무관하게 재사용하는 **플랫폼 사용법·검증 결과** 모음. 뿌리는 데모(genos.genon.ai **v1.9.1~1.9.2**)에서 **실제 실행하며** 작성했다 — 가이드·런북 본문은 v1.9.1 실측, MCP 런북(8/7)과 용어 사전은 v1.9.2 실측이다.

> ⚠️ **2026-09-01 투입 이후: 이 폴더는 더 이상 데모 전용이 아니다.** 삼성 실환경 **V1.8.6**에 실제로
> 배포하며 얻은 실측이 `knowledge.md`에 들어와 있고, **데모와 정반대인 항목이 있다**
> (워크플로우 Python 단계 응답 규약 = V1.8.6은 `yield`가 아니라 **dict `return`**, 코드서빙 게이트웨이
> 경로도 `/json`이 아니라 FastAPI 경로 그대로). **실환경에서 쓸 때는 `knowledge.md`의 V1.8.6 블록이
> 우선**이고, 나머지 문서(가이드·RAG 런북·용어 사전)는 여전히 데모 기준이라 갭 주의.
> 남은 미검증분은 [`../onprem/unverified.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/unverified.md) — ⚠️ **9/3 외부망 계정 회수로
> 데모에서 미리 해 보는 경로가 닫혔다**(A2·A3·A5·A6는 실환경에서 처음 연다).
> 투입 첫날 체크리스트는 **실행 완료**됐다: [`../onprem/day1-runbook.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/day1-runbook.md) "Day-1 실행 결과".

| 문서 | 내용 | 언제 보나 |
|---|---|---|
| [`genos-guide.md`](genos-guide.md) *(GitHub용)* · [`genos-guide.html`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/genos-guide.html) *(오프라인용)* | **A-to-Z 실전 가이드** — 멘탈모델·화면지도·3대 배포 단위·코드서빙 7단계·워크플로우/Python 단계 스트리밍 규약·채팅앱·재배포 사이클·디버깅 3종·함정 표·투입 체크리스트 (스크린샷 22장) | 플랫폼이 처음일 때, 막혔을 때 |
| [`rag-runbook/RUNBOOK.md`](rag-runbook/RUNBOOK.md) | **지식 준비 + RAG 런북** — 벡터DB 생성→문서 업로드(전처리·임베딩·청킹 설정)→적재 확인→Flowise RAG 체인(자체 e2e)→문서형 채팅앱(출처 렌더). 시각 버전: [`rag-runbook/runbook.html`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/runbook.html) *(오프라인용)* + 예시 PDF 동봉 | RAG형 과제(2 ELS·3 법규정) 시작할 때 |
| [`coverage-map.md`](coverage-map.md) *(GitHub용)* · [`coverage-map.html`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/coverage-map.html) *(오프라인용)* | **검증 범위 지도** — 전체 체인에서 검증(초록)/미검증(빨강) 구간 | 뭐가 남았는지 볼 때 |
| [`version-gap.md`](version-gap.md) | **V1.8.6 갭 매트릭스** — 기능 × 최초 등장 버전, 사용 가능/불가 예상, 전부 공식 문서 근거 링크 (8/13 전수 조사) | 실환경에 이 기능이 있나 궁금할 때 |
| [`mcp-runbook.md`](mcp-runbook.md) | **MCP Tool/Server 런북** — 도구 등록(FastMCP)→서버 배포→Agentflow Agent에 `Genos MCP` 연결→선택적 function call 검증 (8/7) | function call 과제 — **과제5 리스크관리 규정(MCP)·과제8 오퍼링 T2SQL** — 시작할 때 (⚠️ 구 표기 "⑧ 리스크규정·NL-to-SQL·DW"는 8/10 폐기된 팀 리넘버링 잔재. 번호 정본은 [`../project/rfp-8tasks.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/project/rfp-8tasks.md)) |
| [`glossary.md`](glossary.md) | **용어 사전** — GenOS 고유 개념 vs 내장 오픈소스(Flowise) vs 표준(MCP·A2A) 구분 정의 + 헷갈리는 용어 정리 | 용어가 낯설 때 (합류 첫날) |
| [`knowledge.md`](knowledge.md) | 실전지식 요약판 (텍스트) — 가이드의 압축본 **+ 실환경 V1.8.6 실측이 얹힌 유일한 문서**(9/1 응답 규약 역전 · 9/2 정석 경로 · 9/5 런타임 코드 공유 없음 · **9/6 코드 스페이스 직접 구동**) | 빠른 리마인드, **실환경 작업 전 필독** |
| `img/` `assets/` | 스크린샷 · **mermaid.min.js(오프라인 렌더 번들)** | — |

## 5분 요약 (처음 온 사람용)

1. **모든 것은 리비전→배포→컨테이너.** 배포/중지는 승인(자체승인 가능), 외부 호출은 인증키+게이트웨이.
2. **3대 배포 단위**: 코드서빙(임의 코드→API) · 워크플로우(단계 파이프라인, 채팅앱 연결) · 모델 서빙(LLM/임베딩 — 노드 연결 시 키 불요).
3. **두 구현 경로**: 정석(플랫폼 부품 조립, 코드 0줄, RAG류) vs 커스텀(코드서빙에 로직, 판정·비교류). → [`../tasks/README.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/tasks/README.md)
4. **최대 함정 셋**: ① 배포 중 리비전은 env 잠김 ② 채팅앱 연결 중엔 워크플로우 재배포 잠김(중지→승인→재배포→재바인딩) ③ Python 단계 채팅 스트리밍은 `json.dumps({"event":"token",...})` yield 필수 — ⚠️ **③은 데모 v1.9.1 기준이고 실환경 V1.8.6은 정반대(dict `return`)**다. `knowledge.md` 참조.
5. **개발할 땐 배포하지 않는다** (9/6): 코드 스페이스에서 진입점을 직접 띄워 curl로 부르면 리비전·배포·승인을 건너뛴다 — 한 줄 고치고 보는 시간 수 분 → 수 초. 굳은 뒤 한 번 올린다.
