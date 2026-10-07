"""판례(prec) 수집기 — 코퍼스 법령 관련 대법원·하급심 판례.

    python -m lawrag.pipeline.collect_prec --dry-run
    python -m lawrag.pipeline.collect_prec
    python -m lawrag.pipeline.collect_prec --force
    python -m lawrag.pipeline.collect_prec --query "명칭"

질의는 01_DATA/INBOX/AUTHORING/corpus/law/manifest.json 의 법령(kind=law) 명칭 — 사건명(evtNm)
부분일치 검색이라 법률 명칭이 실용적이다(감독규정 위반은 사건명이 아니라
참조조문에 나온다 — 관련 판정이 그쪽을 본다). 축약·멱등·원문 보존은
lawrag/pipeline/collect_expc.py 와 같은 규율.

관련 법령 판정은 평문 경계 판정(lawrag/sources/cite.plain_mentions) — 사건명·
판시사항·판결요지·참조조문에서 코퍼스 명칭을 찾되 '국가배상법' 속 '상법'
같은 꼬리 일치는 거른다. 전문(판례내용)은 판정에 안 쓴다(방론 소음).

저장:
    01_DATA/INBOX/AUTHORING/corpus/prec/cases/<판례일련번호>.xml    원문 (전문 포함)
    01_DATA/INBOX/AUTHORING/corpus/prec/manifest.json             대장 (phase_model — 원장 밖)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lawrag.sources.cite import plain_mentions
from lawrag.sources.common import (
    CrawlAborted,
    FetchError,
    HttpClient,
    build_logger,
    load_manifest,
    make_session,
    manifest_item,
    save_manifest,
    sha256_file,
    upsert_item,
)
from lawrag.sources.expc import plan_queries
from lawrag.sources.prec import PrecClient, case_text, parse_case
from lawrag.platform.paths import (
    data_path,
    repository_root,
    runtime_path,
    persisted_data_path,
)

REPO_ROOT = repository_root()
CORPUS_DIR = data_path("INBOX", "AUTHORING", "corpus")
PREC_DIR = CORPUS_DIR / "prec"
CASES_DIR = PREC_DIR / "cases"
LOG_DIR = runtime_path("logs")


def corpus_names() -> tuple[list[str], list[str]]:
    m = json.loads((CORPUS_DIR / "law" / "manifest.json").read_text("utf-8"))
    queries, citable = [], []
    for item in m["items"]:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        citable.append(name)
        if item.get("kind") == "law":
            queries.append(name)
    return queries, citable


def item_intact(item: dict | None) -> bool:
    if not item or not item.get("file"):
        return False
    f = persisted_data_path(item["file"])
    return f.exists() and sha256_file(f) == item.get("sha256")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="판례 수집기")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--query", action="append", default=[], metavar="명칭")
    args = ap.parse_args(argv)

    logger = build_logger(LOG_DIR, "prec")
    client = HttpClient(make_session(), logger)
    api = PrecClient(client)

    query_names, citable = corpus_names()
    queries = plan_queries(query_names + args.query)
    print(f"질의 {len(queries)}건 (법령 명칭 {len(query_names)}건에서 축약)")

    manifest_path = PREC_DIR / "manifest.json"
    manifest = load_manifest(manifest_path)
    manifest["source"] = "law.go.kr OPEN API (prec)"
    manifest["phase_model"] = "수집→색인→위키 (lawrag/pipeline/ingest_prec.py · data/wiki/raw/prec)"

    found: dict[str, dict] = {}
    hit_queries: dict[str, list[str]] = {}
    aborted = False
    ok = skipped = failed = unrelated = 0
    try:
        for q in queries:
            try:
                total, rows = api.search_all(q)
            except (FetchError, RuntimeError) as e:
                print(f"[{q}] 목록 실패: {e}", file=sys.stderr)
                continue
            print(f"[{q}] {total}건")
            for row in rows:
                if not row["serial"]:
                    continue
                found.setdefault(row["serial"], row)
                hit_queries.setdefault(row["serial"], []).append(q)

        if args.dry_run:
            fresh = [s for s in found
                     if args.force or not item_intact(manifest_item(manifest, s))]
            print(f"\n합집합 {len(found)}건 — 새로 받을 본문 {len(fresh)}건")
            return 0

        CASES_DIR.mkdir(parents=True, exist_ok=True)
        for serial in sorted(found):
            row = found[serial]
            existing = manifest_item(manifest, serial)
            if not args.force and item_intact(existing):
                existing["queries"] = sorted(set(existing.get("queries", []))
                                             | set(hit_queries[serial]))
                save_manifest(manifest_path, manifest)
                skipped += 1
                continue
            item = {"name": serial, "kind": "prec", "label": row["label"],
                    "case_no": row["case_no"], "court": row["court"],
                    "case_kind": row["kind"], "replied": row["decided"],
                    "queries": sorted(set(hit_queries[serial])),
                    "status": "error"}
            try:
                xml_text = api.fetch_case(serial)
            except (FetchError, RuntimeError) as e:
                item["error"] = str(e)
                upsert_item(manifest, item)
                save_manifest(manifest_path, manifest)
                failed += 1
                print(f"[{row['case_no']}] 본문 실패: {e}", file=sys.stderr)
                continue

            path = CASES_DIR / f"{serial}.xml"
            path.write_bytes(xml_text.encode("utf-8"))
            case = parse_case(xml_text)
            laws = plain_mentions(case_text(case), citable)
            item.update({
                "file": str(path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(path), "size": path.stat().st_size,
                "actual_format": "xml", "decided": case["decided"],
                "laws": laws, "status": "ok",
            })
            upsert_item(manifest, item)
            save_manifest(manifest_path, manifest)
            ok += 1
            if not laws:
                unrelated += 1
    except CrawlAborted as e:
        aborted = True
        print(f"\n!! 차단 감지 — 전체 중단: {e}", file=sys.stderr)

    print(f"\n완료: ok={ok} skipped={skipped} failed={failed}"
          f" (인용 없음 {unrelated}건)"
          f" 요청수={client.request_count}{' (중단됨)' if aborted else ''}")
    return 2 if aborted else (1 if failed and not ok else 0)


if __name__ == "__main__":
    sys.exit(main())
