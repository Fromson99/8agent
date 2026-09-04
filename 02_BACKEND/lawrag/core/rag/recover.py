"""회복 루프 — 키워드가 빗나갔을 때 도는 사다리. 원본(DELTAFlow)의 이식.

원본의 회복은 "다른 방식으로 다시 찾기"의 사다리였고, 매 단은 앞 단이
빈손일 때만 돈다(첫 성공에서 멈춤):

    ⓪ 도메인 단  창고의 구조를 아는 지식이 먼저 (recover_domains — 법령판:
                 쟁점 재회수·명칭 확장, 결정론). 범용 단은 그 뒤의 일이다.
    ① 의미해석   등록 용어 목록 + 지형도를 LLM 에 보여 주고 뜻이 통하는
                 용어를 고르게 한다. 글자가 안 겹쳐도 의미가 통하면 잡힌다.
    ② 깔때기     구역 계층(카탈로그)을 한 단계씩 내려가며 고른다 —
                 헤딩을 고르면 자식이 다음 카탈로그에 나타난다.
    ③ 원문       구역 본문을 토큰 부분일치로 직접 뒤진다 (결정론, LLM 없음).
    ④ 수색대     찾은 구역의 용어를 수확해 다음 홉의 씨앗으로 — 그래프 위
                 bounded 홉 루프. 마지막에 검증 게이트.
    ⑤ 둘러보기   그래도 없으면 보유 문서를 열거해 고르게 하고, 고를 게
                 없으면 사용자에게 정직하게 되묻는다.

원본에서 그대로 가져온 규율:
    · 신뢰도 0.5 미만이면 **전량 폐기** (fail-closed — 회색지대는 환각 위험)
    · 루프 상한: 깔때기 5걸음·걸음당 4선택, 수색대 3홉·엔트리 8
    · 이미 본 것은 다시 안 본다 (seen / visited_probe)
    · 어느 단이 데려왔는지(via)가 결과마다 남는다 — 조용히 정확 매칭인
      척하지 않는다
    · LLM 이 없으면 LLM 단은 건너뛴다 — 결정론 단(③)은 언제나 돈다
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from lawrag.core.rag import oql, recover_domains, switches
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.graph import Graph, Sec
from lawrag.core.rag.index import Index, norm
from lawrag.core.rag.search import tokens_of

log = logging.getLogger("lawrag.core.rag.recover")

CONF_MIN = float(control_value("recover.confidence_min"))
# 회복 루프는 싼 모델로 고정 — 원본도 폴백 선택은 haiku 급이었다
# (RAG_FAST_LLM_PROVIDER or "claude_haiku_fast"). 여기 판단은 전부 "고르기"라
# 큰 모델이 필요 없고, 사다리는 한 질의에 호출이 잦다. haiku 는 effort 를
# 받으면 400 이 나므로 effort=None 으로 키 자체를 뺀다 (lawrag/core/llm.py 규약).
RECOVER_MODEL = os.environ.get("RAG_RECOVER_MODEL", "claude-haiku-4-5-20251001")
FUNNEL_MAX_STEPS = int(control_value("recover.funnel_steps_max"))
FUNNEL_PICKS_PER_STEP = int(control_value("recover.funnel_picks_per_step_max"))
FUNNEL_KEEP_CAP = int(control_value("recover.funnel_keep_max"))
SCOUT_MAX_HOPS = int(control_value("recover.scout_hops_max"))
SCOUT_MAX_ENTRIES = int(control_value("recover.scout_entries_max"))
SURFACE_CAP = int(control_value("recover.surface_catalog_max"))
FULLTEXT_CAP = int(control_value("recover.fulltext_sections_max"))
SENSE_CATALOG_CAP = int(control_value("recover.sense_catalog_max"))


# ---------------------------------------------------------------- 프롬프트
# 원본 프롬프트에서 도메인(P&ID)만 걷어냈다. 구조와 규칙은 그대로다.

SENSE_SYSTEM = (
    "너는 문서 검색 보조자다. 사용자의 질문에 정확히 일치하는 검색 결과가 없었다. "
    "아래는 시스템에 등록된 용어 목록이다. 각 항목은 id, 용어, 실린 문서들, 출현 수로 "
    "구성된다.\n\n"
    "너는 지금 **둘 중 하나를 명시적으로 선택**해야 한다(빈손으로 침묵하지 마라):\n"
    '  · route="use_terms" — 질문의 **의미**와 관련 있는 용어가 있다 → selected 에 담아라. '
    "표면 글자가 겹치지 않아도 의미가 통하면 고른다(애매·추상 질문 대응이 목적). "
    "단, 관련 없으면 절대 억지로 고르지 마라.\n"
    '  · route="deep_explore" — 쓸만한 용어가 하나도 없다, 또는 용어 수준으로는 답할 수 '
    "없고 문서의 구조(구역 계층)를 직접 뒤져야 한다 → selected 는 빈 배열.\n\n"
    "[지형도]가 함께 주어지면 — 이 시스템이 실제로 보유한 문서와 구역 수다 — 질문이 어느 "
    "문서 이야기인지 엿보고, 더 파볼 가치가 있는 문서를 explore_branches 로 골라라"
    "(route 선택과 별개·병행 가능). 관련 문서가 없으면 빈 배열."
)

SENSE_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["use_terms", "deep_explore"]},
        "selected": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "integer"}, "confidence": {"type": "number"},
            "reason": {"type": "string"}},
            "required": ["id", "confidence", "reason"], "additionalProperties": False}},
        "explore_branches": {"type": "array", "items": {"type": "object", "properties": {
            "doc_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["doc_id", "reason"], "additionalProperties": False}},
        "reason": {"type": "string"},
    },
    "required": ["route", "selected", "explore_branches", "reason"],
    "additionalProperties": False,
}

NAV_SYSTEM = (
    "너는 문서 구조 내비게이터다. 키워드 검색이 0건이라, 카탈로그를 보고 질문의 답이 "
    "있을 법한 곳을 직접 고른다. 카탈로그 항목은 {ref, doc, title, children, paras} — "
    "문서의 구역 헤딩 계층이다. 고르면 그 구역의 요약을 바로 판단하고, 하위 구역"
    "(children)이 다음 스텝 카탈로그에 나타난다 — 계층을 따라 안으로 내려갈 수 있다. "
    "children 이 있고 paras 가 적으면 내려가서 좁히는 게 정밀하다.\n"
    "  - 질문과 의미상 맞는 항목을 최대 몇 개만 고른다(과다 선택 금지 — 정밀하게).\n"
    "  - 이미 본 항목(seen)은 다시 고르지 말고, 그래도 더 볼 게 없으면 done=true.\n"
    "  - 카탈로그에 맞는 게 정말 없으면 picks 를 비우고 done=true."
)

NAV_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {"type": "string"}},
                   "done": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["picks", "done", "reason"], "additionalProperties": False,
}

JUDGE_SYSTEM = (
    "너는 문서 정밀 탐색기다. 사용자 질문과, 방금 연 구역·하위 구역들의 요약 목록"
    "(각 sid)을 받는다. 질문에 실제로 답이 되는 것만 고른다.\n"
    "  - 주제만 비슷하고 직접 답이 아니면 버린다(드리프트 차단).\n"
    "  - 고른 구역으로 질문에 충분히 답할 수 있으면 enough=true, 더 다른 곳을 봐야 "
    "하면 false.\n"
    "  - 하나도 관련 없으면 keep 을 빈 배열로 둔다."
)

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"keep": {"type": "array", "items": {"type": "string"}},
                   "confidence": {"type": "number"}, "enough": {"type": "boolean"},
                   "reason": {"type": "string"}},
    "required": ["keep", "confidence", "enough", "reason"], "additionalProperties": False,
}

VERIFY_SYSTEM = (
    "너는 문서 RAG 의 '증거 검증기'다. 사용자 질문과, 연결관계를 타고 모은 후보 증거 "
    "블록 목록(각 id 부여)을 받는다. 각 블록이 질문에 답하는 데 **실제로 관련 있는지** "
    "판정한다.\n"
    "  - 주제만 비슷하고 질문과 직접 관련 없으면 버린다(드리프트 차단).\n"
    "  - 애매하면 보수적으로 버린다(회색지대는 환각 위험이 크다).\n"
    "  - 하나도 관련 없으면 keep 을 빈 배열로 둔다."
)

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {"keep": {"type": "array", "items": {"type": "string"}},
                   "confidence": {"type": "number"}, "reason": {"type": "string"}},
    "required": ["keep", "confidence", "reason"], "additionalProperties": False,
}

ORIENT_SYSTEM = (
    "너는 문서 RAG 의 '방향 안내자'다. 사용자 질문이 모호하거나 키워드가 안 잡혔다. "
    "지금 시스템이 가진 문서 목록을 보여줄 테니, 질문과 가장 관련 있어 보이는 문서를 "
    "고른다(없으면 빈 배열)."
)

ORIENT_SCHEMA = {
    "type": "object",
    "properties": {"pick": {"type": "array", "items": {"type": "object", "properties": {
        "doc_id": {"type": "string"}, "why": {"type": "string"}},
        "required": ["doc_id", "why"], "additionalProperties": False}},
        "ask_user": {"type": "string"}},
    "required": ["pick", "ask_user"], "additionalProperties": False,
}

DEPTH_SYSTEM = (
    "너는 문서 탐험의 '깊이 선택기'다. 사용자 질문과, 각 탐험 엔트리의 '마일스톤"
    "(중간 정거장)' 목록(번호 n 순)을 받는다.\n"
    "각 엔트리마다 질문에 답하는 데 필요한 만큼만 '몇 번 마일스톤까지' 갈지 정한다"
    "(누적 — N 이면 1..N 전부):\n"
    '  - 정수 N : 1번부터 N번까지\n  - "ALL" : 전부\n  - "NONE" : 질문과 무관 → 제외'
)

DEPTH_SCHEMA = {
    "type": "object",
    "properties": {"depth": {"type": "object",
                             "additionalProperties": {"type": ["integer", "string"]}},
                   "reason": {"type": "string"}},
    "required": ["depth", "reason"], "additionalProperties": False,
}


# ---------------------------------------------------------------- 결과 그릇
@dataclass
class Recovery:
    coords: list = field(default_factory=list)     # [{doc_id,node,via,why}] — 좌표가 결과다
    rungs_fired: list = field(default_factory=list)
    trail: list = field(default_factory=list)      # ladder 형식 기록
    ask_user: str = ""
    meta: dict = field(default_factory=dict)


def _push(coords: list, seen: set, doc_id: str, node, via: str, why: str) -> None:
    key = (doc_id, node)
    if key in seen or node is None:
        return
    seen.add(key)
    coords.append({"doc_id": doc_id, "node": node, "via": via, "why": why})


# ---------------------------------------------------------------- 단들
def _llm_json(llm, kind: str, system: str, user: str, schema: dict) -> Optional[dict]:
    if llm is None:
        return None
    return llm.structured(kind, system, user, schema, max_tokens=2000,
                          effort=None, model=RECOVER_MODEL)


def _term_catalog(g: Graph, index: Index) -> list[dict]:
    """의미해석에 보여줄 용어 목록. 여러 문서에 걸친 용어(어휘의 뼈대)가 먼저 온다."""
    surface = {}
    for e in index.entries:
        surface.setdefault(e.key, e.value)
    rows = []
    for key, secs in g.term_secs.items():
        docs = sorted({g.index.docs[s[0]].name for s, _ in secs if s[0] in g.index.docs})
        rows.append({"key": key, "용어": surface.get(key, key),
                     "문서": docs, "출현": len(secs)})
    rows.sort(key=lambda r: (-len(r["문서"]), -r["출현"], r["key"]))
    rows = rows[:SENSE_CATALOG_CAP]
    for i, r in enumerate(rows):
        r["id"] = i
    return rows


def rung_sense(llm, g: Graph, index: Index, query: str) -> tuple[list, list, dict]:
    """① 의미해석 — 용어 목록 + 지형도에서 뜻이 통하는 용어를 고른다."""
    catalog = _term_catalog(g, index)
    if llm is None or not catalog:
        return [], [], {}
    import json
    view = [{"id": r["id"], "용어": r["용어"], "문서": r["문서"], "출현": r["출현"]}
            for r in catalog]
    user = (f"[질문]\n{query}\n\n[등록된 용어 목록]\n"
            f"{json.dumps(view, ensure_ascii=False)}"
            f"\n\n[지형도 — 이 시스템이 실제 보유한 문서]\n"
            f"{json.dumps(g.terrain(), ensure_ascii=False)}")
    out = _llm_json(llm, "rag.recover.sense", SENSE_SYSTEM, user, SENSE_SCHEMA)
    if out is None:
        return [], [], {}
    by_id = {r["id"]: r for r in catalog}
    coords: list = []
    seen: set = set()
    for s in out.get("selected", []):
        r = by_id.get(s.get("id"))
        if r is None or float(s.get("confidence", 0)) < CONF_MIN:
            continue
        for sec, _via in g.sections_of(r["key"])[:4]:
            _push(coords, seen, sec[0], sec[1], "의미해석",
                  f"용어 '{r['용어']}' — {s.get('reason', '')[:80]}")
    # 지형도에 실제 있는 문서만 — 지어낸 doc_id 는 조용히 버린다 (원본과 같은 가드)
    branches = [b["doc_id"] for b in out.get("explore_branches", [])
                if b.get("doc_id") in g.index.docs]
    return coords, branches, {"route": out.get("route"), "reason": out.get("reason", "")}


def rung_funnel(llm, g: Graph, query: str,
                docs: Optional[list] = None) -> tuple[list, dict]:
    """② 깔때기 — 구역 계층을 한 걸음씩 내려가며 고른다. 걸음 5·선택 4 상한."""
    if llm is None:
        return [], {}
    import json
    v_docs = [d for d in (docs or list(g.index.entry_docs)) if d in g.index.docs]
    catalog: dict[str, dict] = {}
    for doc_id in v_docs:
        v = g.index.docs[doc_id]
        for n in v.nodes:
            if n.get("parent") is None:
                ref = f"{doc_id}:{n['id']}"
                catalog[ref] = {"ref": ref, "doc": v.name,
                                "title": (n.get("title") or n.get("surface") or ""),
                                "children": len(g.children.get((doc_id, n["id"]), [])),
                                "paras": max((n.get("span") or [0, 0])[1]
                                             - (n.get("span") or [0, 0])[0], 0)}
    seen: set[str] = set()
    kept: list = []
    kept_seen: set = set()
    best_conf, steps, path = 0.0, 0, []
    for step in range(FUNNEL_MAX_STEPS):
        view = [c for r, c in catalog.items() if r not in seen]
        if not view:
            break
        nav = _llm_json(llm, "rag.recover.nav", NAV_SYSTEM,
                        f"[질문]\n{query}\n\n[카탈로그(JSON)]\n"
                        f"{json.dumps(view, ensure_ascii=False)}\n\n"
                        f"[이미 본 항목 ref(JSON)]\n{json.dumps(sorted(seen))}",
                        NAV_SCHEMA)
        steps = step + 1
        if nav is None:
            break
        picks = [p for p in nav.get("picks", []) if p in catalog and p not in seen]
        if not picks:
            break
        enough = False
        for ref in picks[:FUNNEL_PICKS_PER_STEP]:
            seen.add(ref)
            doc_id, _, nid = ref.rpartition(":")
            sec: Sec = (doc_id, int(nid))
            v = g.index.docs[doc_id]
            # 자식을 다음 카탈로그에 편다 — 계층을 따라 내려간다
            kids = g.children.get(sec, [])
            for _, kid in kids:
                kn = v.by_id.get(kid) or {}
                kref = f"{doc_id}:{kid}"
                catalog.setdefault(kref, {
                    "ref": kref, "doc": v.name,
                    "title": (kn.get("title") or kn.get("surface") or ""),
                    "children": len(g.children.get((doc_id, kid), [])),
                    "paras": max((kn.get("span") or [0, 0])[1]
                                 - (kn.get("span") or [0, 0])[0], 0)})
            path.append({"ref": ref, "children_added": len(kids)})
            # 이 구역 + 직속 자식의 요약을 판정한다
            sids = [(f"{doc_id}:{sec[1]}", sec)] + \
                   [(f"{d}:{k}", (d, k)) for d, k in kids]
            sview = []
            # 자식은 자르지 않는다 — 장 하나에 조 수십 개가 흔한데, 잘린 조는
            # 판정 자체를 못 받는다. 개수는 문서 구조가 이미 유한하게 만든다.
            for sid, s in sids:
                n = v.by_id.get(s[1]) or {}
                sview.append({"sid": sid, "doc": v.name,
                              "label": v.path(s[1]),
                              "summary": v.section_text(n, cap=220) if n else ""})
            judge = _llm_json(llm, "rag.recover.judge", JUDGE_SYSTEM,
                              f"[질문]\n{query}\n\n[연 구역의 요약(JSON)]\n"
                              f"{json.dumps(sview, ensure_ascii=False)}", JUDGE_SCHEMA)
            if judge is None:
                continue
            best_conf = max(best_conf, float(judge.get("confidence", 0)))
            for sid in judge.get("keep", []):
                d, _, nn = str(sid).rpartition(":")
                if d in g.index.docs and nn.lstrip("-").isdigit():
                    _push(kept, kept_seen, d, int(nn), "깔때기",
                          (judge.get("reason") or "")[:80])
            if judge.get("enough"):
                enough = True
        if enough or nav.get("done") or len(kept) >= FUNNEL_KEEP_CAP:
            break
    meta = {"steps": steps, "confidence": best_conf, "kept": len(kept), "path": path}
    # fail-closed — 신뢰가 문턱 미만이면 전량 폐기. 회색지대는 환각 위험이 크다.
    if not kept or best_conf < CONF_MIN:
        meta["reason"] = "below_threshold" if kept else "no_match"
        return [], meta
    return kept, meta


def rung_fulltext(index: Index, query: str) -> tuple[list, dict]:
    """③ 원문 — 구역 본문을 토큰 부분일치로 뒤진다. 결정론, LLM 없음."""
    toks = [norm(t) for t in tokens_of(query)]
    if not toks:
        return [], {}
    scores: dict[tuple, int] = {}
    for doc_id, v in index.entry_docs.items():       # 진입 — 스코프 안만
        for b in v.blocks:
            t = norm(b.get("text") or "")
            hits = sum(1 for tok in toks if tok in t)
            if not hits:
                continue
            n = v.owner(b.get("idx"))
            if n is None:
                continue
            key = (doc_id, n.get("id"))
            scores[key] = scores.get(key, 0) + hits
    coords: list = []
    seen: set = set()
    for (doc_id, nid), sc in sorted(scores.items(), key=lambda kv: -kv[1])[:FULLTEXT_CAP]:
        _push(coords, seen, doc_id, nid, "원문", f"토큰 {sc}회 일치")
    return coords, {"count": len(coords)}


def rung_scout(llm, g: Graph, catalog: list, query: str) -> tuple[list, dict]:
    """④ 수색대 — 표면을 수확하며 그래프를 걷는 bounded 홉 루프 + 검증 게이트."""
    pats = {p["id"]: p for p in catalog}
    sec_by_term, terms_of_sec = pats.get("sec_by_term"), pats.get("terms_of_sec")
    if sec_by_term is None:
        return [], {}
    surfaces = {norm(t) for t in tokens_of(query)}
    visited: set[tuple] = set()
    entries: list[dict] = []
    hops = 0
    while hops < SCOUT_MAX_HOPS and len(entries) < SCOUT_MAX_ENTRIES:
        hops += 1
        fresh = [s for s in surfaces if ("sec_by_term", s) not in visited]
        if not fresh:
            break
        harvested: set[str] = set()
        for s in fresh:
            visited.add(("sec_by_term", s))
            res = oql.execute(g, sec_by_term, {"tag": s})
            if not res["rows"]:
                continue
            entries.append({"seed": s, **res})
            if len(entries) >= SCOUT_MAX_ENTRIES:
                break
            if terms_of_sec is not None:
                for r in res["rows"]:
                    tr = oql.execute(g, terms_of_sec,
                                     {"sec": f"{r.get('doc_id')}:{r.get('node')}"})
                    harvested |= {row.get("term") for row in tr["rows"] if row.get("term")}
        delta = {s for s in harvested if s and s not in surfaces}
        if not delta:
            break                                    # converged — 새 표면이 없다
        # 정렬 후 자른다 — set 순회로 자르면 어느 표면이 살아남는지 실행마다
        # 달라져 회수 경위를 되짚을 수 없다.
        surfaces |= set(sorted(delta)[:SURFACE_CAP])
    if not entries:
        return [], {"hops": hops, "verified": 0}
    # 검증 게이트 — fail-closed. LLM 이 없거나, 못 믿겠다면 전부 버린다.
    import json
    blocks = []
    for i, e in enumerate(entries):
        body = oql.render_block({"id": e["ontology"], "doc_type": e["doc_type"],
                                 "render": None}, e["rows"][:4]) or ""
        blocks.append({"id": f"b{i}", "seed": e["seed"], "preview": body[:600]})
    out = _llm_json(llm, "rag.recover.verify", VERIFY_SYSTEM,
                    f"[질문]\n{query}\n\n[후보 증거 블록]\n"
                    f"{json.dumps(blocks, ensure_ascii=False)}", VERIFY_SCHEMA)
    if out is None or float(out.get("confidence", 0)) < CONF_MIN or not out.get("keep"):
        return [], {"hops": hops, "verified": 0,
                    "reason": "verify_failed" if out is None else "below_threshold"}
    keep_ids = {str(k) for k in out["keep"]}
    coords: list = []
    seen: set = set()
    for i, e in enumerate(entries):
        if f"b{i}" not in keep_ids:
            continue
        for r in e["rows"][:6]:
            _push(coords, seen, r.get("doc_id"), r.get("node"), "수색대",
                  f"씨앗 '{e['seed']}' → {e['doc_type']}")
    return coords, {"hops": hops, "verified": len(coords),
                    "confidence": out.get("confidence")}


def rung_orient(llm, g: Graph, query: str) -> tuple[list, str, dict]:
    """⑤ 둘러보기 — 보유 문서를 열거해 고르게 한다. 고를 게 없으면 되묻는다."""
    terrain = g.terrain()
    if not terrain:
        return [], "아직 구조화된 문서가 없습니다. 어떤 자료에 대한 질문인가요?", {}
    if llm is None:
        return [], "", {}
    import json
    out = _llm_json(llm, "rag.recover.orient", ORIENT_SYSTEM,
                    f"[질문]\n{query}\n\n[문서 목록(JSON)]\n"
                    f"{json.dumps(terrain, ensure_ascii=False)}", ORIENT_SCHEMA)
    if out is None:
        return [], "", {}
    picks = [p for p in out.get("pick", []) if p.get("doc_id") in g.index.docs]
    if not picks:
        sample = ", ".join(d["doc"] for d in terrain[:5])
        ask = out.get("ask_user") or (f"어느 쪽일까요? 제가 가진 자료 예: {sample}"
                                      if sample else "질문을 좀 더 구체적으로 알려주시겠어요?")
        return [], ask, {"picks": []}
    coords, meta = rung_funnel(llm, g, query, docs=[p["doc_id"] for p in picks])
    for c in coords:
        c["via"] = "둘러보기"
    ask = "" if coords else "고른 문서에서 답을 찾지 못했어요. 좀 더 구체적으로 알려주시겠어요?"
    return coords, ask, {"picks": [p["doc_id"] for p in picks], **meta}


# ---------------------------------------------------------------- 사다리
def run(llm, index: Index, query: str,
        catalog: Optional[list] = None) -> Recovery:
    """회복 사다리 전체 — 매 단은 앞 단이 빈손일 때만 돈다(첫 성공에서 멈춤)."""
    t0 = time.perf_counter()
    g = Graph.from_index(index)
    catalog = catalog or oql.load()
    rec = Recovery()
    log.info("회복 루프 시작 — '%s'", query[:60])

    def record(stage: str, coords: list, note: str = "") -> None:
        rec.trail.append({"stage": stage, "count": len(coords), "note": note})
        log.info("회복 %s — %d건 (누적 %.0fms)%s", stage, len(coords),
                 (time.perf_counter() - t0) * 1000, f" — {note}" if note else "")

    # ⓪ 도메인 단 — 창고의 구조를 아는 지식이 먼저 시도한다 (recover_domains
    #    머리). 법령판은 쟁점 재회수·명칭 확장 — 전부 결정론이라 범용 단보다
    #    수십 배 싸다. 찾으면 범용 사다리는 돌지 않는다(같은 첫-성공 규율).
    if switches.is_on("domain_recover"):
        for rung in recover_domains.rungs():
            coords, dmeta = rung.fn(llm, index, query)
            record(rung.name, coords, dmeta.get("note", ""))
            if coords:
                rec.coords, rec.rungs_fired = coords, [rung.name]
                rec.meta = {rung.name: dmeta}
                return rec

    # ① 의미해석
    coords, branches, meta = rung_sense(llm, g, index, query)
    record("의미해석", coords, meta.get("route", "") or ("건너뜀" if llm is None else ""))
    if coords:
        rec.coords, rec.rungs_fired, rec.meta = coords, ["의미해석"], {"sense": meta}
        return rec

    # ② 깔때기 — 의미해석이 deep_explore 를 골랐거나 가지를 짚었으면 그쪽부터
    coords, fmeta = rung_funnel(llm, g, query, docs=branches or None)
    record("깔때기", coords, fmeta.get("reason", ""))
    if coords:
        rec.coords, rec.rungs_fired, rec.meta = coords, ["깔때기"], {"funnel": fmeta}
        return rec

    # ③ 원문 (결정론)
    coords, tmeta = rung_fulltext(index, query)
    record("원문", coords)
    if coords:
        rec.coords, rec.rungs_fired, rec.meta = coords, ["원문"], {"fulltext": tmeta}
        return rec

    # ④ 수색대
    coords, smeta = rung_scout(llm, g, catalog, query)
    record("수색대", coords, smeta.get("reason", ""))
    if coords:
        rec.coords, rec.rungs_fired, rec.meta = coords, ["수색대"], {"scout": smeta}
        return rec

    # ⑤ 둘러보기
    coords, ask, ometa = rung_orient(llm, g, query)
    record("둘러보기", coords)
    rec.coords, rec.ask_user, rec.meta = coords, ask, {"orient": ometa}
    if coords:
        rec.rungs_fired = ["둘러보기"]
    return rec
