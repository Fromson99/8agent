"""소스 어댑터 레지스트리."""
from __future__ import annotations

from typing import Callable

from . import kofia

ADAPTERS: dict[str, Callable] = {
    "kofia": kofia.build,
}
