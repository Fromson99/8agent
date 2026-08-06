"""T6. 홀드아웃 검증기 — 형식 오추출 방어 1 (SPEC §2.5).

형식 유도에 **쓰지 않은** 샘플에 형식을 적용해 검증한다(샘플 5개면 3개로 유도, 2개로 검증).
실패하면 형식을 확정하지 않고 불일치 지점을 사용자에게 보고한다.

유도에 쓴 샘플에서 잘 도는 것은 당연하다 — 그 샘플로 만든 형식이기 때문이다.
견고성은 **보지 않은 문서**에서만 드러난다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core import fitness_gate, parse_adapter, structurize
from core.format_model import Format
from core.glossary import Glossary


@dataclass
class SampleResult:
    path: str
    score: float
    passed: bool
    sections: int
    facts: int
    residual: int
    warnings: list[str] = field(default_factory=list)

    def dump(self) -> dict:
        return {"path": self.path, "score": round(self.score, 3), "passed": self.passed,
                "sections": self.sections, "facts": self.facts,
                "residual": self.residual, "warnings": self.warnings}


@dataclass
class HoldoutReport:
    results: list[SampleResult] = field(default_factory=list)
    passed: bool = False
    problems: list[str] = field(default_factory=list)

    def dump(self) -> dict:
        return {"passed": self.passed, "problems": self.problems,
                "results": [r.dump() for r in self.results]}


def check(paths: list[str | Path], fmt: Format, glossary: Glossary,
          threshold: float = fitness_gate.DEFAULT_THRESHOLD,
          consistency_tolerance: float = 0.25) -> HoldoutReport:
    """홀드아웃 샘플 각각에 형식을 적용해 채점한다.

    consistency_tolerance — 샘플 간 section 수가 이만큼 넘게 벌어지면 형식이
    문서마다 다르게 잘린다는 뜻이므로 경고한다(§2.5 "section 경계 수").
    """
    report = HoldoutReport()
    if not paths:
        report.problems.append("홀드아웃 샘플이 없습니다 — 형식 신뢰도를 낮음으로 표기하세요 (§2.1)")
        return report

    for p in paths:
        parsed = parse_adapter.parse(p)
        doc = structurize.run(parsed, fmt, glossary)
        fit = fitness_gate.apply(doc, fmt, glossary, len(parsed.elements), threshold)
        report.results.append(SampleResult(
            path=str(p), score=fit.score, passed=fit.passed,
            sections=len(doc.sections), facts=len([f for f in doc.facts if not f.needs_review]),
            residual=len(doc.residual), warnings=fit.warnings))

    failed = [r for r in report.results if not r.passed]
    for r in failed:
        report.problems.append(f"{Path(r.path).name}: 부합률 {r.score:.0%} — {'; '.join(r.warnings[:2])}")

    # 샘플 간 일관성 — 한 문서에서만 잘 도는 형식은 우연일 수 있다
    counts = [r.sections for r in report.results]
    if len(counts) >= 2 and max(counts) > 0:
        spread = (max(counts) - min(counts)) / max(counts)
        if spread > consistency_tolerance:
            report.problems.append(
                f"샘플 간 section 수가 크게 다릅니다 ({min(counts)}~{max(counts)}) — "
                "형식이 문서마다 다르게 자르고 있습니다")

    report.passed = not report.problems
    return report


def to_text(report: HoldoutReport) -> str:
    out = ["홀드아웃 검증 (§2.5)"]
    for r in report.results:
        mark = "통과" if r.passed else "실패"
        out.append(f"  [{mark}] {Path(r.path).name:<34} 부합 {r.score:.0%}  "
                   f"section {r.sections}  fact {r.facts}  잔여 {r.residual}")
        for w in r.warnings[:3]:
            out.append(f"          · {w}")
    if report.problems:
        out.append("")
        out.append("형식을 확정할 수 없습니다:")
        out += [f"  - {p}" for p in report.problems]
    else:
        out.append("")
        out.append("모든 홀드아웃 샘플이 통과했습니다 — 형식을 확정할 수 있습니다.")
    return "\n".join(out)
