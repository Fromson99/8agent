"""T19. 변이 테스트 — 제약이 실제로 오류를 잡는지 증명한다 (SPEC §C12.4).

골든 요약서를 의도적으로 훼손하고, **정확히 그 필드가** 발화하는지 본다.
발화하지 않으면 그 제약은 죽어 있고, 엉뚱한 필드가 함께 터지면 노이즈다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from mutations import mutate   # noqa: E402   # 변이 정의는 테스트 자산 — src 에 두지 않는다
import ontology              # noqa: E402
import reconcile             # noqa: E402

PAIR = ROOT / "data" / "golden_pairs" / "acct_001"
FIRING = ("VALUE_MISMATCH", "MISSING_IN_SUMMARY")


@pytest.fixture(scope="module")
def onto():
    return ontology.load(ontology.default_path(ROOT))


@pytest.fixture(scope="module")
def baseline(onto):
    """훼손 전 기준선 — 여기서 이미 발화 중인 필드는 변이 판정에서 제외한다."""
    rep = reconcile.run(PAIR / "contract.chunks.json", PAIR / "summary.md", onto)
    return {r.field_name: r.verdict for r in rep.rows}


@pytest.mark.parametrize("m", mutate.MUTATIONS, ids=lambda m: m.id)
def test_mutation_is_caught(m, onto, baseline, tmp_path):
    bad = mutate.apply_to(PAIR / "summary.md", m, tmp_path)
    rep = reconcile.run(PAIR / "contract.chunks.json", bad, onto)
    got = {r.field_name: r.verdict for r in rep.rows}

    # (a) 겨냥한 제약이 발화하는가
    assert got.get(m.field) == m.expect, (
        f"[{m.id}] {m.describe} → {m.field} 가 {m.expect} 로 잡히지 않았습니다 "
        f"(실제 {got.get(m.field)})")

    # (b) 엉뚱한 필드가 함께 터지지 않는가 — 기준선 대비 새로 발화한 것만 본다
    spurious = [f for f, v in got.items()
                if f != m.field and v in FIRING and baseline.get(f) not in FIRING]
    assert not spurious, f"[{m.id}] 변이와 무관한 필드가 발화했습니다: {spurious}"


def test_every_mutation_targets_a_real_field(onto):
    """변이가 온톨로지에 없는 필드를 겨냥하면 테스트 자체가 무의미하다."""
    unknown = [m.id for m in mutate.MUTATIONS if m.field not in onto.fields]
    assert not unknown, f"온톨로지에 없는 필드를 겨냥한 변이: {unknown}"


def test_firing_counter_records_baseline(onto, baseline):
    """T20 — 리포트에 제약별 발화 통계가 실려야 한다 (§C12.4)."""
    rep = reconcile.run(PAIR / "contract.chunks.json", PAIR / "summary.md", onto)
    f = rep.firings
    assert f and "per_field" in f and "per_cq" in f
    assert set(f["per_cq"]) <= set(onto.competency_questions), "선언 밖 CQ 가 집계됐습니다"
    covered = {q for s in onto.fields.values() for q in s.cq}
    assert set(f["per_cq"]) == covered, "필드가 참조하는 CQ 가 통계에서 빠졌습니다"
