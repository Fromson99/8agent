"""행 기준(row_anchor) 검증기 — 결정론, LLM 없이 돈다.

앵커는 값을 **뽑지 않는다.** 판단자가 고른 행이 규칙이 못박은 행인지 대조만 한다.
앵커로 셀을 직접 찍으면 조용히 틀릴 수 있기 때문이다(부분일치 충돌·병합 헤더 오프셋).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agents" / "agent1" / "src"))

from judge import verify_row_anchor          # noqa: E402

A = {"kind": "table_row", "text": "수수료선취-오프라인(A) | 0.30 | 0.30 | 0.02 | 0.62"}
C = {"kind": "table_row", "text": "수수료미징구-오프라인(C) | 0.30 | 1.00 | 0.02 | 1.32"}
TXT = {"kind": "text", "text": "이 투자신탁은 운용 및 판매 등의 대가로 …"}


def test_no_anchor_means_no_opinion():
    """앵커가 없으면 검증하지 않는다 — 통과도 실패도 아니다."""
    assert verify_row_anchor([A], None) == (None, "")


def test_matching_row_verifies():
    ok, detail = verify_row_anchor([A], "수수료선취-오프라인(A)")
    assert ok is True and "확인됨" in detail


def test_wrong_row_fails_loudly():
    """다른 행을 골랐으면 조용히 넘어가지 않는다."""
    ok, detail = verify_row_anchor([C], "수수료선취-오프라인(A)")
    assert ok is False
    assert "다른 행" in detail and "수수료미징구-오프라인(C)" in detail


def test_partial_surface_still_matches():
    """정규화 후 포함 관계면 인정 — 공백·괄호 차이를 흡수한다."""
    ok, _ = verify_row_anchor([A], "수수료선취 - 오프라인 (A)")
    assert ok is True


def test_text_only_evidence_cannot_be_verified():
    """근거가 표 행이 아니면 앵커를 확인할 수 없다 — 모른다고 한다."""
    ok, detail = verify_row_anchor([TXT], "수수료선취-오프라인(A)")
    assert ok is False and "확인할 수 없습니다" in detail


def test_any_matching_row_among_several_verifies():
    ok, _ = verify_row_anchor([C, A], "수수료선취-오프라인(A)")
    assert ok is True
