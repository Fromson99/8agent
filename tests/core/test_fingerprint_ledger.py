"""fingerprint 원장 — 관측이 프로세스를 넘어 쌓이고 frame 이 동결되는 계약.

원장이 없으면 관측이 늘 1회라 tier 가 warm 에 고정된다 — 재현빈도 기반
frame 동결(§7)은 영속화가 전제다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.structure import fingerprint as fp_mod            # noqa: E402
from core.structure.model import Fingerprint                # noqa: E402

FP = Fingerprint(families=["kr_장", "kr_article"],
                 order=[["kr_장"], ["kr_article"]])


def test_원장은_저장을_넘어_관측을_쌓는다(tmp_path):
    p = tmp_path / "ledger.json"
    led = fp_mod.Ledger.load(p)
    assert led.observe(FP, "doc-a") == 1
    led.save()

    led2 = fp_mod.Ledger.load(p)                 # 새 프로세스를 흉내낸다
    assert led2.observe(FP, "doc-b") == 2        # 관측이 이어진다
    assert led2.observe(FP, "doc-b") == 2        # 같은 문서는 다시 세지 않는다
    assert fp_mod.tier(2, True) == fp_mod.HOT


def test_frame_동결은_한_번만(tmp_path):
    p = tmp_path / "ledger.json"
    led = fp_mod.Ledger.load(p)
    led.observe(FP, "doc-a")
    led.observe(FP, "doc-b")
    assert fp_mod.may_freeze(2, fitness_passed=True)
    assert led.freeze(FP, "doc-b") is True
    assert led.freeze(FP, "doc-b") is False      # 첫 동결이 정본이다
    led.save()

    led2 = fp_mod.Ledger.load(p)
    frame = led2.frames[FP.key()]
    assert frame["order"] == FP.order
    assert frame["first_doc"] == "doc-b"
