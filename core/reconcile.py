"""T10. 비교 엔진 — 정답 문서 기준 순회 (SPEC §4.1).

비교는 **"어떤 문서의 어떤 section 에 있는 어떤 용어" ↔ "다른 문서의 어떤 section 의 내용"**
을 잇는 매핑 규칙으로 정의된다. 규칙은 `tasks/reconcile_{pair}.yaml` 에 있고,
이 모듈은 그 규칙을 읽어 실행할 뿐 도메인을 모른다.

원칙(§4.1 말미)
    · source(정답)의 rule 은 **전부** 리포트에 한 행씩 나타난다 — 누락·미매핑도 행으로.
    · 판정은 코드 결정론. **LLM 은 판정에 개입하지 않는다.**
    · 행마다 양쪽 raw + source(page/bbox)를 실어 사람이 즉시 대조할 수 있게 한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from core.normalize import compare, to_jsonable
from core.structurize import Document, Fact

VERDICTS = ("MATCH", "VALUE_MISMATCH", "MISSING_IN_TARGET", "UNMAPPED", "NEEDS_REVIEW")


class Side(BaseModel):
    section: Optional[str] = None
    section_any_of: list[str] = Field(default_factory=list)
    term: str

    def sections(self) -> list[str]:
        return [self.section] if self.section else list(self.section_any_of)


class Rule(BaseModel):
    source: Side
    target: Side
    note: Optional[str] = None


class TaskSpec(BaseModel):
    source_of_truth: str
    target: str
    rules: list[Rule] = Field(default_factory=list)


@dataclass
class Row:
    term: str
    value_type: str
    source_section: Optional[str]
    source_value: Optional[str]
    source_raw: Optional[str]
    source_ref: Optional[dict]
    target_section: Optional[str]
    target_value: Optional[str]
    target_raw: Optional[str]
    target_ref: Optional[dict]
    verdict: str
    note: str = ""

    def dump(self) -> dict:
        return {
            "term": self.term, "value_type": self.value_type,
            "source": {"section_id": self.source_section, "value": self.source_value,
                       "raw": self.source_raw, "ref": self.source_ref},
            "target": {"section_id": self.target_section, "value": self.target_value,
                       "raw": self.target_raw, "ref": self.target_ref},
            "verdict": self.verdict, "note": self.note,
        }


@dataclass
class Report:
    source_file: str
    target_file: str
    source_of_truth: str
    target_doc_type: str
    generated_at: str
    rows: list[Row] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    gate: dict = field(default_factory=dict)

    def recount(self) -> "Report":
        counts = {v: 0 for v in VERDICTS}
        for r in self.rows:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
        self.stats = {"total": len(self.rows), **counts}
        return self

    def dump(self) -> dict:
        return {"source_file": self.source_file, "target_file": self.target_file,
                "source_of_truth": self.source_of_truth,
                "target_doc_type": self.target_doc_type,
                "generated_at": self.generated_at,
                "rows": [r.dump() for r in self.rows],
                "stats": self.stats, "gate": self.gate}


# ---------------------------------------------------------------------------

def load_task(path: str | Path) -> TaskSpec:
    return TaskSpec.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _section_matches(section_id: str, wanted: list[str]) -> bool:
    """section_id 의 경로 성분 중 하나라도 지정한 이름과 맞으면 참.

    "별지1/신탁계약 세부내역" 은 `section: "별지1/신탁계약 세부내역"`(완전 일치)로도,
    `section_any_of: ["신탁계약 세부내역"]`(성분 일치)으로도 지정할 수 있다.
    """
    if not wanted:
        return True
    parts = section_id.split("/")
    return any(w == section_id or w in parts for w in wanted)


def _find(doc: Document, side: Side) -> Optional[Fact]:
    wanted = side.sections()
    hits = [f for f in doc.facts
            if f.term == side.term and _section_matches(f.section_id, wanted)]
    if hits:
        # 값 정규화에 성공한 것을 먼저 — 같은 용어가 본문 문장에서도 잡힐 수 있다
        return next((f for f in hits if not f.needs_review), hits[0])
    # 섹션 지정이 안 맞았을 뿐 용어 자체는 있는가 — UNMAPPED 와 구분하기 위해 본다
    return next((f for f in doc.facts if f.term == side.term), None) if wanted else None


def _ref(fact: Optional[Fact], doc_label: str) -> Optional[dict]:
    if fact is None:
        return None
    return {"doc": doc_label, **fact.source}


def run(source_doc: Document, target_doc: Document, task: TaskSpec) -> Report:
    """정답 문서(source)의 rule 을 하나씩 돌며 대상 문서(target)를 검사한다."""
    rows: list[Row] = []

    for rule in task.rules:
        src = _find(source_doc, rule.source)
        tgt = _find(target_doc, rule.target)
        vt = (src.value_type if src else
              (tgt.value_type if tgt else "text"))

        # 1) 정답에 값이 없다 — 대조 기준 자체가 없으므로 보류
        if src is None or not src.raw:
            rows.append(Row(
                term=rule.source.term, value_type=vt,
                source_section=rule.source.section or (rule.source.section_any_of or [None])[0],
                source_value=None, source_raw=None, source_ref=_ref(src, "source"),
                target_section=tgt.section_id if tgt else None,
                target_value=to_jsonable(tgt.value) if tgt else None,
                target_raw=tgt.raw if tgt else None, target_ref=_ref(tgt, "target"),
                verdict="NEEDS_REVIEW",
                note="정답 문서에서 값을 찾지 못해 대조 기준이 없습니다"))
            continue

        # 2) 대상에서 못 찾았다 — 이름조차 없으면 UNMAPPED, 섹션만 안 맞으면 MISSING
        if tgt is None:
            has_term_anywhere = any(f.term == rule.target.term for f in target_doc.facts)
            verdict = "MISSING_IN_TARGET" if has_term_anywhere else "UNMAPPED"
            note = ("대상 문서의 지정 section 에 값이 없습니다" if has_term_anywhere else
                    "대상 문서에서 용어를 찾지 못했습니다 — 용어집 aliases 보강 필요")
            rows.append(Row(
                term=rule.source.term, value_type=vt,
                source_section=src.section_id, source_value=to_jsonable(src.value),
                source_raw=src.raw, source_ref=_ref(src, "source"),
                target_section=None, target_value=None, target_raw=None, target_ref=None,
                verdict=verdict, note=note))
            continue

        # 3) 값 대조 — value_type 비교기로, 결정론
        res = compare(vt, src.raw, tgt.raw)
        rows.append(Row(
            term=rule.source.term, value_type=vt,
            source_section=src.section_id, source_value=to_jsonable(src.value),
            source_raw=src.raw, source_ref=_ref(src, "source"),
            target_section=tgt.section_id, target_value=to_jsonable(tgt.value),
            target_raw=tgt.raw, target_ref=_ref(tgt, "target"),
            verdict=res.verdict, note=res.note))

    report = Report(
        source_file=source_doc.source_file, target_file=target_doc.source_file,
        source_of_truth=task.source_of_truth, target_doc_type=task.target,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        rows=rows,
        gate={"source": source_doc.fitness, "target": target_doc.fitness})
    return report.recount()


def write(report: Report, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report.dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


_SYMBOL = {"MATCH": "✓", "VALUE_MISMATCH": "✗", "MISSING_IN_TARGET": "−",
           "UNMAPPED": "?", "NEEDS_REVIEW": "△"}


def to_text(report: Report) -> str:
    """사람이 읽는 리포트 — 행마다 양쪽 출처를 보여 준다."""
    out = [f"정답    {report.source_file}  ({report.source_of_truth})",
           f"대상    {report.target_file}  ({report.target_doc_type})", ""]
    out.append(f"{'용어':<18} {'유형':<12} {'판정':<18} 정답 → 대상")
    out.append("-" * 104)
    for r in report.rows:
        sym = _SYMBOL.get(r.verdict, " ")
        src = (r.source_raw or "—")[:34]
        tgt = (r.target_raw or "—")[:34]
        out.append(f"{sym} {r.term:<17} {r.value_type:<12} {r.verdict:<18} {src} → {tgt}")
        if r.note:
            out.append(f"    {r.note}")
        if r.source_ref or r.target_ref:
            s = f"p.{r.source_ref.get('page')}" if r.source_ref else "-"
            t = f"p.{r.target_ref.get('page')}" if r.target_ref else "-"
            out.append(f"    출처  정답 {s} / 대상 {t}")
    s = report.stats
    out += ["", f"총 {s.get('total', 0)}  일치 {s.get('MATCH', 0)}  "
                f"불일치 {s.get('VALUE_MISMATCH', 0)}  누락 {s.get('MISSING_IN_TARGET', 0)}  "
                f"미매핑 {s.get('UNMAPPED', 0)}  보류 {s.get('NEEDS_REVIEW', 0)}"]
    for label, g in (("정답", report.gate.get("source")), ("대상", report.gate.get("target"))):
        if g:
            mark = "통과" if g.get("passed") else "격리"
            out.append(f"게이트  {label} {g.get('score')} ({mark})")
    return "\n".join(out)
