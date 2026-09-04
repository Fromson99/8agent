"""용어집 회수 — 질문 → 용어 → 프레임 → 조문. 회수 전략의 본줄기(2026-08-18).

    질문
     ├ 1-a lexicon.exact       질문에 통째로 있는 용어 (결정론)
     ├ 슬롯 낱말 뽑기 (LLM 1)   질문에서 누가·무엇을·누구에게·한다 를 **질문의 말**로
     ├ 1-b lexicon.neighbors   슬롯 낱말마다 용어집 이웃 ≤8 (필드 안에서, 임베딩)
     ├ 2   좁히기 (결정론)       actor(없으면 target)의 정확·이웃·정의상 상하위어로 프레임 색인을 좁힌다
     ├ 3   줄 세우기 (벡터)      좁힌 프레임을 act·target·object 코사인 합으로 정렬 → 상위 12
     └ 4   고르기 (LLM 2)        12줄 메뉴(조 제목 · 누가→한다→누구에게)를 읽고 조문을 고른다

act 는 문자열로 맞추지 않는다 — 실측(18-0124): 문자열 일치는 §84 를 못 찾고,
actor 로 150개로 좁힌 뒤 act·target 벡터 합으로 줄 세우면 12위, 그 12줄을 읽으면
"협조를 요청할 수 있다 → 국가기관"만이 사안에 맞는다. 격차(받아가다↔협조 요청)를
별칭 표 없이 **메뉴 안의 독해**로 넘긴다 — 깔때기가 조 목록을 읽어 넘던 원리.

LLM 은 두 번, 둘 다 **닫힌 메뉴 위의 선택**이다 — 낱말을 지어내지 않는다. 메뉴는
용어집에서 왔으니 골라진 낱말은 반드시 코퍼스 어딘가의 표면형이고, 프레임 색인의
그 필드에 그대로 있다. 이것이 슬롯을 자유 생성하던 framequery 와 다른 점이다
(그건 44마디 실측에서 졌다 — 생성한 낱말이 색인에 없어서).

한계(정직): 이웃이 기관↔사람·일상동사↔술어를 못 잇는다(국세청→세무공무원 ✗,
받아가다→협조 요청 ✗ — 실측). 그 격차는 ① 판별 단이 이웃 목록에서 뜻으로 고르며
얼마간, ② 원장·깔때기 착지에서 자라는 별칭이 나머지를 메운다. 첫 질문에서 못
잡으면 루프(법 스코프 깔때기)로 간다 — 그게 이 전략의 마지막 줄이다.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from lawrag.core.rag import frames as frames_mod
from lawrag.core.rag import lexicon as lexicon_mod
from lawrag.core.rag.index import Index

log = logging.getLogger("lawrag.core.rag.termretrieve")

SLOT_FIELDS = ("actor", "act", "target", "object")
FRAME_MAX = 2
COORD_MAX = 8

SLOT_SYSTEM = (
    "너는 법령 질문 분해기다. 질문에서 '누가(actor) → 누구에게(target) → 무엇을(object) "
    "→ 한다(act)'의 낱말을 **질문에 쓰인 말 그대로** 뽑는다 — 바꿔 쓰지 마라(국세청이면 "
    "국세청, 받아가다면 받아가다). 한 질문에 사안이 둘이면 둘. 없는 칸은 빈 문자열. "
    "act_alts 에는 그 행위를 조문이 쓸 법한 술어로 옮긴 후보를 2~3개 적는다(받아가다 → "
    "요청하다·제출받다·제공받다) — 이건 줄 세우기 보조다."
)
SLOT_SCHEMA = {
    "type": "object",
    "properties": {"frames": {"type": "array", "items": {
        "type": "object",
        "properties": {k: {"type": "string"} for k in SLOT_FIELDS},
        "required": list(SLOT_FIELDS), "additionalProperties": False}}},
    "required": ["frames"], "additionalProperties": False,
}

JUDGE_SYSTEM = (
    "너는 법령 검색의 용어 판별기다. 질문과, 질문 낱말마다 **코퍼스 용어집에서 찾은 "
    "후보**(정확 일치·이웃)를 받는다. 후보 중 이 사안에 맞는 용어만 남기고 나머지는 "
    "버린 뒤, 남긴 용어로 '누가→누구에게→무엇을→한다' 프레임을 1~2개 조립한다.\n"
    "규칙: ① 프레임의 칸에는 **후보 목록에 있는 용어만** 쓴다 — 없는 낱말을 지어내지 "
    "마라(그 낱말은 색인에 없어 아무것도 못 찾는다). ② 뜻이 같으면 표기가 달라도 "
    "고른다 — 질문의 '국세청'에 후보 '국세청장'·'과세관청'이 있으면 그것이 조문의 말이다. "
    "후보에 '정의상 상위어'가 붙어 있으면(예: '세무공무원' — 국세기본법 §2 17호가 국세청장을 "
    "세무공무원의 하나로 정의) **조문은 그 상위어로 쓴다** — 그것을 고르는 것이 맞다. ③ 맞는 후보가 없는 칸은 빈 문자열로 둔다 — 억지로 채우지 마라. "
    "④ 버린 후보는 drop 에 **낱말만** 적는다(이유 없이, 최대 6개) — 길게 쓰면 출력이 잘린다."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "frames": {"type": "array", "items": {
            "type": "object",
            "properties": {k: {"type": "string"} for k in SLOT_FIELDS},
            "required": list(SLOT_FIELDS), "additionalProperties": False}},
        "drop": {"type": "array", "items": {"type": "string"}}},
    "required": ["frames", "drop"], "additionalProperties": False,
}


def _pack(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


# ---------------------------------------------------------------- 질문 → 프레임
def slots(llm, question: str) -> list[dict]:
    """LLM 1 — 질문의 말 그대로 슬롯 낱말."""
    out = llm.structured("rag.term.slots", SLOT_SYSTEM, f"[질문]\n{question}",
                         SLOT_SCHEMA, max_tokens=300, effort="low")
    if not out:
        return []
    return [f for f in out.get("frames", [])[:FRAME_MAX]
            if any((f.get(k) or "").strip() for k in SLOT_FIELDS)]


def candidates(lx: lexicon_mod.Lexicon, question: str, qframes: list[dict],
               tx=None) -> dict:
    """1-a + 1-b + 상위어 확장 — 정확 히트와 슬롯별 이웃 메뉴, 그리고 정의 조가
    선언한 상위어(taxonomy). '국세청' → 이웃 '국세청장' → 상위어 '세무공무원'
    (국세기본법 §2 17호)이 메뉴에 근거와 함께 오른다."""
    exact = lx.exact(question)
    per_slot: list[dict] = []
    for f in qframes:
        row = {}
        for k in SLOT_FIELDS:
            w = (f.get(k) or "").strip()
            if not w:
                continue
            ex = [e["term"] for e in exact if _pack(e["term"]) in _pack(w) or _pack(w) in _pack(e["term"])]
            nb = lx.neighbors(w, field=k)
            ups: list[dict] = []
            if tx is not None:
                seen_up = set()
                for cand in [w] + ex[:4] + [n["term"] for n in nb]:
                    for h in tx.hypernyms(cand):
                        key = _pack(h["term"])
                        if key in seen_up or key == _pack(w):
                            continue
                        seen_up.add(key)
                        ups.append({"term": h["term"], "of": cand,
                                    "why": f"{h['doc'][:12]} {h['path'].split(' ▸ ')[-1][:16]}이 '{cand}'을 '{h['term']}'의 하나로 정의"})
                        if len(ups) >= 4:
                            break
                    if len(ups) >= 4:
                        break
            row[k] = {"word": w, "exact": ex[:4], "neighbors": [n["term"] for n in nb],
                      "neighbors_scored": [(n["term"], n["cos"]) for n in nb],
                      "hypernyms": ups}
        per_slot.append(row)
    return {"exact": exact, "slots": per_slot}


def judge(llm, question: str, cand: dict) -> tuple[list[dict], list[str]]:
    """LLM 2 — 후보를 보고 남길 용어를 고르고 프레임으로 조립. 닫힌 메뉴."""
    menu = []
    for i, row in enumerate(cand["slots"], 1):
        for k, c in row.items():
            line = (f"[사안{i}·{k}] 질문 낱말 '{c['word']}' → 정확: {c['exact'] or '없음'} · "
                    f"이웃: {c['neighbors'] or '없음'}")
            if c.get("hypernyms"):
                line += " · 정의상 상위어: " + " / ".join(
                    f"'{u['term']}' ({u['why']})" for u in c["hypernyms"])
            menu.append(line)
    ex_txt = " · ".join(e["term"] for e in cand["exact"][:12]) or "없음"
    user = (f"[질문]\n{question}\n\n[질문에 통째로 있는 용어]\n{ex_txt}\n\n"
            f"[슬롯별 후보]\n" + "\n".join(menu))
    out = llm.structured("rag.term.judge", JUDGE_SYSTEM, user, JUDGE_SCHEMA,
                         max_tokens=1200, effort="low")
    if not out:
        return [], []
    allowed = {_pack(e["term"]) for e in cand["exact"]}
    for row in cand["slots"]:
        for c in row.values():
            allowed |= {_pack(t) for t in c["exact"]} | {_pack(t) for t in c["neighbors"]}
            allowed |= {_pack(u["term"]) for u in c.get("hypernyms", [])}
    frames = []
    for f in out.get("frames", [])[:FRAME_MAX]:
        clean = {}
        for k in SLOT_FIELDS:
            v = (f.get(k) or "").strip()
            clean[k] = v if _pack(v) in allowed else ""      # 메뉴 밖 낱말은 버린다
        if any(clean.values()):
            frames.append(clean)
    return frames, [str(d)[:80] for d in out.get("drop", [])[:8]]


# ---------------------------------------------------------------- 3 프레임 일치 조회
W = {"actor": 2.0, "act": 2.0, "target": 1.0, "object": 1.0}


def _hit(a: str, b: str) -> bool:
    pa, pb = _pack(a), _pack(b)
    if not pa or not pb:
        return False
    return pa == pb or (len(pa) >= 3 and pa in pb) or (len(pb) >= 3 and pb in pa)


def framematch(index: Index, qframe: dict, cap: int = COORD_MAX) -> list[dict]:
    """프레임 색인에서 필드 일치로 조 좌표 — [{doc_id, node, jo, score, why}].
    actor·act 둘 다 있으면 둘 다 맞아야 하고, 하나만 있으면 그것 + 다른 칸 하나."""
    want = {k: (qframe.get(k) or "").strip() for k in SLOT_FIELDS}
    n_want = sum(1 for v in want.values() if v)
    if n_want == 0:
        return []
    best: dict[tuple, dict] = {}
    for did, v in index.entry_docs.items():          # 진입 — 스코프 안만
        for r in frames_mod.load(did):
            score, matched = 0.0, []
            for k in SLOT_FIELDS:
                if want[k] and _hit(want[k], r.get(k) or ""):
                    score += W[k]
                    matched.append(k)
            if not matched:
                continue
            need = 2 if n_want >= 2 else 1
            if len(matched) < need:
                continue
            if want["actor"] and want["act"] and not ({"actor", "act"} <= set(matched)):
                # 주체와 행위를 다 물었으면 둘 다 맞아야 — 하나만 맞으면 다른 사안이다
                continue
            key = (did, r["jo"])
            if key not in best or best[key]["score"] < score:
                best[key] = {"doc_id": did, "node": r["jo"], "jo": r["jo"], "score": score,
                             "why": " · ".join(f"{k}={r.get(k, '')[:14]}" for k in matched),
                             "via": "용어집 프레임"}
    return sorted(best.values(), key=lambda x: -x["score"])[:cap]


# ---------------------------------------------------------------- 좁히기 → 줄 세우기 → 고르기
NARROW_NEIGHBOR_MIN = 0.72     # actor/target 이웃을 집합에 넣는 문턱 — 이웃 8개를 다 넣으면 집합이 새는다
MENU = 40                 # 실측: §84 가 벡터 27위 — 20이면 빠지고 40이면 선택기가 읽어 고른다
PICK_MAX = 3
RANK_W = {"act": 1.0, "target": 1.0, "object": 0.5}   # object 는 보조 — 정답 조에 그 낱말이 없을 때가 많다
PICK_SYSTEM = (
    "너는 법령 검색의 조문 선택기다. 질문과, 질문의 주체(또는 상대)로 좁힌 조문 프레임 "
    "목록(번호 · 문서 · 조 제목 · 누가→한다→누구에게/무엇을)을 받는다. 질문의 사안에 "
    "**실제로 맞는** 줄만 고른다 — 최대 3개, 확신 순, 없으면 빈 배열. 질문이 두 사안"
    "(받는 것·넘기는 것)을 담으면 각각의 줄을 고른다. 낱말이 안 겹쳐도 "
    "뜻이 같으면 고른다(질문의 '다른 기관에서 받아간다'는 조문에선 '국가기관에 협조를 "
    "요청할 수 있다'일 수 있다). 왜 골랐는지 한 줄."
)
PICK_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {
        "type": "object",
        "properties": {"idx": {"type": "integer"}, "why": {"type": "string"}},
        "required": ["idx", "why"], "additionalProperties": False}}},
    "required": ["picks"], "additionalProperties": False,
}


def _actor_set(lx, tx, cand_row: dict) -> set:
    """슬롯 하나(actor 또는 target)의 낱말 집합 — 정확 + 이웃(문턱) + 정의상 상위어·하위어."""
    out: set = set()
    if not cand_row:
        return out
    w = cand_row.get("word", "")
    out |= {_pack(t) for t in cand_row.get("exact", [])}
    for t in cand_row.get("neighbors_scored", []):
        if t[1] >= NARROW_NEIGHBOR_MIN:
            out.add(_pack(t[0]))
    for u in cand_row.get("hypernyms", []):
        out.add(_pack(u["term"]))
    if tx is not None:
        for base in list(out) + [_pack(w)]:
            for h in tx.hyponyms(base):
                out.add(_pack(h["term"]))
            for h in tx.hypernyms(base):
                out.add(_pack(h["term"]))
    # 3자 이상 + 일반어 제외 — "사람"(§2 17호 '다음 각 목의 사람'이 상위어로 뽑힘)·
    # "기관"·"자료" 같은 낱말이 집합에 들면 좁히기가 안 좁힌다(실측: 196개 중 개보법
    # 벌칙·국가계약법 위원회 조가 앞자리).
    return {x for x in out if len(x) >= 3 and x not in _GENERIC}


_GENERIC = {"사람", "기관", "자료", "정보", "사항", "경우", "위원회", "공무원", "국세", "법인",
            "단체", "개인", "회사", "장관", "대통령령", "법령"}


def narrow(index: Index, lx, tx, cand_row_actor: dict, cand_row_target: dict) -> tuple[list, str]:
    """actor 집합으로 프레임을 좁힌다; actor 가 없으면 target 으로. (rows, 무엇으로)"""
    for field, row in (("actor", cand_row_actor), ("target", cand_row_target)):
        S = _actor_set(lx, tx, row)
        if not S:
            continue
        rows = []
        for did, v in index.entry_docs.items():
            if lx.doc_ids is not None and did not in lx.doc_ids:
                continue
            for r in frames_mod.load(did):
                a = _pack(r.get(field) or "")
                # 한 방향만 — 집합 낱말이 프레임 actor **안에** 있어야 한다. 반대(프레임
                # actor 가 집합 낱말 안에)는 "위원회"·"국세" 같은 조각이 다 물린다.
                if a and any(x in a for x in S):
                    rows.append((did, r))
        if rows:
            return rows, f"{field}∈{{{'·'.join(sorted(S)[:5])}{'…' if len(S) > 5 else ''}}}"
    return [], ""


def rank(lx, rows: list, qwords: dict) -> list:
    """좁힌 프레임을 act·target·object 벡터 코사인 합으로 정렬. 질문에 없는 칸은 0."""
    import numpy as np
    from lawrag.core import embedding
    if lx.vec is None:
        return [(0.0, d, r) for d, r in rows][:MENU]
    pos = {t: i for i, t in enumerate(lx.names)}
    qv: dict = {}
    for k in ("act", "target", "object"):
        words = [w for w in ([qwords.get(k, "")] + (qwords.get(k + "_alts") or [])) if (w or "").strip()]
        vs = []
        for w in words[:4]:
            v = np.asarray(embedding.encode_one(w), dtype=np.float32)
            vs.append(v / (np.linalg.norm(v) + 1e-9))
        if vs:
            qv[k] = vs
    scored = []
    for d, r in rows:
        s = 0.0
        for k, vs in qv.items():
            i = pos.get((r.get(k) or "").strip())
            if i is not None:
                s += RANK_W.get(k, 1.0) * max(float(lx.vec[i] @ v) for v in vs)   # 후보 중 최고
        scored.append((s, d, r))
    scored.sort(key=lambda x: -x[0])
    # 같은 조는 한 줄만 (가장 높은 프레임)
    out, seen = [], set()
    for s, d, r in scored:
        if (d, r["jo"]) in seen:
            continue
        seen.add((d, r["jo"]))
        out.append((s, d, r))
        if len(out) >= MENU:
            break
    return out


def pick(llm, index: Index, question: str, menu: list) -> list[dict]:
    """LLM 2 — 12줄 메뉴에서 조문을 고른다."""
    if not menu:
        return []
    lines = []
    for i, (s, d, r) in enumerate(menu, 1):
        v = index.docs[d]
        lines.append(f"[{i}] {v.name[:14]} ▸ {v.path(r['jo']).split(' ▸ ')[-1][:28]} | "
                     f"{(r.get('actor') or '')[:12]} → {(r.get('act') or '')[:26]} → "
                     f"{(r.get('target') or '')[:14]} / {(r.get('object') or '')[:14]}")
    out = llm.structured("rag.term.pick", PICK_SYSTEM,
                         f"[질문]\n{question}\n\n[프레임 목록]\n" + "\n".join(lines),
                         PICK_SCHEMA, max_tokens=400, effort="low")
    if not out:
        return []
    coords = []
    for p in out.get("picks", [])[:PICK_MAX]:
        i = p.get("idx")
        if isinstance(i, int) and 1 <= i <= len(menu):
            s, d, r = menu[i - 1]
            coords.append({"doc_id": d, "node": r["jo"], "jo": r["jo"], "score": round(s, 3),
                           "why": (p.get("why") or "")[:80], "via": "용어집 프레임"})
    return coords


# ---------------------------------------------------------------- 한 줄로
def retrieve(llm, index: Index, question: str) -> tuple[list[dict], dict]:
    """질문 → 좌표들. (coords, meta). LLM 2콜(슬롯·선택). 빈손이면 [] — 호출부가 루프로 간다."""
    from lawrag.core.rag import taxonomy as taxonomy_mod
    lx = lexicon_mod.current(index)
    tx = taxonomy_mod.current(index, lx, lx.doc_ids)
    meta: dict = {"exact": [], "slots": [], "narrow": "", "menu": 0, "picked": []}
    if llm is None:
        meta["exact"] = [e["term"] for e in lx.exact(question)]
        return [], meta
    qf = slots(llm, question)
    cand = candidates(lx, question, qf, tx=tx)
    meta["exact"] = [e["term"] for e in cand["exact"]]
    meta["slots"] = cand["slots"]
    coords: list[dict] = []
    seen = set()
    for i, row in enumerate(cand["slots"]):
        rows, how = narrow(index, lx, tx, row.get("actor", {}), row.get("target", {}))
        if not rows:
            continue
        qw = {k: row.get(k, {}).get("word", "") for k in ("act", "target", "object")}
        qw["act_alts"] = (qf[i].get("act_alts") or []) if i < len(qf) else []
        menu = rank(lx, rows, qw)
        meta["narrow"] = how
        meta["menu"] = len(menu)
        for c in pick(llm, index, question, menu):
            if (c["doc_id"], c["node"]) in seen:
                continue
            seen.add((c["doc_id"], c["node"]))
            coords.append(c)
        if len(coords) >= COORD_MAX:
            break
    meta["picked"] = [c["why"] for c in coords]
    return coords[:COORD_MAX], meta
