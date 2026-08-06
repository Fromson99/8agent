"""제안자 — **사람이 등록한 표면 패턴** (SPEC §6 "진짜 어휘 추가가 필요한 유일한 순간").

    `custom/*.yaml` 에 파일을 하나 떨구면 그 표면 패턴이 어휘에 들어온다.

## 왜 필요한가

§6 은 어휘 추가가 필요한 순간을 하나로 못박았다 — **세상에 없던 새 표면 패턴의 첫
등장**. 그런데 지금까지는 그때마다 파이썬 파일을 쓰고 재배포해야 했다. 문서를 보다가
`뷁1아 뷁2아` 같은 처음 보는 표기를 만났을 때, 화면에서 바로 등록하고 다시 돌려 볼 수
있어야 한다.

## 여전히 지키는 선

- **표면만 담는다.** `level` 도 `rank` 도 못 넣는다(관리소가 등록 시점에 막는다).
  계층은 문서가 유도한다.
- **패턴은 `^` 앵커여야 한다.** 앵커 없는 패턴은 문장 한복판의 인용을 그대로 삼킨다.
- 서수는 어느 캡처 그룹에서 읽을지만 말한다. 글자→정수 변환은 기존 어휘
  (`lexicon/numerals.yaml`)가 그대로 한다 — 아라비아·원문자·한글·로마 전부 이미 있다.

## 파일 하나가 규칙 하나

    id: bwek
    family: bwek
    surface: "뷁N아"
    pattern: '^뷁\\s*(\\d+)\\s*아'
    groups: [no]
    ordinal_from: [no]
    lang: any
    note: "2026-08 A은행 약관에서 처음 관찰"

`groups` 는 캡처 그룹의 이름이고, `ordinal_from` 은 그중 서수로 읽을 것이다. 나머지는
기존 제안자와 완전히 같은 계약이므로, 등록된 순간부터 연속 단위·들여쓰기·DP 가
그대로 적용된다.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from core.structure.model import Block, Candidate
from core.structure.proposers import in_paren

ID = "custom"
ROLE = "proposer"
LANG = "any"
FAMILY = "custom"
SURFACE = "사람이 등록한 표면 패턴 (custom/*.yaml)"

DEFAULT_DIR = Path(os.environ.get(
    "STRUCTURE_CUSTOM_DIR", Path(__file__).resolve().parent.parent / "custom"))

# 어휘에 들어오면 안 되는 것 — 계층 지식은 문서가 쥔다(§6)
FORBIDDEN = ("level", "rank", "parent", "depth_order")


class RuleError(ValueError):
    """규칙 파일 오류. 등록 시점에 터진다 — 런타임까지 미루면 해석 도중에 죽는다."""


def validate(data: dict[str, Any]) -> dict[str, Any]:
    """규칙 하나를 검사해 정규화한다. 저장 전에도 이 함수를 쓴다."""
    problems: list[str] = []
    rid = str(data.get("id") or "").strip()
    pattern = str(data.get("pattern") or "")

    if not rid or not all(c.isalnum() or c in "-_" for c in rid):
        problems.append("id 는 영숫자·하이픈·밑줄만 쓸 수 있습니다")
    if not pattern:
        problems.append("pattern 이 비어 있습니다")
    elif not pattern.startswith("^"):
        problems.append("pattern 이 ^ 로 시작해야 합니다 — 앵커가 없으면 "
                        "문장 한복판의 인용까지 삼킵니다")
    else:
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            problems.append(f"pattern 이 정규표현식으로 읽히지 않습니다: {exc}")
            compiled = None
        if compiled is not None:
            groups = list(data.get("groups") or [])
            if len(groups) > compiled.groups:
                problems.append(
                    f"groups 가 {len(groups)}개인데 캡처 그룹은 {compiled.groups}개입니다")
            for g in (data.get("ordinal_from") or []):
                if g not in groups:
                    problems.append(f"ordinal_from 의 '{g}' 가 groups 에 없습니다")
    for bad in FORBIDDEN:
        if bad in data:
            problems.append(f"'{bad}' 는 어휘가 담지 않습니다 — 계층은 문서가 유도합니다")
    if problems:
        raise RuleError("규칙 오류:\n  - " + "\n  - ".join(problems))

    return {
        "id": rid,
        "family": str(data.get("family") or rid),
        "surface": str(data.get("surface") or pattern),
        "pattern": pattern,
        "groups": list(data.get("groups") or []),
        "ordinal_from": list(data.get("ordinal_from") or []),
        "lang": str(data.get("lang") or "any"),
        "note": str(data.get("note") or ""),
    }


def load(directory: Optional[Path] = None) -> list[dict[str, Any]]:
    d = Path(directory or DEFAULT_DIR)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        rule = validate(data)
        if rule["id"] != p.stem:
            raise RuleError(f"{p.name}: id '{rule['id']}' 가 파일명과 다릅니다")
        out.append(rule)
    return out


@lru_cache(maxsize=8)
def _rules(mtime: float, directory: str) -> tuple[tuple[dict, re.Pattern], ...]:
    return tuple((r, re.compile(r["pattern"])) for r in load(Path(directory)))


def rules() -> tuple[tuple[dict, re.Pattern], ...]:
    """디렉터리가 바뀌면 다시 읽는다 — 화면에서 규칙을 더한 직후에도 반영된다."""
    d = Path(DEFAULT_DIR)
    if not d.is_dir():
        return ()
    stamp = max((p.stat().st_mtime for p in d.glob("*.yaml")), default=0.0)
    return _rules(stamp, str(d))


def describe() -> list[dict]:
    return [dict(r) for r, _ in rules()]


def propose(block: Block, lex) -> list[Candidate]:
    out: list[Candidate] = []
    for rule, rx in rules():
        for m in rx.finditer(block.text):
            captured = {name: (m.group(i) or "").strip()
                        for i, name in enumerate(rule["groups"], start=1)
                        if i <= (m.re.groups or 0)}
            ordinal = lex.numerals.ordinal(
                [captured.get(g, "") for g in rule["ordinal_from"]]) \
                if rule["ordinal_from"] else None
            out.append(Candidate(
                id="", family=rule["family"], surface=m.group(0).strip(),
                ordinal=ordinal, block_idx=block.idx, offset=m.start(), end=m.end(),
                page=block.page, element_index=block.element_index, text=block.text,
                construction="full", in_paren=in_paren(block.text, m.start()),
                is_heading=block.is_heading, bbox=block.bbox))
    out.sort(key=lambda c: c.offset)
    return out
