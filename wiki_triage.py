"""대화 → 위키 유입 판정(triage) — llm-wiki ingest 의 관문.

    python wiki_triage.py               # 새 대화(질의·피드백)를 판정
    python wiki_triage.py --dry-run     # 판정만 출력, 파일 안 씀
    python wiki_triage.py --limit 50    # 최근 이벤트 조회 폭

질의응답(/rag/)에서 지식이 계속 새어 나온다 — 사용자가 교정한 답, 위키에
없는 해석 논점을 다룬 문답. llm-wiki 의 ingest 관문(triage)을 이 스트림에
댄다: **무엇이 위키에 들어갈 자격이 있는지 LLM 이 판정**하고, 통과분만
raw/conversations/ 에 소스로 남긴다.

정본 SKILL 과 한 가지 의도적 차이: 정본은 "fetch 는 무조건, compile 만
triage"지만, 대화는 소스가 아니라 **후보 스트림**이라 판정 통과분만 raw 가
된다 — 모든 문답을 raw 로 쌓으면 증거층이 잡음으로 메워진다. 탈락 판정은
상태 파일(triage_state.json)에만 남아 재판정을 막는다.

컴파일(아티클 반영)은 여기서 하지 않는다 — 그것은 위키를 소유한 LLM 세션의
일이다 (docs/expc.md §위키). 이 관문의 산출은 raw 파일 + log.md 의
"컴파일 대기" 항목이고, 위키 세션이 그 로그를 보고 병합한다.
판정 규칙: 코드가 거를 수 있는 것(오류 응답·미응답)은 코드가 거르고,
지식 가치 판단만 LLM 에 넘긴다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from core import logbook  # noqa: E402

WIKI_ROOT = REPO_ROOT / "data" / "wiki"
RAW_DIR = WIKI_ROOT / "raw" / "conversations"
LOG_MD = WIKI_ROOT / "wiki" / "log.md"
INDEX_MD = WIKI_ROOT / "wiki" / "index.md"
STATE = WIKI_ROOT / "triage_state.json"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["disposition", "rationale", "topic", "slug", "title", "knowledge",
                 "targets"],
    "properties": {
        "disposition": {"type": "string",
                        "enum": ["New", "Update", "Disputed", "No material"]},
        "rationale": {"type": "string", "description": "판정 근거 한두 문장"},
        "topic": {"type": "string",
                  "description": "위키 주제 디렉터리 (기존 재사용 우선, 예: 해석원칙)"},
        "slug": {"type": "string",
                 "description": "raw 파일 슬러그 — 한글 kebab-case, 60자 이내"},
        "title": {"type": "string", "description": "이 지식 조각의 제목"},
        "knowledge": {"type": "string",
                      "description": "위키에 들어갈 지식의 요지 (컴파일러가 읽는다)"},
        "targets": {"type": "array", "items": {"type": "string"},
                    "description": "병합 대상 아티클 slug 들 (New 면 빈 배열)"},
    },
}

SYSTEM = """너는 법령해석 지식 베이스(llm-wiki)의 ingest 관문이다.
법령 RAG 챗봇의 문답 하나를 보고, 위키에 들어갈 지식이 있는지 판정한다.

판정 기준 (SKILL 규율):
- New: 위키에 없는 해석 개념·원칙이 문답에 담겼다 — 새 아티클감.
- Update: 기존 아티클이 다루는 개념에 새 사례·논점을 보탠다.
- Disputed: 위키의 기존 주장과 모순되는 내용이다.
- No material: 위키가 이미 아는 내용이거나, 단순 조문 조회·사실 확인이라
  해석 지식이 아니다. **얇은 소스로 아티클을 억지로 만들지 않는다.**

주의:
- 조문 내용 자체는 지식이 아니다 — 그건 코퍼스(법령 원문)의 몫이다.
  위키가 담는 것은 "어떻게 읽는가": 해석 원칙, 문턱, 판정 방향, 예외 구조.
- 사용자 피드백(교정·반박)이 붙은 문답은 가치가 높다 — 시스템이 틀린 자리가
  곧 위키가 메워야 할 자리다.
