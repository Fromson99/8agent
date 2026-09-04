"""Confusion-matrix metrics for final-answer legal evidence sets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Hashable, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class EvidenceConfusion:
    """Article-root confusion matrix for one question.

    True negatives are retained for audit only.  They must not be used in the
    legal evidence score because the corpus-sized negative universe would make
    almost every sparse answer appear nearly perfect.
    """

    tp: int
    fp: int
    fn: int
    tn: int

    @classmethod
    def from_sets(
        cls,
        required: Iterable[Hashable],
        selected: Iterable[Hashable],
        *,
        universe_size: int,
    ) -> "EvidenceConfusion":
        gold = set(required)
        answer = set(selected)
        union_size = len(gold | answer)
        if universe_size < union_size:
            raise ValueError("universe_size is smaller than required/selected union")
        return cls(
            tp=len(gold & answer),
            fp=len(answer - gold),
            fn=len(gold - answer),
            tn=universe_size - union_size,
        )

    @property
    def selected(self) -> int:
        return self.tp + self.fp

    @property
    def required(self) -> int:
        return self.tp + self.fn

    @property
    def precision(self) -> float:
        return self.tp / self.selected if self.selected else 0.0

    @property
    def recall(self) -> float:
        return self.tp / self.required if self.required else 0.0

    @property
    def f1(self) -> float:
        denominator = 2 * self.tp + self.fp + self.fn
        return 2 * self.tp / denominator if denominator else 0.0

    @property
    def jaccard(self) -> float:
        denominator = self.tp + self.fp + self.fn
        return self.tp / denominator if denominator else 0.0

    @property
    def complete(self) -> bool:
        return self.fn == 0

    @property
    def exact(self) -> bool:
        return self.fn == 0 and self.fp == 0

    def tversky(self, *, fp_weight: float = 0.25, fn_weight: float = 1.0) -> float:
        if fp_weight < 0 or fn_weight < 0:
            raise ValueError("weights must be non-negative")
        denominator = self.tp + fp_weight * self.fp + fn_weight * self.fn
        return self.tp / denominator if denominator else 0.0

    def to_dict(self) -> dict[str, int | float | bool]:
        return {
            **asdict(self),
            "selected": self.selected,
            "required": self.required,
            "precision": round(self.precision, 8),
            "recall": round(self.recall, 8),
            "f1": round(self.f1, 8),
            "jaccard": round(self.jaccard, 8),
            "legal_tversky": round(self.tversky(), 8),
            "complete": self.complete,
            "exact": self.exact,
        }


def aggregate_evidence_confusions(
    rows: Sequence[EvidenceConfusion],
    *,
    micro_weight: float = 0.45,
    macro_weight: float = 0.35,
    complete_weight: float = 0.20,
    fp_weight: float = 0.25,
    fn_weight: float = 1.0,
) -> dict[str, int | float]:
    if not rows:
        raise ValueError("at least one confusion row is required")
    weights_total = micro_weight + macro_weight + complete_weight
    if abs(weights_total - 1.0) > 1e-9:
        raise ValueError("group score component weights must sum to 1")
    total = EvidenceConfusion(
        tp=sum(row.tp for row in rows),
        fp=sum(row.fp for row in rows),
        fn=sum(row.fn for row in rows),
        tn=sum(row.tn for row in rows),
    )
    macro_tversky = mean(row.tversky(fp_weight=fp_weight, fn_weight=fn_weight) for row in rows)
    complete_rate = mean(float(row.complete) for row in rows)
    micro_tversky = total.tversky(fp_weight=fp_weight, fn_weight=fn_weight)
    group_score = 100 * (
        micro_weight * micro_tversky
        + macro_weight * macro_tversky
        + complete_weight * complete_rate
    )
    result: dict[str, int | float] = {
        "cases": len(rows),
        **total.to_dict(),
        "macro_tversky": round(macro_tversky, 8),
        "complete_cases": sum(row.complete for row in rows),
        "complete_rate": round(complete_rate, 8),
        "exact_cases": sum(row.exact for row in rows),
        "group_score": round(group_score, 6),
    }
    return result


def difficulty_balanced_score(groups: Mapping[str, Mapping[str, int | float]]) -> float:
    """Equal-weight CORE and HARD groups, independent of their case counts."""
    expected = {"core", "hard"}
    if set(groups) != expected:
        raise ValueError(f"difficulty groups must be exactly {sorted(expected)}")
    return round((float(groups["core"]["group_score"]) + float(groups["hard"]["group_score"])) / 2, 6)
