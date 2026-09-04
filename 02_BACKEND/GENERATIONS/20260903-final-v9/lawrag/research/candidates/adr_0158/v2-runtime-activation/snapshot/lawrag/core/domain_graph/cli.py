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


def default_candidates() -> Path:
    return default_data_dir() / "domain_graph" / "candidates.json"


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

    a = sub.add_parser("approve", help="레거시 오프라인 1급 배치 승인(질의 승격에는 사용 안 함)")
    a.add_argument("--candidate", type=Path, default=default_candidates())
    a.add_argument("--db", type=Path, default=default_db())
    a.add_argument("--output", type=Path, default=default_canonical())
    a.add_argument("--audit", type=Path,
                   default=default_data_dir() / "domain_graph" / "approval_audit.json")
    a.add_argument("--batch-size", type=int, default=50)
    a.add_argument("--workers", type=int, default=1,
                   help="동시 Haiku 승인 배치 수 (1..16)")
    a.add_argument("--retry-deferred", action="store_true",
                   help="이미 보류된 후보도 다시 심사")
    a.add_argument("--approve-all", action="store_true",
                   help="사용자 전수 승인: 기존 기각/보류 포함 전부 approve/high (무결성 검증 유지)")

    s = sub.add_parser("stage2", help="그래프의 2급 Concept을 승인 원장에 적재")
    s.add_argument("--db", type=Path, default=default_db())
    s.add_argument("--candidate", type=Path, default=default_candidates())
    s.add_argument("--canonical", type=Path, default=default_canonical())
    s.add_argument("--limit", type=int, default=0)

    fc = sub.add_parser("stage-frame-concepts",
                        help="Frame 슬롯 표면형을 Concept 승인 후보로 적재")
    fc.add_argument("--db", type=Path, default=default_db())
    fc.add_argument("--candidate", type=Path, default=default_candidates())
    fc.add_argument("--canonical", type=Path, default=default_canonical())
    fc.add_argument("--limit", type=int, default=0)

    nc = sub.add_parser("stage-normative-concepts",
                        help="닫힌 규범 양태·기능 Concept을 승인 후보로 적재")
    nc.add_argument("--candidate", type=Path, default=default_candidates())
    nc.add_argument("--canonical", type=Path, default=default_canonical())

    rc = sub.add_parser(
        "stage-requirement-concepts",
        help="조건·예외·시점·수치·방법·효과 span을 불확실성 포함 Concept 후보로 적재")
    rc.add_argument("--db", type=Path, default=default_db())
    rc.add_argument("--candidate", type=Path, default=default_candidates())
    rc.add_argument("--canonical", type=Path, default=default_canonical())
    rc.add_argument("--limit", type=int, default=0)

    pn = sub.add_parser("promote-normative-facets",
                        help="승인된 Frame mode/function을 canonical 역할로 승격")
    pn.add_argument("--canonical", type=Path, default=default_canonical())
    pn.add_argument("--candidate", type=Path, default=default_candidates())
    pn.add_argument("--reviewer", default="user:normative-facet-migration")
    pn.add_argument("--dry-run", action="store_true")

    af = sub.add_parser("assertion-freshness",
                        help="현행 조문과 canonical Assertion 출처의 개정 정합성 진단")
    af.add_argument("--structure", type=Path, default=default_structure())
    af.add_argument("--canonical", type=Path, default=default_canonical())
    af.add_argument("--limit", type=int, default=100)

    fk = sub.add_parser("stage-frame-knowledge",
                        help="승인 Concept로 Frame Assertion·taxonomy Relation 후보 조립")
    fk.add_argument("--db", type=Path, default=default_db())
    fk.add_argument("--candidate", type=Path, default=default_candidates())
    fk.add_argument("--canonical", type=Path, default=default_canonical())
    fk.add_argument("--limit", type=int, default=0)

    tq = sub.add_parser("term-queue", help="LLM이 제안하고 사람 판정을 기다리는 표현 목록")
    tq.add_argument("--status", choices=("pending", "approved", "rejected", "all"),
                    default="pending")
    tr = sub.add_parser("term-resolve", help="표현 제안을 사람이 승인 또는 기각")
    tr.add_argument("proposal_id")
    tr.add_argument("action", choices=("승인", "기각", "approve", "reject"))
    tr.add_argument("--reviewer", default="user")
    tr.add_argument("--note", default="")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command in ("term-queue", "term-resolve"):
        from lawrag.core.rag import term_proposals

        if args.command == "term-queue":
            result = {"proposals": term_proposals.queue(args.status)}
        else:
            result = term_proposals.resolve(
                args.proposal_id, args.action,
                reviewer=args.reviewer, note=args.note)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "approve":
        from .approval import approve
        llm = None
        if not args.approve_all:
            from lawrag.core import llm as llm_mod
            if not llm_mod.available():
                parser().error(f"LLM 없음 — {llm_mod.MISSING_HINT}")
            llm = llm_mod.LLM()
        def report(pos, total, size, decided):
            print(f"승인 배치 {pos}/{total} · 후보 {size} · 누적 판정 {decided}", flush=True)
        result = approve(llm, args.candidate, args.db,
                         args.output, args.audit, batch_size=args.batch_size,
                         workers=args.workers, retry_deferred=args.retry_deferred,
                         force_all=args.approve_all,
                         progress=report)
        summary = {k: v for k, v in result.items() if k not in ("decisions", "reasons")}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.command == "stage2":
        from .candidates import stage_grade2
        result = stage_grade2(args.db, args.candidate, args.canonical,
                              limit=max(0, args.limit))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "stage-frame-concepts":
        from .candidates import stage_frame_concepts
        result = stage_frame_concepts(args.db, args.candidate, args.canonical,
                                      limit=max(0, args.limit))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "stage-normative-concepts":
        from .candidates import stage_normative_concepts
        result = stage_normative_concepts(args.candidate, args.canonical)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "stage-requirement-concepts":
        from .candidates import stage_requirement_concepts
        result = stage_requirement_concepts(
            args.db, args.candidate, args.canonical, limit=max(0, args.limit))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "promote-normative-facets":
        from .normative import promote_candidate_blob, promote_registry_blob
        blob = json.loads(args.canonical.read_text(encoding="utf-8"))
        result = promote_registry_blob(blob, approved_by=args.reviewer)
        candidate_result = {}
        candidate_blob = None
        if args.candidate.is_file():
            candidate_blob = json.loads(args.candidate.read_text(encoding="utf-8"))
            candidate_result = promote_candidate_blob(
                candidate_blob, approved_by=args.reviewer)
        if not args.dry_run:
            temporary = args.canonical.with_suffix(args.canonical.suffix + ".tmp")
            temporary.write_text(
                json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(args.canonical)
            if candidate_blob is not None:
                candidate_tmp = args.candidate.with_suffix(args.candidate.suffix + ".tmp")
                candidate_tmp.write_text(
                    json.dumps(candidate_blob, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                candidate_tmp.replace(args.candidate)
        print(json.dumps({**result, "candidate": candidate_result,
                          "dry_run": bool(args.dry_run),
                          "canonical": str(args.canonical)},
                         ensure_ascii=False, indent=2))
        return 0
    if args.command == "assertion-freshness":
        from .freshness import audit
        from .tier1 import Tier1Registry
        index = Index.load(store=args.structure).scoped(None)
        registry = Tier1Registry.load(args.canonical)
        result = audit(index, registry, detail_limit=max(0, args.limit))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "stage-frame-knowledge":
        from .candidates import stage_frame_knowledge
        result = stage_frame_knowledge(args.db, args.candidate, args.canonical,
                                       limit=max(0, args.limit))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "build":
        index = Index.load(
            store=args.structure, terms_file=args.glossary,
            links_file=args.data_dir / "links.json")
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


if __name__ == "__main__":
    raise SystemExit(main())
