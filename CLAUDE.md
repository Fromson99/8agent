# 8-AGENT

법령·규정 문서를 수집→구조화→연결→질의응답으로 잇는 시스템. 전체 그림은
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), 반영 경로는 scripts/serve.sh (uvicorn) 재시작 하나 —
컨테이너는 쓰지 않는다(2026-08-18 컨테이너 파일·레거시 앱 삭제).

## 지식 위키 — 세션 간 기억

`data/wiki/` 는 법령해석 도메인 지식의 llm-wiki(raw 불변층 + LLM 컴파일층)다.
**법령해석·규정 적용을 다루는 작업 전에 `data/wiki/wiki/index.md` 를 먼저
읽어 라우팅하라** — 세션은 리셋되지만 위키는 남는다. 역할 구도:

- 법령 원문("무엇이라 쓰였나") → 구조 스토어·RAG (data/structure, lawrag/core/rag)
- 해석 지식("어떻게 읽는가") → 위키 (data/wiki)

위키를 소유한 것은 LLM 세션(너)이다. 의무 (정본 절차: docs/expc.md §위키):

- `data/wiki/wiki/log.md` 의 "컴파일 대기"(triage·rule 항목)를 보면 병합하라
  — 아티클 수정 → index.md Updated 갱신 → log.md 한 줄 → 검사 통과.
- 수치·인용은 쓰기 전에 Raw 원문에서 확인하고 **원문 표기 그대로** 쓴다
  (grounding — "20%"가 아니라 "100분의 20").
- 검증: `python scripts/expc_wiki_check.py` (grounding·충실도·미참조 재고).
- raw/ 는 절대 고치지 않는다. 낡은 주장은 삭제 대신 Status: Outdated/Disputed.

## 진화 루프

- 대화→위키 유입 판정: `python -m lawrag.pipeline.wiki_triage` (오답·감사 지문 우선)
- 아티클 실적: 적중 원장 data/wiki/ledger.jsonl (lawrag/core/rag/wikiledger) —
  생애 보고서(lawrag/core/rag/wikilife)가 4기준·권고로 접는다 (/expc/ 위키 판 배지)
- 규칙 정착·강등은 rules.set_status 가 위키 연대기에 자동 기록 — 정착 규칙은
  아티클로 컴파일하고 본문에 `rule:<id>` 로 인용하라 (강등 시 재심이 걸린다)
