"""소스 어댑터 레지스트리."""
from __future__ import annotations

from typing import Callable

from . import kofia, krx, lawgo

ADAPTERS: dict[str, Callable] = {
    "kofia": kofia.build,
    "krx": krx.build,
    "law": lawgo.build,
}
