#!/usr/bin/env python3
"""Build or independently validate a ``legal-graph-v1`` sidecar generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lawrag.core.legal_graph.compiler import BuildConfig, build_generation


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="compile and atomically publish a generation")
    build.add_argument("--structure-store", type=Path, default=Path("data/structure"))
    build.add_argument("--law-index", type=Path, default=Path("data/law_index.json"))
    build.add_argument("--delegation", type=Path, default=Path("data/delegation.json"))
    build.add_argument("--canonical", type=Path,
                       default=Path("data/domain_graph/canonical.json"))
    build.add_argument("--frames-store", type=Path, default=Path("data/frames"))
    build.add_argument("--glossary", type=Path, default=Path("data/glossary.json"))
    build.add_argument("--links", type=Path, default=Path("data/links.json"))
    build.add_argument("--output-root", type=Path, default=Path("data/legal_graph"))
    build.add_argument("--no-publish-current", action="store_true")

    validate = sub.add_parser("validate", help="validate a generation without rebuilding it")
    validate.add_argument("--generation", type=Path,
                          help="generation directory (default: resolve output CURRENT.json)")
    validate.add_argument("--output-root", type=Path, default=Path("data/legal_graph"))
    validate.add_argument("--structure-store", type=Path, default=Path("data/structure"))
    return parser


def _generation_from_pointer(output_root: Path) -> Path:
    pointer_path = output_root / "CURRENT.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    manifest = Path(str(pointer["manifest"]))
    return (output_root / manifest).resolve().parent


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        result = build_generation(BuildConfig(
            structure_store=args.structure_store,
            law_index_file=args.law_index,
            delegation_file=args.delegation,
            canonical_file=args.canonical,
            frames_store=args.frames_store,
            glossary_file=args.glossary,
            links_file=args.links,
            output_root=args.output_root,
            publish_current=not args.no_publish_current,
        ))
        print(json.dumps({
            "generation_id": result.generation_id,
            "generation_path": str(result.generation_path),
            "manifest_path": str(result.manifest_path),
            "content_sha256": result.content_sha256,
            "reused": result.reused,
            "current_path": str(result.current_path) if result.current_path else None,
        }, ensure_ascii=False, sort_keys=True))
        return 0

    generation = args.generation.resolve() if args.generation else \
        _generation_from_pointer(args.output_root.resolve())
    try:
        from lawrag.core.legal_graph.validation import validate_generation
    except ImportError as exc:
        raise SystemExit(f"independent validator is unavailable: {exc}") from exc
    receipt = validate_generation(generation, structure_store=args.structure_store.resolve())
    if hasattr(receipt, "to_dict"):
        receipt = receipt.to_dict()
    elif not isinstance(receipt, dict):
        receipt = {"valid": True, "result": str(receipt)}
    if isinstance(receipt, dict) and (
        receipt.get("ok") is False or receipt.get("valid") is False
    ):
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
