#!/usr/bin/env python3
"""Read-only validation receipt for the current legal-system routing catalog."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_research_atlas import LegalResearchAtlas
from lawrag.core.rag.legal_system_map import (
    LegalGraphSemanticCardIndex,
    load_legal_system_map,
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preload-semantic-cards",
        action="store_true",
        help="also cold/warm-load the existing verified Legal Graph snapshot",
    )
    args = parser.parse_args()
    index = Index.load(
        store=ROOT / "data" / "structure",
        terms_file=ROOT / "data" / "glossary.json",
        links_file=ROOT / "data" / "links.json",
    )
    atlas = LegalResearchAtlas.from_index(index)
    system_map = load_legal_system_map(atlas)
    purpose_sources = Counter(row.purpose_source for row in system_map.profiles)
    output = {
        "ok": True,
        "schema_version": system_map.schema_version,
        "catalog_version": system_map.catalog_version,
        "authority_generation": system_map.authority_generation,
        "authority_as_of": system_map.authority_as_of,
        "current_instruments": len(atlas.instruments),
        "profiled_instruments": len(system_map.profiles),
        "profiles_with_purpose": sum(bool(row.purpose) for row in system_map.profiles),
        "purpose_sources": dict(sorted(purpose_sources.items())),
        "issue_families": len(system_map.issue_families),
        "effective_dates_sha256": system_map.effective_dates_sha256,
        "profiles_sha256": system_map.profiles_sha256,
        "legal_graph_generation": system_map.legal_graph.generation_id,
        "semantic_card_rows": system_map.legal_graph.semantic_cards_rows,
        "semantic_cards_preloaded": False,
    }
    if args.preload_semantic_cards:
        cards = LegalGraphSemanticCardIndex(atlas, system_map)
        output["article_cards"] = cards.preload()
        output["semantic_cards_preloaded"] = True
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
