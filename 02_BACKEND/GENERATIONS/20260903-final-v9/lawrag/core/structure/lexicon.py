"""언어 자원 적재 — 조사·서수를 **용어처럼** 따로 관리한다.

게이트가 쓰는 지식은 코드에 박지 않고 `lexicon/` 아래 파일로 둔다. 조사 하나를 더하는 일이
파이썬을 고치는 일이 되면 어휘가 자라지 않는다. 나중에 관리소가 붙을 때 구분자 라이브러리와
같은 자리에서 다뤄질 것들이다.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

LEXICON_DIR = Path(__file__).resolve().parent / "lexicon"


class Josa:
    """조사 어휘 — 매치 바로 뒤에 붙은 형태가 조사인지 판정한다."""

    def __init__(self, forms: list[str], chained: list[str]) -> None:
        # 긴 것부터 봐야 '에서' 가 '에' 에 먹히지 않는다.
        self.forms = sorted({f for f in forms if f}, key=len, reverse=True)
        self.chained = [re.compile(p) for p in chained]
        self._raw_chained = list(chained)

    def attached(self, tail: str) -> Optional[str]:
        """꼬리에 **공백 없이** 붙은 조사. 없으면 None.

        공백을 요구하지 않는 것이 핵심이다 — `제3장 총칙` 의 '총칙' 은 제목이고
        `제3장의 규정` 의 '의' 는 조사다. 둘을 가르는 것은 공백의 유무다.
        """
        if not tail or tail[0].isspace():
            return None
        for f in self.forms:
            if tail.startswith(f):
                return f
        return None

    def chained_reference(self, tail: str) -> Optional[str]:
        """`제19조제3항` 처럼 구분자 뒤에 또 구분자가 붙은 인용."""
        if not tail or tail[0].isspace():
            return None
        for i, rx in enumerate(self.chained):
            m = rx.match(tail)
            if m:
                return m.group(0) if m.group(0) else self._raw_chained[i]
        return None


class Numerals:
    """서수 어휘 — 번호 글자를 정수로 읽는다."""

    def __init__(self, scales: dict[str, dict[str, int]]) -> None:
        self.scales = scales
        flat: dict[str, int] = {}
        for name, table in sorted(scales.items()):
            for glyph, value in table.items():
                key = str(glyph)
                if key in flat:
                    # 조용히 잘못 읽는 것보다 적재에서 터지는 편이 낫다.
                    raise ValueError(
                        f"서수 글자 '{key}' 가 두 체계에 걸립니다 — 자동 판별이 성립하지 않습니다")
                flat[key] = int(value)
        self.flat = flat

    def read(self, token: str) -> Optional[int]:
        """글자 하나(또는 로마 표기 하나)를 정수로. 못 읽으면 None."""
        t = (token or "").strip()
        if not t:
            return None
        if t.isascii() and t.isdigit():
            return int(t)
        return self.flat.get(t)

    def ordinal(self, values: list[str]) -> Optional[tuple[int, ...]]:
        """여러 그룹을 사전식 서수로. 하나라도 못 읽으면 None(게이트가 건너뛴다)."""
        out: list[int] = []
        for v in values:
            n = self.read(v)
            if n is None:
                return None
            out.append(n)
        return tuple(out) if out else None


class Predicates:
    """참조 서술어 — 마커를 인용으로 만드는 술어. 조사 가드가 함께 쓴다."""

    def __init__(self, words: list[str]) -> None:
        self.words = sorted({w for w in words if w}, key=len, reverse=True)

    def first_in(self, text: str) -> Optional[str]:
        return next((w for w in self.words if w in text), None)


class Lexicon:
    def __init__(self, josa: Josa, numerals: Numerals, predicates: Predicates) -> None:
        self.josa = josa
        self.numerals = numerals
        self.predicates = predicates


def load(directory: str | Path = LEXICON_DIR) -> Lexicon:
    d = Path(directory)
    jp, np_, pp = d / "josa.yaml", d / "numerals.yaml", d / "reference_predicates.yaml"
    for p in (jp, np_, pp):
        if not p.exists():
            raise FileNotFoundError(f"언어 자원 파일이 없습니다: {p}")
    jdata = yaml.safe_load(jp.read_text(encoding="utf-8")) or {}
    ndata = yaml.safe_load(np_.read_text(encoding="utf-8")) or {}
    pdata = yaml.safe_load(pp.read_text(encoding="utf-8")) or {}
    return Lexicon(
        josa=Josa(jdata.get("josa") or [], jdata.get("chained_reference") or []),
        numerals=Numerals(ndata.get("scales") or {}),
        predicates=Predicates(pdata.get("predicates") or []))


@lru_cache(maxsize=4)
def default() -> Lexicon:
    return load()
