"""금융위 회신사례(법령해석·비조치의견서) 수집기 — raw 층을 만든다.

    python -m lawrag.pipeline.collect_fsc --dry-run      # 질의 계획과 목록 수만 (상세는 안 받는다)
    python -m lawrag.pipeline.collect_fsc                # 수집 (재실행 시 멱등 skip)
    python -m lawrag.pipeline.collect_fsc --force
    python -m lawrag.pipeline.collect_fsc --query "명칭"   # 임시 질의 추가

무엇을 받을지는 코퍼스가 결정한다 — data/corpus/law/manifest.json 에서 **소관부처에
'금융'이 든 문서**(금융위원회·금융감독원)의 명칭이 질의 집합이다. 이 포털은
금융위 소관이라 상법·개인정보법 질의는 원리적으로 이 소스의 것이 아니다
(그쪽은 법제처 expc 가 받는다). 부분일치 축약은 expc 와 같다(plan_queries).

포털의 본문검색(searchCondition=all)이 서버에서 돌므로 목록 자체가 이미
"질의 명칭을 본문에 담은" 사례들이다. 그 위에 관련 명칭 판정을 한 번 더
한다 — 낫표 관례가 없는 문서라 앞 경계(비한글) 평문 판정(lawrag/sources/cite)이다.

저장 (llm-wiki raw 층의 원천 — corpus 는 수집 정본):
    data/corpus/fsc/cases/<유형gubun>-<idx>.html   상세 원문
    data/corpus/fsc/manifest.json                 대장 (phase_model 선언 — 원장 밖)
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
from lawrag.sources.fsc import DETAIL, FscClient, case_text, parse_detail
from lawrag.platform.paths import (
    data_path,
    repository_root,
    runtime_path,
    persisted_data_path,
)

REPO_ROOT = repository_root()
CORPUS_DIR = data_path("corpus")
FSC_DIR = CORPUS_DIR / "fsc"
CASES_DIR = FSC_DIR / "cases"
LOG_DIR = runtime_path("logs")


def corpus_names() -> tuple[list[str], list[str]]:
    """(질의 명칭 — 금융 소관만, 인용 판정 명칭 — 전부)."""
    m = json.loads((CORPUS_DIR / "law" / "manifest.json").read_text("utf-8"))
    queries, citable = [], []
    for item in m["items"]:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        citable.append(name)
        if "금융" in (item.get("dept") or ""):
            queries.append(name)
    return queries, citable


def item_intact(item: dict | None) -> bool:
    if not item or not item.get("file"):
        return False
    f = persisted_data_path(item["file"])
    return f.exists() and sha256_file(f) == item.get("sha256")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="금융위 회신사례 수집기")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--query", action="append", default=[], metavar="명칭")
    args = ap.parse_args(argv)

    logger = build_logger(LOG_DIR, "fsc")
    client = HttpClient(make_session(), logger)
    api = FscClient(client)

    query_names, citable = corpus_names()
    queries = plan_queries(query_names + args.query)
    print(f"질의 {len(queries)}건 (금융 소관 명칭 {len(query_names)}건에서 축약)")

    manifest_path = FSC_DIR / "manifest.json"
    manifest = load_manifest(manifest_path)
    manifest["source"] = "better.fsc.go.kr 회신사례"
    manifest["phase_model"] = "수집→색인→위키 (lawrag/pipeline/ingest_fsc.py · data/wiki/raw/fsc)"

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
            print(f"[{q}] {total}건 (유형 채택 {len(rows)}건)")
            for row in rows:
                if not row["idx"]:
                    continue
                key = f"{DETAIL[row['kind']][0]}-{row['idx']}"
                found.setdefault(key, row)
                hit_queries.setdefault(key, []).append(q)

        if args.dry_run:
            fresh = [k for k in found
                     if args.force or not item_intact(manifest_item(manifest, k))]
            print(f"\n합집합 {len(found)}건 — 새로 받을 상세 {len(fresh)}건")
            return 0

        CASES_DIR.mkdir(parents=True, exist_ok=True)
        for key in sorted(found):
            row = found[key]
            existing = manifest_item(manifest, key)
            if not args.force and item_intact(existing):
                existing["queries"] = sorted(set(existing.get("queries", []))
                                             | set(hit_queries[key]))
                save_manifest(manifest_path, manifest)
                skipped += 1
                continue
            item = {"name": key, "kind": row["kind"], "label": row["title"],
                    "replied": row["replied"],
                    "queries": sorted(set(hit_queries[key])), "status": "error"}
            try:
                html_text = api.fetch_detail(row["kind"], row["idx"])
            except FetchError as e:
                item["error"] = str(e)
                upsert_item(manifest, item)
                save_manifest(manifest_path, manifest)
                failed += 1
                print(f"[{key}] 상세 실패: {e}", file=sys.stderr)
                continue

            path = CASES_DIR / f"{key}.html"
            path.write_bytes(html_text.encode("utf-8"))
            case = parse_detail(html_text)
            laws = plain_mentions(case_text(case, row["title"]), citable)
            item.update({
                "file": str(path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(path), "size": path.stat().st_size,
                "actual_format": "html", "dept": case.get("dept", ""),
                "laws": laws, "status": "ok",
            })
            upsert_item(manifest, item)
            save_manifest(manifest_path, manifest)   # 건 단위 저장 — 중단돼도 보존
            ok += 1
            if not laws:
                unrelated += 1
    except CrawlAborted as e:
        aborted = True
        print(f"\n!! 차단 감지 — 전체 중단: {e}", file=sys.stderr)

    print(f"\n완료: ok={ok} skipped={skipped} failed={failed}"
          f" (인용 없음 {unrelated}건 — 색인이 거른다)"
          f" 요청수={client.request_count}{' (중단됨)' if aborted else ''}")
    return 2 if aborted else (1 if failed and not ok else 0)


if __name__ == "__main__":
    sys.exit(main())
