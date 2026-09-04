"""계층 사후 교정 — 파이프라인이 잘못 붙인 마디를 사람이 제자리로 옮긴다.

## 왜 덮어쓰지 않고 겹쳐 읽는가

`result.json` 은 해석의 산출이다. 거기에 직접 손대면 **다시 해석하는 순간**
사라진다(규칙 한 줄 고치면 재해석은 늘 일어난다). 그래서 교정은 links.json ·
edge_rules.json 과 같은 규약을 따른다 — 별도 파일에 (문서, 마디) → 새 부모로
남기고, 읽는 쪽이 겹쳐 읽는다. 재해석해도 교정은 살아남고, 교정이 틀렸으면
지우면 원본이 그대로 돌아온다.

## 무엇을 고칠 수 있나

**부모만** 고친다. level 은 부모에서 다시 계산한다 — 손으로 매기면 부모와
어긋난 층이 생긴다(트리가 두 개의 진실을 갖는다). surface·title·span 은
건드리지 않는다: 그건 파싱의 산출이지 계층 판단이 아니다.

    "6) 집합투자업자의 합병…" 이 "라. 투자운용인력의 변경…" 의 형제로 붙었다
      → 6) 의 부모를 라. 로 옮긴다(들여쓰기). 아래 자손도 층이 함께 내려간다.

## 규칙(어휘)과 무엇이 다른가

custom/*.yaml 은 **표면 패턴**이라 문서를 안 가린다(SPEC §6 — level·parent
금지). 여기 교정은 정반대로 **이 문서의 이 마디**만 가리키는 좌표 수정이다.
같은 오해가 여러 문서에서 반복되면 그때가 규칙을 만들 자리다 — 교정은 그
증거로도 쌓인다(어느 표면형이 자꾸 잘못 붙는지).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.platform.paths import runtime_path

# 경로 규약은 core.rag.index.store_path 와 같다. import 하지 않고 같은 식을
# 다시 쓰는 이유는 순환 때문이다 — index 가 이 모듈을 부른다.
def _store() -> Path:
    return Path(
        os.environ.get("STRUCTURE_STORE")
        or runtime_path("out", "structure", "viewer")
    )


def fixes_path() -> Path:
    return Path(os.environ.get("STRUCTURE_FIXES_STORE",
                               _store().parent / "structure_fixes.json"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> list[dict]:
    p = fixes_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("fixes", [])
    except Exception:
        return []


def for_doc(doc_id: str) -> dict:
    """문서의 교정 — {node: fix}. 같은 마디를 여러 번 고치면 마지막이 이긴다."""
    return {f["node"]: f for f in load() if f.get("doc_id") == doc_id}


def _save(rows: list[dict]) -> None:
    p = fixes_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"fixes": rows}, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def record(doc_id: str, node: int, parent: Optional[int],
           before: Optional[dict] = None, note: str = "") -> dict:
    """교정 하나를 남긴다(같은 마디의 옛 교정은 갈아 끼운다)."""
    rows = [f for f in load()
            if not (f.get("doc_id") == doc_id and f.get("node") == node)]
    row = {"doc_id": doc_id, "node": node, "parent": parent,
           "before": before or {}, "메모": note, "ts": _now()}
    rows.append(row)
    _save(rows)
    return row


def remove(doc_id: str, node: int) -> int:
    rows = load()
    keep = [f for f in rows
            if not (f.get("doc_id") == doc_id and f.get("node") == node)]
    if len(keep) != len(rows):
        _save(keep)
    return len(rows) - len(keep)


def _would_cycle(by_parent: dict, node: int, new_parent: Optional[int]) -> bool:
    """새 부모가 이 마디의 자손이면 고리가 된다 — 트리가 아니게 된다."""
    cur, seen = new_parent, set()
    while cur is not None and cur not in seen:
        if cur == node:
            return True
        seen.add(cur)
        cur = by_parent.get(cur)
    return False


def apply(doc_id: str, nodes: list[dict]) -> list[dict]:
    """교정을 겹쳐 읽은 마디 목록. 원본 리스트·딕트는 건드리지 않는다.

    부모를 옮긴 뒤 **level 을 뿌리부터 다시 센다** — 옮긴 가지의 자손까지
    층이 함께 따라온다. 고리를 만드는 교정은 조용히 무시한다(트리가 먼저다).
    """
    fixes = for_doc(doc_id)
    if not fixes:
        return nodes
    out = [dict(n) for n in nodes]
    by_id = {n.get("id"): n for n in out}
    by_parent = {n.get("id"): n.get("parent") for n in out}
    for nid, f in fixes.items():
        n = by_id.get(nid)
        if n is None:
            continue                      # 재해석으로 사라진 마디 — 교정도 무의미
        new_parent = f.get("parent")
        if new_parent is not None and new_parent not in by_id:
            continue
        if _would_cycle(by_parent, nid, new_parent):
            continue
        n["parent"] = new_parent
        by_parent[nid] = new_parent
        n["교정됨"] = True
    # level 재계산 — 뿌리(부모 없음)가 원래 level 을 유지하고 아래로 +1
    kids: dict = {}
    for n in out:
        kids.setdefault(n.get("parent"), []).append(n)
    stack = [(n, n.get("level", 1)) for n in kids.get(None, [])]
    seen: set = set()
    while stack:
        n, lv = stack.pop()
        nid = n.get("id")
        if nid in seen:
            continue
        seen.add(nid)
        n["level"] = lv
        for k in kids.get(nid, []):
            stack.append((k, lv + 1))
    return out
