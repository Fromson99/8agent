"""오케스트레이션 + CLI.

    P1 파싱   도클링 → 블록          parsers.parse
    P2 태깅   블록 → 섹션 → 요소     pipeline.tag_document        [LLM]
    P3 1단계  섹션 대응              pipeline.pair_sections       [코드 축소 + LLM]
    P4 2단계  값 비교                pipeline.compare_elements    [코드 + LLM 폴백]
    P5 완결성 / 리포트               report

사용
    python -m trust_reconciler.main --contract a.pdf --statement b.pdf --out out/run1
    python -m trust_reconciler.main ... --tags trust_fee,trust_period   # 이번 건만 좁혀서
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import parsers, pipeline, report as reporting
from .cache import SnapshotStore, prompt_fingerprint
from .docmodel import Report, to_jsonable
from .glossary import Glossary
from .llm.client import LLMUnavailable, get_client
from .textkit import truncate

CONFIG_DIR = Path(__file__).parent / "config"
CACHE_DIR = Path(__file__).parent.parent / "snapshots"


def load_json(name: str, override: Optional[str] = None) -> dict:
    path = Path(override) if override else CONFIG_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def filter_schema(schema: dict, tags: Optional[list[str]]) -> dict:
    """이번 대사에서 볼 태그만 남긴다. 프론트에서 사용자가 고른 것을 그대로 받는다."""
    if not tags:
        return schema
    keep = set(tags)
    out = dict(schema)
    out["sections"] = [s for s in schema.get("sections", []) if s["id"] in keep]
    return out


def _meta_from_llm(doc, llm) -> None:
    """발행사·기준일·상품유형을 LLM 이 채운다.

    예전에는 정규식 6종으로 뽑았고 dataset 9종 중 4종(44%)만 성공했다.
    3종은 문서에 연도 표기가 아예 없어 어떤 패턴으로도 불가능했다 —
    LLM 도 못 찾으면 None 을 남기고, 리포트가 '기준일 미확인'으로 경고한다.
    """
    head = doc.blocks[:25]
    res = llm.doc_meta({
        "doc_role": doc.doc_role,
        "file_name": Path(doc.source_path).name,
        "blocks": [{"block_id": b.block_id, "kind": b.kind,
                    "page": b.provenance.page, "text": truncate(b.content(), 300)}
                   for b in head],
    })
    doc.meta.title = res.get("title") or doc.meta.title
    doc.meta.issuer = res.get("issuer")
    doc.meta.version_date = res.get("version_date")
    doc.meta.product_type = res.get("product_type") or "일반"
    doc.meta.confidence = float(res.get("confidence") or 0.0)
    doc.meta.evidence = res.get("evidence", "")


def reconcile(contract_file: str,
              statement_file: str,
              tag_schema: Optional[dict] = None,
              glossary_path: Optional[str] = None,
              mapping_table: Optional[dict] = None,
              tags: Optional[list[str]] = None,
              authority: str = "contract",
              llm_backend: str = "auto",
              snapshot: Optional[str] = None,
              verify_all_pairs: bool = False,
              save_glossary: bool = True) -> Report:
    schema = filter_schema(tag_schema or load_json("tag_schema.json"), tags)
    mapping_table = mapping_table or load_json("mapping_table.json")
    gpath = Path(glossary_path) if glossary_path else CONFIG_DIR / "glossary.json"
    glossary = Glossary.load(gpath)

    store = SnapshotStore(snapshot or (CACHE_DIR / "run.json"),
                          prompt_fingerprint=prompt_fingerprint())
    llm = get_client(llm_backend, store=store)

    # P1 — 파싱 (LLM 없음)
    c_parsed = parsers.parse(contract_file, "contract")
    s_parsed = parsers.parse(statement_file, "product_statement")

    # 메타 (LLM)
    _meta_from_llm(c_parsed, llm)
    _meta_from_llm(s_parsed, llm)

    # P2 — 태깅
    c_tagged = pipeline.tag_document(c_parsed, schema, glossary, llm)
    s_tagged = pipeline.tag_document(s_parsed, schema, glossary, llm)

    # P3 — 1단계
    pairs = pipeline.pair_sections(c_tagged, s_tagged, schema, glossary, llm,
                                   verify_all=verify_all_pairs)

    # P4 — 2단계
    comparisons = pipeline.compare_elements(pairs, c_tagged, s_tagged, schema,
                                            mapping_table, llm)

    # P5 — 완결성 + 리포트
    completeness = reporting.check_completeness(s_tagged, schema, s_parsed.meta.product_type)
    rep = reporting.build(c_parsed, s_parsed, c_tagged, s_tagged, pairs, comparisons,
                          completeness, schema, authority=authority, backend=llm.name,
                          glossary_pending=glossary.pending_review())

    store.save()
    if save_glossary:
        glossary.save(gpath)          # LLM 이 제안한 용어가 파일에 남아 사람이 확인할 수 있게
    return rep


def build_bundle(contract_file: str, statement_file: str, **kwargs) -> dict:
    """리포트 + 중간 산출물을 한 덩어리 JSON 으로.

    프론트(viewer)가 파이프라인 각 단계를 다 보여줄 수 있어야 하므로,
    최종 리포트만이 아니라 원본 블록·태깅 결과·스냅샷 통계까지 함께 담는다.
    reconcile() 을 다시 부르지 않고 내부 단계를 직접 태워 중간값을 붙든다.
    """
    schema = filter_schema(kwargs.get("tag_schema") or load_json("tag_schema.json"),
                           kwargs.get("tags"))
    mapping = kwargs.get("mapping_table") or load_json("mapping_table.json")
    gpath = Path(kwargs.get("glossary_path") or (CONFIG_DIR / "glossary.json"))
    glossary = Glossary.load(gpath)

    store = SnapshotStore(kwargs.get("snapshot") or (CACHE_DIR / "run.json"),
                          prompt_fingerprint=prompt_fingerprint())
    llm = get_client(kwargs.get("llm_backend", "auto"), store=store)

    c_parsed = parsers.parse(contract_file, "contract")
    s_parsed = parsers.parse(statement_file, "product_statement")
    _meta_from_llm(c_parsed, llm)
    _meta_from_llm(s_parsed, llm)

    c_tagged = pipeline.tag_document(c_parsed, schema, glossary, llm)
    s_tagged = pipeline.tag_document(s_parsed, schema, glossary, llm)
    pairs = pipeline.pair_sections(c_tagged, s_tagged, schema, glossary, llm,
                                   verify_all=kwargs.get("verify_all_pairs", False))
    comparisons = pipeline.compare_elements(pairs, c_tagged, s_tagged, schema, mapping, llm)
    completeness = reporting.check_completeness(s_tagged, schema, s_parsed.meta.product_type)
    rep = reporting.build(c_parsed, s_parsed, c_tagged, s_tagged, pairs, comparisons,
                          completeness, schema, authority=kwargs.get("authority", "contract"),
                          backend=llm.name, glossary_pending=glossary.pending_review())
    store.save()

    return {
        "report": to_jsonable(rep),
        "parsed": {"contract": to_jsonable(c_parsed), "statement": to_jsonable(s_parsed)},
        "tagged": {"contract": to_jsonable(c_tagged), "statement": to_jsonable(s_tagged)},
        "schema": schema,
        "glossary": {"version": glossary.version,
                     "terms": [vars(t) for t in glossary.terms.values()]},
        "mapping_table": mapping,
        "snapshot_stats": store.stats,
        "inputs": {"contract": contract_file, "statement": statement_file},
    }


def deliver(rep: Report, channel: str = "mail", target: Optional[str] = None) -> dict:
    """결과 전달 스텁 — 메일/SCS 연동 자리. 페이로드 형태만 고정해 둔다."""
    return {
        "channel": channel, "target": target,
        "subject": f"[신탁 대사] 불일치 {rep.summary.get('mismatch')}건 / "
                   f"누락 {rep.summary.get('missing')}건",
        "body_markdown": reporting.to_markdown(rep),
        "attachment_json": to_jsonable(rep),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="trust_reconciler",
                                 description="신탁계약서 ↔ 핵심상품설명서 대사")
    ap.add_argument("--contract", required=True)
    ap.add_argument("--statement", required=True)
    ap.add_argument("--schema", help="tag_schema.json 경로")
    ap.add_argument("--glossary", help="glossary.json 경로")
    ap.add_argument("--mapping", help="mapping_table.json 경로")
    ap.add_argument("--tags", help="이번에 볼 태그만 쉼표로 (프론트 선택값)")
    ap.add_argument("--authority", default="contract", choices=["contract", "change_table"])
    ap.add_argument("--llm", default="auto", choices=["auto", "anthropic", "snapshot"])
    ap.add_argument("--snapshot", help="스냅샷 파일 경로 (기본 snapshots/run.json)")
    ap.add_argument("--verify-all-pairs", action="store_true",
                    help="태그가 같은 쌍도 LLM 이 다시 확인 (정확↑ 비용↑)")
    ap.add_argument("--out", help="결과 저장 디렉토리")
    args = ap.parse_args(argv)

    try:
        rep = reconcile(
            args.contract, args.statement,
            tag_schema=load_json("tag_schema.json", args.schema),
            glossary_path=args.glossary,
            mapping_table=load_json("mapping_table.json", args.mapping),
            tags=[t.strip() for t in args.tags.split(",")] if args.tags else None,
            authority=args.authority, llm_backend=args.llm, snapshot=args.snapshot,
            verify_all_pairs=args.verify_all_pairs)
    except LLMUnavailable as e:
        print(f"실행할 수 없습니다: {e}", file=sys.stderr)
        print("이 파이프라인은 문서 해석을 전부 LLM 에 맡깁니다(정규식 미사용). "
              "ANTHROPIC_API_KEY 를 설정하거나 --snapshot 으로 기록본을 주세요.", file=sys.stderr)
        return 2

    md = reporting.to_markdown(rep)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(
            json.dumps(to_jsonable(rep), ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "report.md").write_text(md, encoding="utf-8")
        print(f"저장됨: {out/'report.json'}, {out/'report.md'}")
    print(md)
    return 1 if rep.summary.get("high_severity", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
