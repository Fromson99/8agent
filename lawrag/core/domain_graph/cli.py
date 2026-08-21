"""도메인 그래프 빌드·조회 CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lawrag.core.rag.index import ROOT, Index, store_path, terms_path

from .builder import GraphBuilder
from .canonical import CanonicalRegistry
from .store import GraphStore


def default_structure() -> Path:
    configured = Path(store_path())
    local = ROOT / "data" / "structure"
    # 서비스는 env를 주입한다. 저장소에서 CLI만 실행할 때는 실제 정본 자리를 쓴다.
    return configured if configured.exists() or not local.exists() else local


def default_data_dir() -> Path:
    return default_structure().parent


def default_glossary() -> Path:
    configured = Path(terms_path())
    local = default_data_dir() / "glossary.json"
    return configured if configured.exists() or not local.exists() else local


def default_db() -> Path:
    return default_data_dir() / "domain_graph" / "graph.sqlite"


def default_canonical() -> Path:
    return default_data_dir() / "domain_graph" / "canonical.json"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="구조·프레임·용어를 로컬 property graph로 조립")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="그래프를 원천 파생물에서 재생성")
    b.add_argument("--output", type=Path, default=default_db())
    b.add_argument("--structure", type=Path, default=default_structure())
    b.add_argument("--glossary", type=Path, default=default_glossary())
    b.add_argument("--data-dir", type=Path, default=default_data_dir())
    b.add_argument("--canonical", type=Path, default=default_canonical())
    b.add_argument("--doc", action="append", dest="docs", help="doc_id (여러 번 지정 가능)")
    b.add_argument("--no-blocks", action="store_true")
    b.add_argument("--no-derived", action="store_true")

    r = sub.add_parser("resolve", help="표면형이 가리키는 개념·문서좌표 조회")
    r.add_argument("surface")
    r.add_argument("--db", type=Path, default=default_db())
    r.add_argument("--doc-id", default="")

    n = sub.add_parser("neighbors", help="노드의 직접 간선 조회")
    n.add_argument("node_id")
    n.add_argument("--db", type=Path, default=default_db())
    n.add_argument("--direction", choices=("out", "in"), default="out")

    c = sub.add_parser("counts", help="노드·간선 종류별 개수")
    c.add_argument("--db", type=Path, default=default_db())

    e = sub.add_parser("export", help="DB를 Graph DB 이관용 JSONL로 내보내기")
    e.add_argument("directory", type=Path)
    e.add_argument("--db", type=Path, default=default_db())
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "build":
        index = Index.load(store=args.structure, terms_file=args.glossary)
        registry = CanonicalRegistry.load(registry_path=args.canonical,
                                          glossary_path=args.glossary)
        result = GraphBuilder(index, data_dir=args.data_dir, registry=registry,
                              glossary_path=args.glossary).build(
            args.output, doc_ids=args.docs, include_blocks=not args.no_blocks,
            include_derived=not args.no_derived)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    with GraphStore(args.db, readonly=True) as store:
        if args.command == "resolve":
            result = store.resolve(args.surface, doc_id=args.doc_id)
        elif args.command == "neighbors":
            result = store.neighbors(args.node_id, direction=args.direction)
        elif args.command == "counts":
            result = store.counts()
        else:
            store.export_jsonl(args.directory)
            result = {"directory": str(args.directory)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