- 확신이 없으면 No material — 위키 오염이 누락보다 나쁘다."""


def load_state() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text("utf-8"))
    return {"done": {}}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", "utf-8")


def prioritize(cands: list[dict], flagged: set[str]) -> list[dict]:
    """자기수선 순서 — 시스템이 틀린 자리가 위키가 메울 자리다.
    피드백 오답(사람이 틀렸다 함) > 감사 지문·교정(기계가 스스로 표시) >
    피드백 있음 > 나머지. 같은 급 안에서는 최신부터."""
    def score(c: dict) -> tuple:
        wrong = any(f.get("verdict") == "오답" for f in c["feedbacks"])
        return (2 if wrong else 0) + (1.5 if c["qid"] in flagged else 0) \
            + (1 if c["feedbacks"] else 0), c.get("ts", "")
    return sorted(cands, key=score, reverse=True)


def candidates(limit: int) -> list[dict]:
    """판정 후보 — 코드 결정론으로 거를 수 있는 것은 여기서 거른다."""
    events = logbook.read_rag_events(limit=limit)
    feedbacks: dict[str, list[dict]] = {}
    for e in events:
        if e.get("kind") == "feedback" and e.get("qid"):
            feedbacks.setdefault(e["qid"], []).append(e)
    out = []
    for e in events:
        if e.get("kind") != "ask" or e.get("error") or not e.get("answer"):
            continue
        if e.get("answerable") is False:      # 미응답 — 지식이 아니라 공백 기록
            continue
        out.append({"qid": e.get("qid", ""), "ts": e.get("ts", ""),
                    "q": e.get("q", ""), "answer": e.get("answer", ""),
                    "feedbacks": feedbacks.get(e.get("qid", ""), [])})
    try:
        from core.rag import verdicts as verdicts_mod
        flagged = verdicts_mod.flagged_qids()
    except Exception:                          # 감사 스토어가 없는 배포
        flagged = set()
    return prioritize(out, flagged)


def safe_slug(s: str) -> str:
    s = re.sub(r"[^\w가-힣\-]+", "-", s.strip()).strip("-")
    return s[:60] or "conversation"


def write_raw(c: dict, verdict: dict, today: str) -> Path:
    fb = "\n".join(f"- {f.get('verdict', '')}: {f.get('note', '') or ''}".rstrip(": ")
                   for f in c["feedbacks"])
    date = (c["ts"] or today)[:10]
    text = (f"# {verdict['title']}\n\n"
            f"> Source: rag 질의응답 (qid {c['qid'] or '미상'})\n"
            f"> Collected: {today}\n"
            f"> Published: {date or 'Unknown'}\n\n"
            f"## 질문\n\n{c['q']}\n\n"
            f"## 답변\n\n{c['answer']}\n"
            + (f"\n## 사용자 피드백\n\n{fb}\n" if fb else ""))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    p = RAW_DIR / f"{date}-{safe_slug(verdict['slug'])}.md"
    n = 2
    while p.exists():
        p = RAW_DIR / f"{date}-{safe_slug(verdict['slug'])}-{n}.md"
        n += 1
    p.write_text(text, "utf-8")
    return p


def append_log(entry: str) -> None:
    LOG_MD.parent.mkdir(parents=True, exist_ok=True)
    base = LOG_MD.read_text("utf-8") if LOG_MD.is_file() else "# Wiki Log\n"
    LOG_MD.write_text(base.rstrip("\n") + "\n\n" + entry.strip() + "\n", "utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="대화 → 위키 유입 판정")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args(argv)

    state = load_state()
    todo = [c for c in candidates(args.limit)
            if c["qid"] and c["qid"] not in state["done"]]
    if not todo:
        print("판정할 새 대화가 없습니다")
        return 0
    print(f"판정 대상 {len(todo)}건")

    from core.llm import LLM
    llm = LLM()
    index_md = INDEX_MD.read_text("utf-8") if INDEX_MD.is_file() else "(위키 없음)"
    today = time.strftime("%Y-%m-%d")
    kept = 0
    for c in todo:
        fb = "; ".join(f"{f.get('verdict', '')} {f.get('note', '') or ''}".strip()
                       for f in c["feedbacks"]) or "없음"
        user = (f"[위키 인덱스]\n{index_md}\n\n[문답]\n질문: {c['q']}\n\n"
                f"답변: {c['answer']}\n\n사용자 피드백: {fb}")
        verdict = llm.structured("wiki-triage", SYSTEM, user, SCHEMA,
                                 effort="medium")
        if verdict is None:
            print(f"  ?? {c['qid']}: LLM 호출 실패 — 다음 실행에서 재시도", file=sys.stderr)
            continue
        disp = verdict["disposition"]
        print(f"  {disp:12s} {c['q'][:50]}  — {verdict['rationale'][:60]}")
        if args.dry_run:
            continue
        if disp == "No material":
            state["done"][c["qid"]] = {"disposition": disp, "at": today}
            save_state(state)
            continue
        raw_path = write_raw(c, verdict, today)
        rel = raw_path.relative_to(WIKI_ROOT)
        targets = "; ".join(verdict["targets"]) or "(새 아티클)"
        append_log(f"## [{today}] triage | 컴파일 대기: {verdict['title']}\n"
                   f"- Disposition: {disp}\n"
                   f"- Raw: {rel}\n"
                   f"- 대상: {targets}\n"
                   f"- 요지: {verdict['knowledge']}")
        state["done"][c["qid"]] = {"disposition": disp, "at": today,
                                   "raw": str(rel)}
        save_state(state)
        kept += 1

    if not args.dry_run:
        print(f"\n완료: 통과 {kept}건 / 판정 {len(todo)}건"
              + (f" — 컴파일 대기가 log.md 에 쌓였습니다. "
                 f"위키 세션(Claude)에 병합을 시키세요 (docs/expc.md §위키)"
                 if kept else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
