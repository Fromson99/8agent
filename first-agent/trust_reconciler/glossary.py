"""용어집 — 계약서와 설명서가 같은 것을 다르게 부르는 표현을 묶는다.

두 경로로 채워진다 (사용자 요구).
    user  현업이 직접 추가. 항상 우선.
    llm   태깅 중 LLM 이 발견해 제안. 리포트에 올라오고, 사람이 확인하면 user 로 승격.

P3(1단계 섹션 대응)에서 **전수 비교를 피하는 장치**로 쓰인다.
두 문서의 섹션을 모두 곱해 LLM 에 물으면 비용이 폭발한다.
공유 용어가 하나도 없는 조합은 애초에 후보에서 뺀다.

정규표현식을 쓰지 않는다. 표면형 조회는 textkit.fold 로 정규화한 문자열 포함 검사다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .textkit import fold


@dataclass
class Term:
    canonical: str
    display: str = ""
    value_type: str = "text"
    surfaces: list[str] = field(default_factory=list)
    confusable_with: list[str] = field(default_factory=list)
    source: str = "seed"           # user | llm | seed
    note: str = ""

    def folded(self) -> list[tuple[str, str]]:
        """(정규화 표면형, 원본 표면형). 긴 것부터 — '신탁보수율'이 '보수율'보다 먼저 잡혀야 한다."""
        pairs = [(fold(s), s) for s in ([self.display] + self.surfaces) if s]
        pairs = [(f, s) for f, s in pairs if len(f) >= 2]
        return sorted(set(pairs), key=lambda p: -len(p[0]))


class Glossary:
    def __init__(self, terms: Iterable[Term] | None = None, version: str = "1.0"):
        self.version = version
        self.terms: dict[str, Term] = {t.canonical: t for t in (terms or [])}
        self._index: list[tuple[str, str, str]] = []      # (folded, surface, canonical)
        self._reindex()

    # --- 로드 / 저장 -------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "Glossary":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        terms = [Term(**{k: v for k, v in t.items() if not k.startswith("_")})
                 for t in data.get("terms", [])]
        return cls(terms, version=data.get("version", "1.0"))

    def save(self, path: str | Path) -> None:
        """LLM 제안까지 포함해 되쓴다. 사람이 열어 source 를 user 로 바꾸면 확정된다."""
        p = Path(path)
        original = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        original["version"] = self.version
        original["terms"] = [
            {k: v for k, v in vars(t).items() if v not in ([], "", None)}
            for t in sorted(self.terms.values(), key=lambda t: (t.source != "user", t.canonical))
        ]
        p.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")

    def _reindex(self) -> None:
        idx = []
        for t in self.terms.values():
            for f, s in t.folded():
                idx.append((f, s, t.canonical))
        # 긴 표면형이 먼저 매칭되도록 정렬
        self._index = sorted(idx, key=lambda x: -len(x[0]))

    # --- 조회 -------------------------------------------------------------
    def lookup(self, surface: str) -> Optional[str]:
        """표면형 하나 → canonical. 정확 포함만 본다 (유사도 추정을 하지 않는다)."""
        f = fold(surface)
        if not f:
            return None
        for ff, _s, canonical in self._index:
            if ff == f:
                return canonical
        return None

    def find_in(self, text: str) -> list[str]:
        """텍스트에 등장한 용어의 canonical 목록. 긴 표면형이 먼저 잡히고, 겹치면 한 번만 센다."""
        f = fold(text)
        if not f:
            return []
        found: list[str] = []
        for ff, _s, canonical in self._index:
            if canonical in found:
                continue
            if ff and ff in f:
                found.append(canonical)
        return found

    def confusable(self, canonical: str) -> set[str]:
        t = self.terms.get(canonical)
        return set(t.confusable_with) if t else set()

    def display(self, canonical: str) -> str:
        t = self.terms.get(canonical)
        return t.display if t and t.display else canonical

    # --- LLM 제안 반영 -----------------------------------------------------
    def absorb(self, suggestions: Iterable[dict]) -> list[dict]:
        """LLM 이 제안한 용어를 받아들인다.

        기존 용어에 표면형만 추가되는 경우와, 아예 새 용어인 경우를 구분해 기록한다.
        사용자가 만든 항목(source=user)은 절대 덮어쓰지 않는다.
        """
        applied: list[dict] = []
        for s in suggestions or []:
            canonical = (s.get("canonical") or "").strip()
            surfaces = [x for x in (s.get("surfaces") or []) if x]
            if not canonical or not surfaces:
                continue
            existing = self.terms.get(canonical)
            if existing:
                if existing.source == "user":
                    continue
                added = [x for x in surfaces if fold(x) not in {f for f, _ in existing.folded()}]
                if not added:
                    continue
                existing.surfaces.extend(added)
                applied.append({"canonical": canonical, "added_surfaces": added,
                                "kind": "surface_added"})
            else:
                self.terms[canonical] = Term(
                    canonical=canonical, display=s.get("display") or canonical,
                    value_type=s.get("value_type", "text"), surfaces=surfaces,
                    confusable_with=s.get("confusable_with") or [], source="llm",
                    note=s.get("note", ""))
                applied.append({"canonical": canonical, "surfaces": surfaces, "kind": "new_term",
                                "display": s.get("display") or canonical})
        if applied:
            self._reindex()
        return applied

    def pending_review(self) -> list[dict]:
        """사람이 확인해야 할 LLM 제안 목록."""
        return [{"canonical": t.canonical, "display": t.display, "surfaces": t.surfaces,
                 "value_type": t.value_type, "note": t.note}
                for t in self.terms.values() if t.source == "llm"]
