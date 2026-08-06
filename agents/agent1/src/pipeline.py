"""agent1 파이프라인 — **파일 두 개를 받아 대사한다.**

    run(계약서.pdf, 투자설명서.pdf) → 리포트

앞단(용어 등록 · 형식 만들기)은 문서 종류당 한 번이고 이미 자산으로 있다.
런타임은 이 함수 하나다.

    1. 파싱·구조화   (결정론)  두 문서를 section 트리 + fact 로
    2. 범위 좁히기   (결정론)  rule 이 지정한 section 만 꺼내 증거 표로
    3. 판정         (LLM)     증거 표를 보고 값 대조
    4. 출처 되돌리기 (결정론)  증거 ID → page/bbox/cell
    5. 집계·리포트
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AGENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_ROOT.parent.parent
for p in (str(REPO_ROOT), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import yaml                                             # noqa: E402
import judge as judge_mod                               # noqa: E402
import scope as scope_mod                               # noqa: E402
import service                                          # noqa: E402

# 형식·용어집 경로는 더 이상 여기에 없다. 구조화는 service 가 등록부에 맡기고,
# 이 파일은 그 결과를 좁히고(scope) 판정하는(judge) 일만 한다.
RULES = AGENT_ROOT / "tasks" / "agent1_trust_vs_prospectus.yaml"
OUTPUT = AGENT_ROOT / "output"

Structured = service.Structured        # 이관 전 이름 유지 (pipeline.Structured 호출자용)


@dataclass
class Report:
    contract_file: str
    prospectus_file: str
    generated_at: str
    model: str = ""
    rows: list[judge_mod.Judgement] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    gate: dict = field(default_factory=dict)
    scopes: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)

    def recount(self) -> "Report":
        counts = {v: 0 for v in judge_mod.VERDICTS}
        for r in self.rows:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
        checked = counts["MATCH"] + counts["VALUE_MISMATCH"]
        self.stats = {
            "total": len(self.rows), **counts,
            "대조한 항목": checked,
            "맞음": counts["MATCH"], "틀림": counts["VALUE_MISMATCH"],
            "정확도": round(counts["MATCH"] / checked, 3) if checked else None,
        }
        return self

    def dump(self) -> dict:
        return {"contract_file": self.contract_file,
                "prospectus_file": self.prospectus_file,
                "generated_at": self.generated_at, "model": self.model,
                "stats": self.stats, "gate": self.gate, "usage": self.usage,
                "rows": [r.dump() for r in self.rows],
                "scopes": self.scopes}


# ---------------------------------------------------------------------------

def load_rules(path=None) -> dict:
    return yaml.safe_load(Path(path or RULES).read_text(encoding="utf-8"))


def run(contract: str | Path, prospectus: str | Path,
        rules_path: Optional[str | Path] = None, llm=None,
        save_docs: bool = False, keep_scopes: bool = True) -> Report:
    """파일 두 개를 받아 대사한다 — 이 에이전트의 런타임 전부."""
    rules = load_rules(rules_path)

    src = service.structurize_contract(contract)
    tgt = service.structurize_prospectus(prospectus)

    if llm is None:
        from core.llm import LLM
        llm = LLM()

    report = Report(
        contract_file=Path(contract).name, prospectus_file=Path(prospectus).name,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=getattr(llm, "model", ""),
        gate={"contract": src.doc.fitness, "prospectus": tgt.doc.fitness})

    for rule in rules.get("rules", []):
        s_side, t_side = rule.get("source", {}), rule.get("target")
        term = s_side.get("term")

        # 대상 문서에 개념 자체가 없는 필드 — 조용히 빼지 않고 한 행으로 남긴다
        if t_side is None:
            report.rows.append(judge_mod.Judgement(
                term=term, verdict="NOT_APPLICABLE",
                reason=rule.get("note") or "대상 문서에 대응 개념이 없다고 규칙에 선언됨",
                method="rule"))
            continue

        s_scope = scope_mod.build(
            src.doc, "계약서", _paths(s_side), terms=[term], glossary=src.glossary)
        t_scope = scope_mod.build(
            tgt.doc, "투자설명서", _paths(t_side), terms=[t_side.get("term")],
            glossary=tgt.glossary)

        j = judge_mod.judge(term, s_scope, t_scope, llm, note=rule.get("note", ""),
                            row_anchor=t_side.get("row_anchor"))
        j.term = term
        report.rows.append(j)

        if keep_scopes:
            report.scopes[term] = {"contract": s_scope.dump(),
                                   "prospectus": t_scope.dump()}

    report.usage = llm.totals() if hasattr(llm, "totals") else {}
    if save_docs:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for label, s in (("contract", src), ("prospectus", tgt)):
            p = OUTPUT / f"{Path(s.parsed.path).stem}.doc.json"
            p.write_text(json.dumps(s.doc.dump(), ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return report.recount()


def _paths(side: dict) -> list[str]:
    if side.get("section"):
        return [side["section"]]
    return list(side.get("section_any_of") or [])


def write(report: Report, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report.dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


_SYM = {"MATCH": "✓", "VALUE_MISMATCH": "✗", "MISSING_IN_TARGET": "−",
        "SOURCE_EXTRACTION_FAILED": "!", "NOT_APPLICABLE": "·", "NEEDS_REVIEW": "△"}


def to_text(report: Report) -> str:
    out = [f"계약서    {report.contract_file}",
           f"투자설명서 {report.prospectus_file}",
           f"판정      {report.model}", ""]
    for r in report.rows:
        out.append(f"{_SYM.get(r.verdict, ' ')} {r.term:<16} {r.verdict}")
        out.append(f"    계약서   {r.source_value or '—'}")
        for ref in r.source_refs:
            out.append(f"             ↳ {ref['section_id']} p{ref['page']} "
                       f"({ref['ev_id']}) {ref['text'][:60]}")
        out.append(f"    설명서   {r.target_value or '—'}")
        for ref in r.target_refs:
            out.append(f"             ↳ {ref['section_id']} p{ref['page']} "
                       f"({ref['ev_id']}) {ref['text'][:60]}")
        if r.reason:
            out.append(f"    근거     {r.reason}")
        for w in r.warnings:
            out.append(f"    !        {w}")
        out.append("")
    s = report.stats
    out.append(f"총 {s.get('total', 0)}건 — 대조 {s.get('대조한 항목', 0)} "
               f"(맞음 {s.get('맞음', 0)} / 틀림 {s.get('틀림', 0)})"
               + (f", 정확도 {s['정확도']:.0%}" if s.get("정확도") is not None else ""))
    out.append(f"  보류 {s.get('NEEDS_REVIEW', 0)}  누락 {s.get('MISSING_IN_TARGET', 0)}  "
               f"정답추출실패 {s.get('SOURCE_EXTRACTION_FAILED', 0)}  "
               f"해당없음 {s.get('NOT_APPLICABLE', 0)}")
    for label, g in (("계약서", report.gate.get("contract")),
                     ("설명서", report.gate.get("prospectus"))):
        if g:
            out.append(f"게이트 {label} {g.get('score')} "
                       f"({'통과' if g.get('passed') else '격리'})")
    u = report.usage
    if u:
        out.append(f"LLM 호출 {u.get('calls')}  입력 {u.get('input_tokens'):,} "
                   f"출력 {u.get('output_tokens'):,}  오류 {u.get('errors')}")
    return "\n".join(out)
