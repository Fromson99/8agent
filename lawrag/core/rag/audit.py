"""사후 감사 — 답을 보낸 **뒤에** 컨텍스트를 되짚는 LLM 한 콜.

예전에는 답변 합성 콜이 판정까지 함께 했다. 구조화 출력은 JSON 을 다 만들어야
끝나므로, 그 판정 배열을 만드는 시간이 **사용자가 답을 기다리는 시간**에 그대로
얹혔다(게다가 effort=high). 답변 속도가 중요하므로 갈랐다:

    질의 → 검색 → 필터 → 답변 합성(answer/refs만)  → 사용자에게 즉시
                                        └→ 큐 → 워커 스레드 → 감사 1콜 → 판정 백로그

## 무엇을 판정하나 — 네 갈래

컨텍스트에 구역이 들어오는 길이 둘이고(진입 검색 · 참조 확장), 그 위에 우리가
세운 계층이 얹혀 있다. 잘못될 수 있는 자리도 그래서 넷이다.

    오참조    참조 해소가 **좌표를 틀렸다**. 본문의 '제19조제2항' 이 가리키는
              조항과 실제로 실린 구역이 다르다 → 간선을 끊을 후보(그래프 결함)
    참조무관  간선은 옳은데 이번 질문에 안 맞다 → 확장 규칙이 넓다(회수 결함)
    검색무관  진입 검색(벡터·용어)이 엉뚱한 것을 끌어왔다 → 검색 결함
    구조화오류 실린 구역의 **계층이 원문과 다르다**. 장을 찾아 그 아래 조·절을
              함께 실었는데 매달린 자리가 틀렸다 → 구조 재해석 후보

앞의 셋은 "이 구역이 왜 여기 있나"를 묻고, 넷째는 "이 구역이 어떻게 생겼나"를
묻는다. 그래서 넷째만은 **답에 인용한 구역에도** 붙을 수 있다 — 인용했더라도
계층이 틀렸으면 그건 우리 구조화의 결함이다.

## 왜 계층을 볼 수 있는가

컨텍스트를 평평하게 넘기면 계층이 사라져 판정할 것이 없다. 그래서 구역 본문은
`DocView.section_outline` 이 **자손 마디를 들여쓰기로 세운 채** 넘긴다(`▸` 로
시작하는 줄이 우리가 세운 마디, 나머지가 원문 줄).

## fail-open

감사가 실패해도 답변에는 영향이 없다 — 이미 나갔다. 실패는 로그로만 남긴다.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Optional

log = logging.getLogger("lawrag.core.rag.audit")

KINDS = ("오참조", "참조무관", "검색무관", "구조화오류")

AUDIT_SYSTEM = (
    "너는 문서 검색 결과의 **사후 감사자**다. 이미 나간 답변과, 그 답변이 본 "
    "컨텍스트(구역 목록)를 받는다. 답을 다시 쓰지 마라 — 컨텍스트의 결함만 찾는다.\n"
    "각 구역 머리에는 좌표와 **경위**가 있다: 진입 검색으로 들어왔는지, 다른 구역의 "
    "참조를 타고 들어왔는지(← 참조로 옴: 「출발 구역」 본문의 '표면형').\n"
    "구역 본문은 우리 해석이 세운 계층 그대로다 — `▸` 로 시작하는 줄이 **우리가 "
    "세운 마디**(제목)이고, 들여쓰기가 그 마디의 층이며, 나머지는 원문 줄이다.\n"
    "\n"
    "네 가지로만 판정한다(확실한 것만, 애매하면 비운다):\n"
    "  · kind=오참조 — **참조 해소가 좌표를 틀렸을 때만**. 경위에 적힌 표면형이 "
    "가리키는 조항과 실제로 실린 구역이 **다른** 경우다. 표면형이 가리키는 그 조항이 "
    "맞게 실렸다면 오참조가 **아니다** — 질문과 아무리 무관해도 그 연결은 옳다"
    "(옳은 연결을 오참조로 적으면 사람이 그 법령 참조를 영영 잃는다).\n"
    "  · kind=참조무관 — 참조로 끌려왔고 연결은 옳은데, 이번 질문에는 안 맞다.\n"
    "  · kind=검색무관 — 참조가 아니라 **진입 검색**으로 들어왔는데 질문과 무관하다. "
    "검색(벡터·용어)이 빗나갔다는 신호다.\n"
    "  · kind=구조화오류 — 실린 구역의 **계층이 원문과 어긋난다**. 예: 조가 다른 조의 "
    "자식으로 매달림, 항이 앞 조에 붙음, 제목 줄(▸)이 본문 한복판을 자름, 번호가 "
    "이어지는 항목들이 서로 다른 부모에 흩어짐. 이것만은 **답에 인용한 구역에도** "
    "붙일 수 있다 — 인용했더라도 계층이 틀렸으면 우리 구조화의 결함이다. "
    "본문을 못 읽어 판단이 안 서면 적지 마라.\n"
    "\n"
    "reason 은 한 줄 근거. 무엇을 보고 그렇게 판단했는지 **원문 표현을 인용해** 적어라.\n"
    "이 기록은 후보일 뿐이고 반영은 사람이 승인한다."
)

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "n": {"type": "integer"},
                "kind": {"type": "string", "enum": list(KINDS)},
                "reason": {"type": "string"},
            },
            "required": ["n", "kind", "reason"],
            "additionalProperties": False}},
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def audit(llm, question: str, answer: str, sections, cited: set[int]) -> list[dict]:
    """감사 1콜 — 좌표는 코드가 되돌린다(모델은 번호만 말한다).

    `cited` 는 답에 인용한 컨텍스트 번호. 인용한 구역에 '무관'을 붙이는 것은
    자기모순이라 걸러내고, 구조화오류만 남긴다.
    """
    from lawrag.core.rag.answer import _context_text

    if llm is None or not sections:
        return []
    t0 = time.perf_counter()
    user = (f"[질문]\n{question}\n\n[이미 나간 답변]\n{answer[:1500]}\n\n"
            f"[컨텍스트]\n{_context_text(sections)}")
    out = llm.structured("rag.audit", AUDIT_SYSTEM, user, AUDIT_SCHEMA,
                         max_tokens=1500, effort="low")
    if out is None:
        log.warning("감사 실패 — 구역 %d (%.0fms)", len(sections),
                    (time.perf_counter() - t0) * 1000)
        return []

    valid = {s.n: s for s in sections}
    found: list[dict] = []
    for d in out.get("findings", []):
        i, kind = d.get("n"), d.get("kind")
        if not isinstance(i, int) or i not in valid or kind not in KINDS:
            continue
        # 인용한 구역에 '무관·오참조'는 모순 — 계층 결함만 받는다
        if i in cited and kind != "구조화오류":
            continue
        s = valid[i]
        # 경위와 판정이 어긋나면 버린다. 참조로 오지 않은 구역에 '오참조/참조무관'을
        # 붙이면 좌표가 없어 백로그가 손댈 자리를 못 찾는다.
        if kind in ("오참조", "참조무관") and not s.ref_src:
            kind = "검색무관"
        if kind == "검색무관" and s.ref_src:
            kind = "참조무관"
        found.append({"n": i, "kind": kind,
                      "reason": (d.get("reason") or "")[:200],
                      "section": s.cite(), "via": s.kind,
                      "matched": s.matched, "ref_src": s.ref_src})
    log.info("감사 — 구역 %d, 지문 %d (%.0fms)", len(sections), len(found),
             (time.perf_counter() - t0) * 1000)
    return found


# ---------------------------------------------------------------------------
# 백그라운드 실행 — 답변 뒤에 돈다
# ---------------------------------------------------------------------------
# 요청 스레드에서 떼어 낸다. 큐가 차면 **버린다**(막지 않는다) — 감사는 있으면
# 좋은 기록이지 질의를 세울 이유가 아니다. 버린 건 세어서 로그로 알린다.

_Q: "queue.Queue[dict]" = queue.Queue(maxsize=256)
_worker: Optional[threading.Thread] = None
_lock = threading.Lock()
_dropped = 0


def _run_one(job: dict) -> None:
    from lawrag.core.rag import verdicts as verdicts_mod

    findings = audit(job["llm"], job["question"], job["answer"],
                     job["sections"], job["cited"])
    if findings:
        verdicts_mod.log(job["qid"], job["question"], findings)


def _loop() -> None:
    while True:
        job = _Q.get()
        try:
            _run_one(job)
        except Exception:                       # 감사 실패가 프로세스를 세우지 않는다
            log.exception("감사 작업 실패 — qid=%s", job.get("qid"))
        finally:
            _Q.task_done()


def submit(llm, qid: str, question: str, answer: str, sections, cited) -> bool:
    """감사를 큐에 넣는다 — 여기서는 아무것도 기다리지 않는다."""
    global _worker, _dropped
    if llm is None or not sections:
        return False
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, name="rag-audit", daemon=True)
            _worker.start()
    try:
        _Q.put_nowait({"llm": llm, "qid": qid, "question": question,
                       "answer": answer, "sections": list(sections),
                       "cited": set(cited)})
        return True
    except queue.Full:
        _dropped += 1
        log.warning("감사 큐가 가득 찼습니다 — 이번 질의는 감사하지 않습니다 "
                    "(누적 %d건)", _dropped)
        return False


def stats() -> dict:
    return {"queued": _Q.qsize(), "dropped": _dropped,
            "worker": bool(_worker and _worker.is_alive())}


def drain(timeout: float = 30.0) -> bool:
    """큐가 빌 때까지 기다린다 — 시험과 종료 훅에서 쓴다."""
    end = time.monotonic() + timeout
    while _Q.unfinished_tasks and time.monotonic() < end:
        time.sleep(0.05)
    return not _Q.unfinished_tasks
