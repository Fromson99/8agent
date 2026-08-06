"""T13. 리포트 출력 — §B9 스키마로 직렬화 + 사람용 요약."""
from __future__ import annotations

import json
from pathlib import Path

from schema import ReconcileReport

MARK = {"MATCH": "✓", "VALUE_MISMATCH": "✗", "MISSING_IN_SUMMARY": "−",
        "UNMAPPED": "?", "NEEDS_REVIEW": "△"}


def write(report: ReconcileReport, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report.model_dump(exclude_none=True), ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def to_text(report: ReconcileReport) -> str:
    s = report.stats
    lines = [
        f"계약서   {report.contract}",
        f"요약서   {report.summary}",
        "",
        f"{'필드':22s} {'유형':12s} {'판정':20s} 계약서 → 요약서",
        "-" * 104,
    ]
    for r in report.rows:
        lines.append(
            f"{MARK.get(r.verdict,' ')} {r.field_name:20s} {r.value_type:12s} "
            f"{r.verdict:20s} {_cut(r.contract_value)} → {_cut(r.summary_value)}")
        if r.note:
            lines.append(f"    {r.note}")
    lines += [
        "",
        f"총 {s.get('total',0)}  일치 {s.get('match',0)}  불일치 {s.get('value_mismatch',0)}  "
        f"누락 {s.get('missing',0)}  미매핑 {s.get('unmapped',0)}  보류 {s.get('needs_review',0)}",
    ]
    f = report.firings or {}
    if f:
        cq = f.get("per_cq", {})
        if cq:
            lines.append("")
            lines.append("제약 발화 (§C12.4) — CQ 별")
            for q, v in sorted(cq.items()):
                lines.append(f"  {q}  검사 {v['checked']}  발화 {v['fired']}")
        never = f.get("never_fired") or []
        if never:
            lines.append(f"  미발화 필드 {len(never)}개: {', '.join(never[:8])}"
                         + (" …" if len(never) > 8 else ""))
    return "\n".join(lines)


def _cut(v, n: int = 26) -> str:
    t = (v or "—").replace("\n", " ")
    return t if len(t) <= n else t[:n] + "…"
