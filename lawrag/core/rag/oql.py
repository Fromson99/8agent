"""OQL — 탐험 규칙(패턴) 카탈로그·검증·실행기. DB 없이.

원본(DELTAFlow)의 OQL 은 YAML 패턴을 안전한 bounded READ-ONLY Cypher 로
컴파일해 Neo4j 에 던졌다. 여기서는 **같은 패턴 형식**을 코퍼스 그래프
(lawrag/core/rag/graph.py) 걷기로 실행한다 — 패턴은 여전히 데이터고, 컴파일러 대신
걸음 해석기가 있다. 원본과의 이름 차이 하나: seed.match 의 슬롯이
`tag_number_prop` 이 아니라 `key_prop` 이다(도메인 냄새를 뺐다).

원본에서 그대로 가져온 규율:
    · limit 필수, 상한 500 — 무한 traversal 방지
    · return 식은 화이트리스트(`별칭.속성` 꼴)만 — 함수·연산자 금지
    · 파라미터는 선언된 것만, 값은 치환이 아니라 바인딩
    · milestones — 결과를 버킷으로 접고, 깊이 선택은 1..N **누적** 컷
    · 렌더 틀의 빈 키는 "" — 행 하나가 깨져도 블록이 죽지 않는다
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import yaml

from lawrag.core.rag.graph import Graph
from lawrag.core.rag.index import norm

CATALOG = Path(__file__).resolve().parent / "patterns.yaml"
LIMIT_CEILING = 500
RENDER_ROW_CAP = 16
MILESTONE_CAP = 24
WORLDS = {"doc", "term", "structured"}
RELS = {"MENTIONS", "HAS_CHILD", "SIBLING", "BRIDGE"}
LABELS = {"Term", "Section"}

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_RET_EXPR_RE = re.compile(rf"^{_IDENT}(?:\.{_IDENT})?$")


# ---------------------------------------------------------------- 카탈로그
def load(path: Optional[Path] = None) -> list[dict]:
    data = yaml.safe_load(Path(path or CATALOG).read_text(encoding="utf-8"))
    pats = data.get("patterns", [])
    seen: set[str] = set()
    for p in pats:
        validate(p)
        if p["id"] in seen:
            raise ValueError(f"패턴 id 중복: {p['id']}")
        seen.add(p["id"])
    return pats


def validate(pat: dict) -> None:
    """원본 catalog.py 의 검증을 걷기 실행기에 맞게 옮긴 것. 어기면 거부."""
    pid = pat.get("id")
    if not pid:
        raise ValueError("패턴에 id 가 없습니다")
    lim = pat.get("limit")
    if not isinstance(lim, int) or not (1 <= lim <= LIMIT_CEILING):
        raise ValueError(f"{pid}: limit 은 1..{LIMIT_CEILING} 정수 필수 — 무한 traversal 방지")
    if pat.get("world") not in WORLDS:
        raise ValueError(f"{pid}: world 는 {sorted(WORLDS)} 중 하나")
    params = {p["name"] for p in pat.get("parameters", [])}
    trav = pat.get("traversal") or {}
    seed = trav.get("seed") or {}
    labels = seed.get("labels") or []
    if not labels or any(l not in LABELS for l in labels):
        raise ValueError(f"{pid}: seed.labels 는 {sorted(LABELS)} 중에서")
    match = seed.get("match") or {}
    if set(match.keys()) != {"key_prop", "param"}:
        raise ValueError(f"{pid}: seed.match 는 key_prop·param 두 슬롯 고정")
    if match["param"] not in params:
        raise ValueError(f"{pid}: seed.match.param '{match['param']}' 이 parameters 에 없습니다")
    aliases = {"se"}
    for st in trav.get("steps") or []:
        if st.get("rel") not in RELS:
            raise ValueError(f"{pid}: rel 은 {sorted(RELS)} 중에서 ({st.get('rel')})")
        if st.get("direction", "out") not in ("out", "in"):
            raise ValueError(f"{pid}: direction 은 out|in")
        a = st.get("alias")
        if not a or a in aliases:
            raise ValueError(f"{pid}: step alias 는 고유해야 하고 'se' 금지 ({a})")
        aliases.add(a)
    rets = pat.get("return") or []
    if not rets:
        raise ValueError(f"{pid}: return 이 비었습니다")
    ret_as = set()
    for r in rets:
        if not _RET_EXPR_RE.match(r.get("expr", "")):
            raise ValueError(f"{pid}: return 식 화이트리스트 위반 — {r.get('expr')!r}")
        ret_as.add(r.get("as"))
    ms = pat.get("milestones") or {}
    for k in ("by", "order", "preview"):
        if ms.get(k) and ms[k] not in ret_as:
            raise ValueError(f"{pid}: milestones.{k} 는 return 의 as 중 하나여야 합니다")


# ---------------------------------------------------------------- 걷기 실행
# 노드 표현: ("term", key) | ("sec", (doc_id, node_id))

def _props(g: Graph, node: tuple) -> dict:
    kind, val = node
    if kind == "term":
        return {"term": val, "n": len(g.term_secs.get(val, []))}
    doc_id, nid = val
    v = g.index.docs.get(doc_id)
    if v is None:
        return {}
    n = v.by_id.get(nid) or {}
    return {"doc_id": doc_id, "node": nid, "doc": v.name,
            "title": (n.get("title") or n.get("surface") or ""),
            "path": v.path(nid) or v.name, "page": n.get("page"),
            "level": n.get("level"),
            "preview": v.section_text(n, cap=120) if n else ""}


def _walk(g: Graph, node: tuple, rel: str, direction: str) -> list[tuple]:
    kind, val = node
    if rel == "MENTIONS":
        if kind == "term" and direction == "out":
            return [("sec", s) for s, _ in g.sections_of(val)]
        if kind == "sec" and direction == "in":
            return [("term", k) for k in g.terms_of(val)]
    if kind == "sec" and rel == "HAS_CHILD":
        if direction == "out":
            return [("sec", s) for s in g.children.get(val, [])]
        p = g.parent.get(val)
        return [("sec", p)] if p else []
    if kind == "sec" and rel == "SIBLING":
        return [("sec", s) for s in g.siblings(val)]
    if kind == "sec" and rel == "BRIDGE":
        return [("sec", s) for s, _ in g.bridge(val)]
    return []


def _seed_nodes(g: Graph, label: str, key_prop: str, value: str) -> list[tuple]:
    if label == "Term":
        key = norm(value)
        return [("term", key)] if key in g.term_secs else []
    # Section — 좌표 문자열 "doc_id:node"
    doc_id, _, nid = str(value).rpartition(":")
    if not doc_id or not nid.lstrip("-").isdigit():
        return []
    sec = (doc_id, int(nid))
    return [("sec", sec)] if g.index.docs.get(doc_id) else []


def execute(g: Graph, pat: dict, params: dict) -> dict:
    """패턴 하나를 걷는다 → 원본 format_pattern_result 와 같은 봉투."""
    trav = pat["traversal"]
    seed = trav["seed"]
    pname = seed["match"]["param"]
    value = params.get(pname)
    if value in (None, ""):
        raise ValueError(f"필수 파라미터 누락: {pname}")

    lim = pat["limit"]
    paths: list[dict] = [{"se": n} for n in
                         _seed_nodes(g, seed["labels"][0], seed["match"]["key_prop"],
                                     str(value))]
    prev = "se"
    for st in trav.get("steps") or []:
        nxt: list[dict] = []
        for b in paths:
            for out in _walk(g, b[prev], st["rel"], st.get("direction", "out")):
                nxt.append({**b, st["alias"]: out})
                if len(nxt) >= lim * 4:            # 폭발 방지 — 마지막에 limit 로 자른다
                    break
            if len(nxt) >= lim * 4:
                break
        paths = nxt
        prev = st["alias"]

    rows: list[dict] = []
    seen: set[tuple] = set()
    for b in paths:
        row = {}
        for r in pat["return"]:
            alias, _, prop = r["expr"].partition(".")
            node = b.get(alias)
            row[r["as"]] = (_props(g, node).get(prop) if node and prop else
                            (str(node) if node else None))
        key = tuple(sorted((k, str(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if len(rows) >= lim:
            break

    return {"ontology": pat["id"], "doc_type": pat.get("doc_type", pat["id"]),
            "kind": pat.get("result_kind", "OQLResult"),
            "world": pat.get("world", "doc"),
            "params": dict(params), "count": len(rows), "rows": rows}


# ---------------------------------------------------------------- 마일스톤
def _bucket_key(row: dict, by: str) -> str:
    v = row.get(by)
    return str(v) if v not in (None, "") else "(빈값)"


def build_milestones(pat: dict, rows: list[dict]) -> tuple[Optional[str], list[dict], bool]:
    """행들을 버킷으로 접는다 — "몇 번까지 볼래?" 의 선택지. 원본 그대로."""
    spec = pat.get("milestones") or {}
    by, cutoff = spec.get("by"), bool(spec.get("cutoff"))
    if not by:
        return None, [{"key": "(전체)", "count": len(rows), "preview": ""}], cutoff
    order, prev = spec.get("order"), spec.get("preview")
    buckets: dict[str, dict] = {}
    for r in rows:
        k = _bucket_key(r, by)
        b = buckets.setdefault(k, {"key": k, "count": 0, "preview": "", "_o": None})
        b["count"] += 1
        if prev and not b["preview"] and r.get(prev):
            b["preview"] = str(r[prev]).replace("\n", " ")[:80]
        if order and b["_o"] is None and r.get(order) is not None:
            b["_o"] = r.get(order)
    items = list(buckets.values())
    if order:
        items.sort(key=lambda b: (b["_o"] is None, b["_o"]))
    for b in items:
        b.pop("_o", None)
    return by, items[:MILESTONE_CAP], cutoff


def filter_by_depth(rows: list[dict], by: Optional[str], milestones: list[dict],
                    depth) -> list[dict]:
    """깊이 적용 — 정수 N 은 1..N **누적** 컷. 원본 filter_by_depth 그대로."""
    if depth == "NONE":
        return []
    if depth == "ALL" or not by:
        return rows
    if isinstance(depth, int):
        keys = {m["key"] for m in milestones[:depth]}
    elif isinstance(depth, list):
        keys = {str(s) for s in depth}
    else:
        return rows
    return [] if not keys else [r for r in rows if _bucket_key(r, by) in keys]


# ---------------------------------------------------------------- 렌더
class _Safe(dict):
    def __missing__(self, key):                     # 빈 키 → "" — 행 하나가 블록을 못 죽인다
        return ""


def render_block(pat: dict, rows: list[dict]) -> Optional[str]:
    if not rows:
        return None
    lines = [f"### {pat.get('doc_type', pat['id'])}"]
    tmpl = pat.get("render")
    for r in rows[:RENDER_ROW_CAP]:
        clean = {k: ("" if v is None else v) for k, v in r.items()}
        if tmpl:
            try:
                lines.append(tmpl.format_map(_Safe(clean)))
                continue
            except Exception:
                pass
        lines.append("- " + ", ".join(f"{k}={v}" for k, v in clean.items() if v != ""))
    return "\n".join(lines) if len(lines) > 1 else None
