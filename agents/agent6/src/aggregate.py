"""T-A6.6 집계 — 판정을 리포트 행으로, 행을 하나의 상태로 (AGENT6 §5-6·§6).

여기서 지켜야 하는 불변량이 넷이다.

1. **행 수 = 체크리스트 항목 수.** 활성이든, 비활성이든, 스펙에서 꺼 둔 항목이든
   모든 항목이 정확히 한 행씩 나온다(§7). 행이 사라지면 "점검하지 않은 것"과
   "통과한 것"이 구별되지 않는다. `enabled: false` 항목이 리포트에서 통째로 빠지던
   구멍을 여기서 막는다 — 꺼 둔 것도 사실이고, 사실은 리포트에 남아야 한다.
2. **파생 항목은 계산한다.** F-29 는 LLM 을 부르지 않고 구성 항목의 판정으로 산출한다
   (§9-5). 그래서 파생은 반드시 다른 항목이 다 정해진 **뒤에** 계산된다.
3. **FAIL·UNCLEAR 에는 갈 곳이 있다.** 라우팅 없는 미비는 사라진 미비다. 라우팅은
   코드가 정하지 않고 항목 스펙의 `fail_route/unclear_route` 가 정한다(§4 말미).
4. **점검하지 못한 항목은 통과의 근거가 될 수 없다.** 근거 미해소로 활성이 차단된
   항목(basis_policy=block)은 NOT_APPLICABLE 로 적히지만 "해당 없음"이 아니라
   "못 봤음"이다. `unchecked()` 가 그 둘을 갈라 주고, report 가 그것을 종합 판정에
   반영한다. 이 구분이 없으면 근거를 못 붙인 항목이 많을수록 리포트가 깨끗해진다.

## confidence 감점이 여기 모이는 이유

감점 사유는 판정기 바깥에서 온다 — 메타 부족으로 보수 활성된 항목(when UNKNOWN),
화자·타임스탬프 없는 평문 전사, 낮은 STT 신뢰도(§11). 판정기가 이것들을 알 필요는
없고, 알면 판정이 입력 품질에 따라 흔들린다. 판정은 판정대로 내리고, 그 판정을
**얼마나 믿을 것인가**는 여기서 한 번에 깎는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from agents.agent6.src import schema
from agents.agent6.src.judge import (METHOD_BASIS_BLOCKED, METHOD_DERIVED,
                                     METHOD_DISABLED, METHOD_WHEN, Judgment)
from agents.agent6.src.preprocess import Prepared

# STT 신뢰도가 이 값 아래면 판정 confidence 를 한 단계 깎는다. 전사가 흔들리면
# 그 위에 세운 모든 판정이 흔들린다 — 판정기는 그 사실을 모르므로 여기서 반영한다.
STT_LOW_CONFIDENCE = 0.85

# "해당 없음"이 아니라 "점검하지 못했음"인 행의 method. 종합 판정이 이것을 본다(불변량 4).
UNCHECKED_METHODS = (METHOD_BASIS_BLOCKED, METHOD_DISABLED)


class AggregateError(ValueError):
    """집계 불변량이 깨졌다. 리포트를 만들지 않고 멈춘다."""


@dataclass
class Aggregated:
    rows: list[schema.ItemVerdict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def by_id(self, item_id: str) -> Optional[schema.ItemVerdict]:
        return next((r for r in self.rows if r.id == item_id), None)

    def verdicts(self) -> dict[str, str]:
        return {r.id: r.verdict for r in self.rows}


def unchecked(rows: Sequence[schema.ItemVerdict]) -> list[schema.ItemVerdict]:
    """점검하지 못한 행 — 근거 미해소 차단, 스펙에서 꺼 둔 항목.

    when 으로 비활성된 항목은 여기 들어오지 않는다. "이 통화에는 해당하지 않는다"는
    **점검한 결과**이지 못 본 것이 아니다(예: 고령투자자 항목 · 고객이 40세).
    """
    return [r for r in rows if r.method in UNCHECKED_METHODS]


def _global_penalty(prepared: Prepared) -> tuple[int, list[str]]:
    """전사 품질에서 오는 전역 감점. 사유를 함께 돌려준다(감점은 설명 없이 하지 않는다)."""
    steps, notes = 0, []
    stats = prepared.transcript.stats or {}
    if stats.get("mode") == "평문" or not stats.get("with_timestamp"):
        steps += 1
        notes.append("화자·타임스탬프 없는 전사 — 모든 항목의 confidence 를 한 단계 낮춥니다(§1)")
    stt = prepared.meta.stt_confidence
    if stt is not None and stt < STT_LOW_CONFIDENCE:
        steps += 1
        notes.append(f"STT 신뢰도 {stt:.2f} < {STT_LOW_CONFIDENCE} — "
                     f"모든 항목의 confidence 를 한 단계 낮춥니다(§11)")
    return steps, notes


def _when_notes(activation) -> list[str]:
    """리포트 행에 실을 비고 — when 사유 + 근거 미해소 사유.

    두 사유를 한 칸에 모으는 이유: 읽는 사람의 질문이 하나이기 때문이다.
    "이 항목은 왜 이렇게 판정됐는가(혹은 왜 판정되지 않았는가)".
    """
    notes = list(activation.reasons)
    reason = getattr(activation, "blocked_reason", None)
    if reason and reason not in notes:
        notes.append(reason)
    return notes


def _row_for_disabled(item: schema.ChecklistItem) -> schema.ItemVerdict:
    """스펙에서 꺼 둔 항목(§4: 파일을 지우지 않고 enabled: false 로 끈다).

    행을 남기는 이유: 30항목짜리 체크리스트가 28행으로 나오면 읽는 사람은 그것이
    "꺼 둔 2개"인지 "빠뜨린 2개"인지 알 수 없다. 상태를 적어 남긴다.
    """
    return schema.ItemVerdict(
        id=item.id, name=item.name, type=item.type, active=False,
        verdict="NOT_APPLICABLE", basis_refs=item.basis_refs(),
        inactive_reason="스펙에서 꺼 둔 항목입니다(enabled: false) — 이번 실행에서 점검하지 않았습니다",
        method=METHOD_DISABLED,
        when_notes=[item.note] if item.note else [])


def _basis_blocked(activation) -> bool:
    """이 비활성이 **근거 미해소 때문**인가.

    `blocked_reason` 만 보면 안 된다 — basis_policy=warn 에서는 근거가 미해소여도 활성이
    유지되므로, when 으로 꺼진 항목이 미해소 근거를 함께 달고 있는 경우가 흔하다(E-26 은
    고객이 적합해서 꺼진 것이지 근거가 없어서 꺼진 것이 아니다). 실제로 그 둘을 섞어
    "점검하지 못한 항목"으로 세는 실수를 했다.

    차단으로 꺼진 활성은 preprocess 가 **사유를 그 하나만** 달아 만든다. 그것이 두
    경우를 가르는 유일한 구조적 표식이다.
    """
    reason = getattr(activation, "blocked_reason", None)
    return bool(reason) and tuple(activation.reasons) == (reason,)


def _row_for_inactive(item: schema.ChecklistItem, activation) -> schema.ItemVerdict:
    # 근거 미해소로 활성이 차단된 것은 "해당 없음"이 아니라 "점검하지 못함"이다.
    blocked = _basis_blocked(activation)
    return schema.ItemVerdict(
        id=item.id, name=item.name, type=item.type, active=False,
        verdict="NOT_APPLICABLE", basis_refs=item.basis_refs(),
        inactive_reason=activation.text,
        method=METHOD_BASIS_BLOCKED if blocked else METHOD_WHEN,
        when_notes=_when_notes(activation))


def _row_for_judgment(item: schema.ChecklistItem, judgment: Judgment,
                      activation, penalty: int) -> schema.ItemVerdict:
    confidence = schema.downgrade(judgment.confidence,
                                  penalty + activation.confidence_penalty)
    reason = judgment.reason
    if judgment.notes:
        reason = (reason + " / " if reason else "") + " / ".join(judgment.notes)
    return schema.ItemVerdict(
        id=item.id, name=item.name, type=item.type, active=True,
        verdict=judgment.verdict, route=item.route_for(judgment.verdict),
        evidence=judgment.evidence or None,
        llm_reason=reason or None, basis_refs=item.basis_refs(),
        confidence=confidence, method=judgment.method,
        when_notes=_when_notes(activation))


def _row_for_derived(item: schema.ChecklistItem, verdicts: dict[str, str],
                     rows: dict[str, schema.ItemVerdict], activation,
                     penalty: int) -> schema.ItemVerdict:
    """파생 항목 — **LLM 을 부르지 않는다**(§9-5). 구성 항목의 판정만으로 만든다."""
    assert item.derived is not None
    verdict = item.derived.evaluate(verdicts)
    sources = item.derived.sources()

    # confidence 는 구성 항목 중 가장 낮은 것을 따른다. 파생이 근거보다 확신할 수는 없다.
    live = [rows[s] for s in sources if s in rows and rows[s].verdict != "NOT_APPLICABLE"]
    if live:
        confidence = max((r.confidence for r in live),
                         key=lambda c: schema.CONFIDENCE_ORDER.index(c))
    else:
        confidence = "low"

    # 사유에는 계산식과 **끌어내린 구성 항목**만 적는다. 규칙의 근거(derived.note)는
    # 스펙 파일에 있고, 리포트에 통째로 옮기면 정작 무엇이 문제인지가 묻힌다.
    driving = [f"{s}={verdicts.get(s)}" for s in sources]
    reason = f"파생 계산({', '.join(driving)}) — 독립 LLM 판정 없음"
    problems = [s for s in sources if verdicts.get(s) in ("FAIL", "UNCLEAR")]
    if problems:
        reason += f". 끌어내린 구성 항목: {', '.join(problems)}"

    if verdict == "NOT_APPLICABLE":
        # 구성 항목이 전부 비활성이면 파생도 판정할 것이 없다.
        return schema.ItemVerdict(
            id=item.id, name=item.name, type=item.type, active=False,
            verdict="NOT_APPLICABLE", basis_refs=item.basis_refs(),
            inactive_reason=f"구성 항목이 모두 비활성입니다({', '.join(sources)})",
            method=METHOD_DERIVED, when_notes=_when_notes(activation))

    return schema.ItemVerdict(
        id=item.id, name=item.name, type=item.type, active=True,
        verdict=verdict, route=item.route_for(verdict),
        evidence=None, llm_reason=reason,
        basis_refs=item.basis_refs(),
        confidence=schema.downgrade(confidence, penalty + activation.confidence_penalty),
        method=METHOD_DERIVED, when_notes=_when_notes(activation))


def run(prepared: Prepared, judgments: dict[str, Judgment]) -> Aggregated:
    """항목 → 리포트 행. 파생은 마지막에 계산한다(불변량 2)."""
    penalty, notes = _global_penalty(prepared)
    rows: dict[str, schema.ItemVerdict] = {}

    # 1차 — 파생이 아닌 항목
    for item in prepared.items:
        if not item.enabled:
            rows[item.id] = _row_for_disabled(item)
            continue
        activation = prepared.activations[item.id]
        if not activation.active:
            rows[item.id] = _row_for_inactive(item, activation)
            continue
        if item.derived is not None:
            continue
        j = judgments.get(item.id)
        if j is None:
            raise AggregateError(
                f"{item.id}: 활성 항목인데 판정이 없습니다 — 판정 국면이 항목을 빠뜨렸습니다. "
                f"빠진 판정을 통과로 세지 않습니다(§0 조용한 실패 금지)")
        rows[item.id] = _row_for_judgment(item, j, activation, penalty)

    # 2차 — 파생
    verdicts = {i: r.verdict for i, r in rows.items()}
    for item in prepared.items:
        if not item.enabled or item.derived is None or item.id in rows:
            continue
        rows[item.id] = _row_for_derived(item, verdicts, rows,
                                         prepared.activations[item.id], penalty)

    ordered = [rows[i.id] for i in prepared.items if i.id in rows]
    if len(ordered) != len(prepared.items):
        missing = sorted({i.id for i in prepared.items} - set(rows))
        raise AggregateError(
            f"리포트 행 수가 체크리스트 항목 수와 다릅니다 — 항목이 조용히 빠졌습니다: "
            f"{', '.join(missing)}")

    blocked = unchecked(ordered)
    if blocked:
        notes.append(
            f"점검하지 못한 항목 {len(blocked)}개({', '.join(r.id for r in blocked)}) — "
            f"이 항목들은 통과의 근거가 될 수 없습니다")
    return Aggregated(rows=ordered, notes=notes)


def assert_complete(rows: Sequence[schema.ItemVerdict],
                    items: Sequence[schema.ChecklistItem]) -> None:
    """체크리스트의 모든 항목이 한 행씩 있는가 — 조용한 스킵 검출(§9-3).

    `schema.Report.assert_complete` 는 `enabled` 인 항목만 기대한다. 여기서는 꺼 둔
    항목까지 한 행씩 나오는지를 본다(불변량 1). 둘은 같은 것을 다른 범위로 검사한다.
    """
    expected = {i.id for i in items}
    got = [r.id for r in rows]
    dupes = sorted({i for i in got if got.count(i) > 1})
    missing, extra = sorted(expected - set(got)), sorted(set(got) - expected)
    if missing or extra or dupes:
        raise AggregateError(
            "리포트 행이 체크리스트와 맞지 않습니다"
            + (f" — 빠짐: {', '.join(missing)}" if missing else "")
            + (f" — 없는 항목: {', '.join(extra)}" if extra else "")
            + (f" — 중복: {', '.join(dupes)}" if dupes else ""))


def route_counts(rows: Sequence[schema.ItemVerdict]) -> dict[str, int]:
    """라우팅별 건수 — CLI 요약과 리포트 통계가 함께 쓴다."""
    out: dict[str, int] = {}
    for r in rows:
        if r.route:
            out[r.route] = out.get(r.route, 0) + 1
    return out
