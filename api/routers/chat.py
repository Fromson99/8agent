"""GenOS 채팅 연동 — `POST /chat/stream` (SSE).

GenOS 워크플로우가 이 엔드포인트를 flowise 대신 호출한다. 규약은 GenOS 문서
(`mocking-flowise`)를 그대로 따른다.

    요청   POST /chat/stream   헤더 `x-request-from: internal`
           {"question": "...", "chatId": "...", "userInfo": {...}}
    응답   text/event-stream, 한 줄에 하나씩
           data: {"event": "<이름>", "data": <값>}

           token                  최종 답변 토큰 (마크다운)
           reasoning_token        판단 과정 — GenOS 가 "Visible Reasoner" 로 접어 보여준다
           agentFlowExecutedData  근거·출처 카드
           error                  오류 메시지
           result                 null — 스트림 종료 신호
           : keep-alive           10초마다 (주석 라인, 프록시 타임아웃 방지)

## 이 어댑터가 채팅에 붙이는 것

일반 LLM 챗봇이 아니다. 답은 **온톨로지 엔진이 만들고**, 채팅은 그 과정을 보여주는
창일 뿐이다. 그래서 `reasoning_token` 에 흘리는 것이 "모델의 생각"이 아니라
라우터가 실제로 지나간 경로(`alias:신탁금액 → intent:value(rule) → …`)다.
값 질문은 fact 표에서 끝나고, 해석 질문만 청크 검색으로 간다 — 화면에 그대로 나온다.

임베딩이 없어 매 단계가 재현 가능하다는 원래 설계를, 채팅 UI 에서도 깨지 않는다.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from .. import engines
from ..documents import STORE as DOCS
from ..documents import Document

router = APIRouter(tags=["genos-chat"])

SENTINEL = "__STREAM_DONE__"
HEARTBEAT_SEC = 10

# chatId → 활성 문서. 대화가 "이 계약서" 를 계속 가리킬 수 있게 한다.
_SESSIONS: dict[str, str] = {}
_SESSION_CAP = 500

Emit = Callable[[str, Any], Awaitable[None]]


class GenerateRequest(BaseModel):
    question: str = ""
    chatId: Optional[str] = None
    userInfo: Optional[dict] = None
    docId: Optional[str] = None        # 워크플로우가 문서를 직접 지정할 때
    model_config = ConfigDict(extra="allow")


HELP = """**신탁계약 정합성 검증 에이전트**

계약서에 대해 그냥 물어보세요. 값 질문은 fact 표에서 바로 답하고,
해석 질문은 조 단위로 근거를 찾아 옵니다.

- `신탁금액이 얼마인가요?` — 값 질의
- `중도해지는 어떻게 하나요?` — 해석 질의
- `만기일은 언제인가요?` — 문서에 없으면 신탁기간에서 **계산**해 근거와 함께 냅니다

**명령어**

| 명령 | 하는 일 |
|---|---|
| `/docs` | 등록된 계약서 목록 |
| `/use <doc_id>` | 이 대화에서 볼 계약서 지정 |
| `/fields` | 별지1 필드 목록 |
| `/help` | 이 도움말 |

