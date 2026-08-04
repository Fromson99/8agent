"""T10. 필드 매핑 — normalize → exact → alias → UNMAPPED (SPEC §B5).

별칭은 온톨로지 `fields.*.aliases` 에서 온다(§C8 T15: aliases.yaml 흡수).
하위호환으로 config/aliases.yaml 이 있으면 함께 읽는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import comparators as cmp
from ontology import Ontology


def normalize(name: str) -> str:
    """§B5-1 — 공백·괄호·단위·조사 제거 후 비교."""
    return cmp.normalize_text(name)


class Mapper:
    def __init__(self, onto: Ontology, extra_aliases: Optional[Path] = None):
        self.onto = onto
        self.index = onto.alias_index()
        if extra_aliases and Path(extra_aliases).exists():
            self._absorb_yaml(Path(extra_aliases))

    def _absorb_yaml(self, path: Path) -> None:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for canonical, names in (data.get("aliases") or {}).items():
            if canonical not in self.onto.fields:
                continue                       # 온톨로지에 없는 필드는 무시
            self.index.setdefault(normalize(canonical), canonical)
            for n in names or []:
                self.index.setdefault(normalize(n), canonical)

    def resolve(self, summary_label: str) -> Optional[str]:
        """요약서 라벨 → 별지1 정규 필드명. 못 찾으면 None(=UNMAPPED)."""
        n = normalize(summary_label)
        if not n:
            return None
        if n in self.index:
            return self.index[n]
        # 부분 포함 — 요약서가 "투자금액(원)" 처럼 덧붙이는 경우
        for key, canonical in self.index.items():
            if len(key) >= 3 and (key in n or n in key):
                return canonical
        return None

    def build(self, summary_facts) -> dict[str, object]:
        """정규 필드명 → 요약서 Fact. 먼저 매핑된 것이 이긴다."""
        out: dict[str, object] = {}
        for f in summary_facts:
            canonical = self.resolve(f.field_name)
            if canonical and canonical not in out:
                out[canonical] = f
        return out
