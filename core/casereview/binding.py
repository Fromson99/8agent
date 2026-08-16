"""의존성 원장 — 우리 자산이 어느 조문에 매여 있는가 (docs/REVIEW.md §Binding).

**트랙 B(적법성 검토)가 생산하고 트랙 A(개정 추적)가 소비한다.** B 에서 "이
서비스가 전자금융감독규정 제15조에 걸리고 이러이러하게 통과했다"를 검토했으면
그 결과를 여기 남긴다. 나중에 제15조가 개정되면 원장을 역인덱스로 뒤집어
**영향받는 자산 목록**이 즉시 나온다. 이게 없으면 A 는 개정마다 전수 재검토라
실무에서 안 돌아간다.

진단 튜플(data/rag/tuples)과 성격이 다르다 — 그건 **관측**이라 append-only 로
고쳐 쓰지 않지만, 이건 **자산의 현재 상태**를 들고 있는 원장이라 재검토하면
갱신된다. 그래서 파일도 jsonl 이 아니라 json 이고, 자산+좌표가 키다.

    {"asset": "우리 서비스명", "doc": "전자금융감독규정", "node": 412,
     "path": "제15조 ▸ ①", "issue": "망분리 적용 대상인가",
     "judgment": "충족", "conclusion": "조건부", "rid": "R…", "at": "…"}

자산 이름은 사람이 준다 — 시스템이 서비스 이름을 알 길이 없다. 자산 없이
검토하면(track=해석) 적재하지 않는다: 원장은 "무엇이 무엇에 매였나"의 기록이지
질의 로그가 아니다.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]


def ledger_path() -> Path:
    return Path(os.environ.get("REVIEW_BINDINGS")
                or ROOT / "data" / "review" / "bindings.json")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def load() -> list[dict]:
    p = ledger_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text("utf-8"))
        return data.get("bindings", [])
    except Exception:                      # 깨진 원장은 없는 것으로 — 검토를 죽이지 않는다
        return []


def _save(rows: list[dict]) -> None:
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bindings": rows}, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _key(b: dict) -> tuple:
    return (b.get("asset", ""), b.get("doc", ""), b.get("node"), b.get("issue", ""))


def record(state, asset: str) -> int:
    """검토 상태를 원장에 적재한다 — 같은 (자산·조문·쟁점)은 **갱신**한다.

    재검토가 과거 판정을 덮는 것이 맞다: 원장은 현재 상태를 말해야 하고,
    이력이 필요하면 진단 튜플(관측)이 그 몫이다. 적재한 줄 수를 돌려준다.
    """
    if not asset or not state.subs:
        return 0
    by_issue = {v.issue_id: v for v in state.verdicts}
    fresh: list[dict] = []
    for s in state.subs:
        n = state.norm(s.norm_id)
        i = state.issue(s.issue_id)
        if n is None or i is None:
            continue
        if s.judgment == "해당없음":
            continue          # 매이지 않은 것은 의존이 아니다 — 원장은 '매임'의 기록이다
        v = by_issue.get(s.issue_id)
        fresh.append({"asset": asset, "doc": n.doc, "doc_id": n.doc_id,
                      "node": n.node, "path": n.path,
                      "issue": i.question, "card": i.card,
                      "req": s.req_text[:120], "judgment": s.judgment,
                      "conclusion": v.conclusion if v else "판단보류",
                      "rid": state.rid, "at": _now()})
    rows = load()
    keys = {_key(b) for b in fresh}
    rows = [b for b in rows if _key(b) not in keys]      # 같은 자리는 갱신
    rows.extend(fresh)
    _save(rows)
    return len(fresh)


def impacted(doc: str, node: Optional[int] = None) -> list[dict]:
    """역인덱스 — 이 조문이 바뀌면 어느 자산이 영향받나 (트랙 A 의 입구).

    node 를 주면 그 마디에 매인 것만, 안 주면 그 문서 전체다. 개정 델타가
    조문 단위로 오므로 보통 node 까지 준다.
    """
    out = [b for b in load() if b.get("doc") == doc
           and (node is None or b.get("node") == node)]
    out.sort(key=lambda b: (b.get("asset", ""), b.get("path", "")))
    return out


def assets() -> list[dict]:
    """자산별 요약 — 무엇이 몇 개 조문에 매여 있고 미해결이 몇인가."""
    agg: dict[str, dict] = {}
    for b in load():
        a = agg.setdefault(b.get("asset", ""),
                           {"asset": b.get("asset", ""), "bindings": 0,
                            "docs": set(), "불명": 0, "불충족": 0, "last": ""})
        a["bindings"] += 1
        a["docs"].add(b.get("doc", ""))
        if b.get("judgment") in ("불명", "불충족"):
            a[b["judgment"]] += 1
        a["last"] = max(a["last"], b.get("at", ""))
    return [{**a, "docs": sorted(a["docs"])} for a in
            sorted(agg.values(), key=lambda x: -x["bindings"])]