새 계약서는 `POST /v1/parser/parse` 로 PDF 를 올리면 자동 등록됩니다.
요약서 대사는 `POST /v1/parser/reconcile` 을 쓰세요 — 판정표를 통째로 냅니다."""


# ---------------------------------------------------------------------------
# 답변 생성
# ---------------------------------------------------------------------------

async def _emit_text(emit: Emit, text: str) -> None:
    """마크다운을 줄 단위로 흘린다. 채팅이 한 덩어리로 툭 나오지 않게."""
    for line in text.splitlines(keepends=True):
        await emit("token", line)
        await asyncio.sleep(0)          # 이벤트 루프에 양보 — 인위적 지연은 주지 않는다


async def _card(emit: Emit, label: str, payload: dict) -> None:
    """GenOS 가 플로우 카드로 렌더링하는 이벤트. content 는 JSON 문자열이어야 한다."""
    await emit("agentFlowExecutedData", {
        "nodeLabel": label,
        "data": {"output": {"content": json.dumps(payload, ensure_ascii=False)}},
    })


def _pick(req_doc_id: Optional[str], chat_id: str) -> tuple[Optional[Document], Optional[str]]:
    """이번 질문이 어느 문서에 대한 것인지 정한다."""
    if req_doc_id:
        doc = DOCS.get(req_doc_id)
        return (doc, None) if doc else (None, f"`{req_doc_id}` 문서를 찾지 못했습니다.")
    held = _SESSIONS.get(chat_id)
    if held:
        doc = DOCS.get(held)
        if doc:
            return doc, None
    docs = DOCS.list()
    if not docs:
        return None, ("등록된 계약서가 없습니다.\n\n"
                      "`POST /v1/parser/parse` 로 PDF 를 올리면 파싱 후 자동 등록됩니다.")
    if len(docs) == 1:
        return docs[0], None
    lines = "\n".join(f"- `{d.doc_id}` — {d.name} ({len(d.chunks.get('chunks') or [])}청크)"
                      for d in docs[:15])
    return None, (f"계약서가 {len(docs)}건 있습니다. `/use <doc_id>` 로 골라 주세요.\n\n{lines}")


def _format_answer(out: dict, doc: Document) -> str:
    """엔진 출력 → 채팅 마크다운. 판정·값을 다시 쓰지 않고 있는 그대로 옮긴다."""
    route = out.get("route") or {}
    ans = out.get("answer") or {}
    parts: list[str] = []

    if ans.get("found"):
        parts.append(f"**{ans['field_name']}** — {ans['value']}\n")
        if ans.get("raw") and ans["raw"] != ans["value"]:
            parts.append(f"> 원문: {ans['raw']}\n")
        if ans.get("derived_from"):
            parts.append(f"> 계산: {ans['derived_from']}  ← 문서에 없는 값을 파생식으로 구했습니다\n")
        src = ans.get("source") or {}
        if src.get("doc"):
            parts.append(f"> 근거: {src.get('doc')} p.{src.get('page')}\n")
        return "".join(parts)

    if ans and not ans.get("found") and ans.get("note"):
        parts.append(f"fact 표에서 **{ans.get('field_name') or route.get('field')}** 를 "
                     f"찾지 못했습니다 ({ans['note']}). 본문을 찾아봤습니다.\n\n")

    hits = out.get("hits") or []
    if not hits:
        parts.append("관련된 조항을 찾지 못했습니다. "
                     "`/fields` 로 이 계약서가 다루는 항목을 확인해 보세요.\n")
        return "".join(parts)

    for h in hits[:3]:
        head = h.get("chunk_id")
        topic = h.get("topic")
        parts.append(f"### {topic or head}\n")
        parts.append(h.get("text", "").strip() + "\n\n")
        parts.append(f"> `{head}` · 점수 {h.get('score')} · 매칭 {'·'.join(h.get('why') or [])}\n\n")
    if len(hits) > 3:
        parts.append(f"그 밖에 {len(hits) - 3}건이 더 걸렸습니다.\n")
    parts.append(f"\n— {doc.name}")
    return "".join(parts)


async def _answer_query(emit: Emit, question: str, doc: Document) -> None:
    onto = engines.ontology()
    cli = engines.parser("cli")

    await emit("reasoning_token", f"대상 문서: {doc.name} ({doc.doc_id})\n")
    # 엔진은 동기 코드다. 스레드로 빼서 하트비트가 계속 나가게 한다.
    out = await asyncio.to_thread(cli._run_query, doc.chunks, question, onto)
    if "error" in out:
        raise RuntimeError(out["error"])

    route = out.get("route") or {}
    await emit("reasoning_token",
               f"분류: intent={route.get('intent')} field={route.get('field')} "
               f"role={route.get('role')} conf={route.get('confidence')}\n")
    await emit("reasoning_token", "경로: " + (" → ".join(route.get("path") or []) or "(규칙 미적중)") + "\n")
    # 해석 질의에서는 answer 가 None 으로 온다 — 키가 없는 게 아니라 값이 None 이다
    answer = out.get("answer") or {}
    if answer.get("found"):
        await emit("reasoning_token", "값 질문이라 fact 표에서 끝났습니다 — 검색을 타지 않았습니다.\n")
    else:
        await emit("reasoning_token",
                   f"후보 {out.get('candidates')}청크 → 적중 {len(out.get('hits') or [])}건\n")

    await _card(emit, "질의 라우팅", {"route": route, "candidates": out.get("candidates")})
    if out.get("hits"):
        await _card(emit, "근거 청크", {
            "hits": [{"chunk_id": h["chunk_id"], "topic": h.get("topic"),
                      "score": h.get("score"), "why": h.get("why")}
                     for h in out["hits"]],
            "expanded": out.get("expanded"), "context": out.get("context")})
    if answer.get("found"):
        await _card(emit, "출처", answer.get("source") or {})

    await _emit_text(emit, _format_answer(out, doc))


async def _handle(emit: Emit, req: GenerateRequest, chat_id: str) -> None:
    q = (req.question or "").strip()
    if not q:
        await _emit_text(emit, HELP)
        return

    if q.startswith("/") or q in ("도움말", "help"):
        cmd, _, arg = q.lstrip("/").partition(" ")
        cmd, arg = cmd.lower(), arg.strip()

        if cmd in ("help", "도움말", "?"):
            await _emit_text(emit, HELP)
            return

        if cmd in ("docs", "문서", "documents"):
            docs = DOCS.list()
            if not docs:
                await _emit_text(emit, "등록된 계약서가 없습니다. "
                                       "`POST /v1/parser/parse` 로 PDF 를 올리세요.")
                return
            held = _SESSIONS.get(chat_id)
            lines = ["**등록된 계약서**\n", "| doc_id | 이름 | 청크 | 출처 |", "|---|---|---|---|"]
            for d in docs:
                mark = " ←" if d.doc_id == held else ""
                s = d.summary()
                lines.append(f"| `{d.doc_id}`{mark} | {d.name} | {s['chunks']} | {d.source} |")
            await _card(emit, "문서 목록", {"documents": [d.summary() for d in docs]})
            await _emit_text(emit, "\n".join(lines))
            return

        if cmd in ("use", "선택"):
            doc = DOCS.get(arg) if arg else None
            if not doc:
                await _emit_text(emit, f"`{arg or '(비어 있음)'}` 문서를 찾지 못했습니다. "
                                       f"`/docs` 로 목록을 보세요.")
                return
            if len(_SESSIONS) > _SESSION_CAP:
                _SESSIONS.clear()          # 대화 상태는 캐시일 뿐 — 넘치면 통째로 버린다
            _SESSIONS[chat_id] = doc.doc_id
            s = doc.summary()
            await _emit_text(emit, f"이 대화의 계약서를 **{doc.name}** (`{doc.doc_id}`) 로 "
                                   f"맞췄습니다. 청크 {s['chunks']}개 · 조 {s['articles']}개.")
            return

        if cmd in ("fields", "필드"):
            onto = engines.ontology()
            lines = ["**별지1 필드**\n", "| 필드 | 타입 | 조 |", "|---|---|---|"]
            for name, spec in onto.fields.items():
                lines.append(f"| {name} | {getattr(spec, 'value_type', '')} | "
                             f"{getattr(spec, 'article', '') or '—'} |")
            await _emit_text(emit, "\n".join(lines))
            return

        await _emit_text(emit, f"모르는 명령입니다: `/{cmd}`\n\n{HELP}")
        return

    doc, problem = _pick(req.docId, chat_id)
    if problem:
        await _emit_text(emit, problem)
        return
    assert doc is not None
    _SESSIONS.setdefault(chat_id, doc.doc_id)
    await _answer_query(emit, q, doc)


# ---------------------------------------------------------------------------
# SSE 배관 — GenOS 예제와 같은 구조
# ---------------------------------------------------------------------------

@router.post("/chat/stream", summary="GenOS 채팅 연동 (SSE)")
async def chat_stream(req: GenerateRequest, request: Request) -> StreamingResponse:
    queue: asyncio.Queue[str] = asyncio.Queue()
    disconnected = asyncio.Event()
    chat_id = req.chatId or f"chat-{id(req):x}"

    async def emit(event: str, data: Any) -> None:
        payload = {"event": event, "data": data}
        await queue.put(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")

    async def heartbeat() -> None:
        # 프록시가 조용한 연결을 끊는다. 10초마다 주석 라인을 보내 살려 둔다.
        while not disconnected.is_set():
            await asyncio.sleep(HEARTBEAT_SEC)
            await queue.put(": keep-alive\n\n")

    async def runner() -> None:
        try:
            await emit("session", {"chatId": chat_id})
            await _handle(emit, req, chat_id)
        except Exception as exc:
            await emit("error", f"{type(exc).__name__}: {exc}")
            await emit("token", f"\n\n오류가 발생했습니다: {exc}")
        finally:
            await emit("result", None)
            await queue.put(SENTINEL)

    async def sse():
        producer = asyncio.create_task(runner())
        pinger = asyncio.create_task(heartbeat())
        try:
            while True:
                if await request.is_disconnected():
                    disconnected.set()
                    break
                chunk = await queue.get()
                if chunk == SENTINEL:
                    break
                yield chunk
        finally:
            disconnected.set()
            producer.cancel()
            pinger.cancel()

    return StreamingResponse(sse(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",      # nginx 가 SSE 를 버퍼링하지 않게
    })
