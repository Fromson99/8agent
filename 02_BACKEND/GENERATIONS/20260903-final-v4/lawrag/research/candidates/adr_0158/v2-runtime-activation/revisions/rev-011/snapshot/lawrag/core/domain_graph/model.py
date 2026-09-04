"""Graph DB로 그대로 옮길 수 있는 최소 property-graph 계약."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any


def normalize_surface(value: str) -> str:
    """표기형 묶음 키. 의미를 바꾸는 문장부호는 보존한다."""
    return re.sub(r"\s+", "", value or "").casefold()


def stable_id(prefix: str, *parts: object) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def lexeme_id(surface: str) -> str:
    return stable_id("lexeme", normalize_surface(surface))


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    label: str = ""
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    id: str
    kind: str
    src: str
    dst: str
    props: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(cls, kind: str, src: str, dst: str, *, key: object = "",
             props: dict[str, Any] | None = None) -> "Edge":
        return cls(stable_id("edge", kind, src, dst, key), kind, src, dst, props or {})
