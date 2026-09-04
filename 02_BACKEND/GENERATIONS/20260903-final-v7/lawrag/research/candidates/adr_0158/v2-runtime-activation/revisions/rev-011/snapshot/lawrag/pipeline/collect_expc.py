"""법령해석례(expc) 수집기 — raw 층을 만든다.

    python -m lawrag.pipeline.collect_expc --dry-run     # 질의 계획과 목록 수만 (본문은 안 받는다)
    python -m lawrag.pipeline.collect_expc               # 수집 (재실행 시 멱등 skip)
    python -m lawrag.pipeline.collect_expc --force       # 멱등성 무시하고 재수집
    python -m lawrag.pipeline.collect_expc --query "명칭"  # 코퍼스 밖 질의 임시 추가

무엇을 받을지는 선언이 아니라 **코퍼스가 결정한다**: data/corpus/law/manifest.json
의 법령(kind=law) 명칭이 곧 질의 집합이다 — 코퍼스에 법령이 늘면 해석례도
따라 넓어진다. 행정규칙(admrul)은 질의하지 않는다(법제처 해석례는 법령 대상).

수집 규율은 lawrag/pipeline/collect.py 와 같다 — 멱등(파일 존재+sha 일치면 skip), 부분 실패
허용, 원문 보존(사례 XML 을 그대로 저장), 요청 규율은 common.HttpClient 소유.

저장 구조 (llm-wiki 의 raw 층 — 불변, 이후 단계는 읽기 전용):
    data/corpus/expc/cases/<일련번호>.xml    사례 원문
    data/corpus/expc/manifest.json          사례 대장 (관련 법령·질의 출처 포함)

관련 법령 판정은 lawrag/sources/expc.cited_laws — 본문의 「법령명」 낫표 인용
완전일치다. 안건명 부분일치 검색의 오탐('상법'→'군인 재해보상법')은 이 단계에서
laws=[] 로 남고, 색인(lawrag/pipeline/ingest_expc.py)이 걸러낸다. 원문은 그래도 보존한다 —
판정 기준이 바뀌면 재판정할 원본이 있어야 한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lawrag.sources.common import (
    CrawlAborted,
    FetchError,
    HttpClient,
    build_logger,
    detect_format,
    load_manifest,
    make_session,
    manifest_item,
    save_manifest,
    sha256_file,
    upsert_item,
)
from lawrag.sources.expc import ExpcClient, case_text, cited_laws, parse_case, plan_queries

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
EXPC_DIR = CORPUS_DIR / "expc"
CASES_DIR = EXPC_DIR / "cases"
LOG_DIR = REPO_ROOT / "var" / "logs"


def corpus_law_names() -> tuple[list[str], list[str]]:
    """(질의 명칭, 인용 판정 명칭). 질의는 법령만, 인용 판정은 법령·행정규칙 전부."""
    m = json.loads((CORPUS_DIR / "law" / "manifest.json").read_text("utf-8"))
    queries, citable = [], []
    for item in m["items"]:
        name = item.get("name", "").strip()
        if not name:
            continue
        citable.append(name)
        if item.get("kind") == "law":
            queries.append(name)
    return queries, citable


def item_intact(item: dict | None) -> bool:
    """사례 파일이 존재하고 sha 가 맞는가 — expc 대장은 항목당 파일 하나다."""
    if not item or not item.get("file"):
        return False
    f = REPO_ROOT / item["file"]
    return f.exists() and sha256_file(f) == item.get("sha256")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="법령해석례(expc) 수집기")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--query", action="append", default=[],
                    metavar="명칭", help="질의 임시 추가 (코퍼스 밖 확인용)")
    args = ap.parse_args(argv)

    logger = build_logger(LOG_DIR, "expc")
    client = HttpClient(make_session(), logger)
    api = ExpcClient(client)

    query_names, citable = corpus_law_names()
    queries = plan_queries(query_names + args.query)
    print(f"질의 {len(queries)}건 (법령 명칭 {len(query_names)}건에서 축약"
          f"{' + 추가 ' + str(len(args.query)) + '건' if args.query else ''})")

    manifest_path = EXPC_DIR / "manifest.json"
    manifest = load_manifest(manifest_path)
    manifest["source"] = "law.go.kr OPEN API (expc)"
    # 해석례는 구조화(원장 단계 모델) 경로 밖이다 — 색인·위키로 간다.
    # 이 선언을 보고 계보 원장(lawrag/core/lineage)이 이 코퍼스를 건너뛴다.
    manifest["phase_model"] = "수집→색인→위키 (lawrag/pipeline/ingest_expc.py · data/expc/wiki)"

    # 1) 목록 — 질의 합집합을 일련번호로 모은다 (사례 하나가 여러 질의에 걸린다)
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
            for s in sorted(found, key=lambda s: found[s]["case_no"]):
                mark = "  " if s in fresh else "= "   # '=' 는 이미 무결
                print(f"{mark}{found[s]['case_no']:8s} {found[s]['label'][:64]}")
            return 0

        # 2) 본문 — 사례 단위 멱등. 한 건 실패는 기록하고 계속 간다.
        CASES_DIR.mkdir(parents=True, exist_ok=True)
        for serial in sorted(found):
            row = found[serial]
            existing = manifest_item(manifest, serial)
            if not args.force and item_intact(existing):
                # 본문은 그대로 두고 질의 출처만 합친다 (질의 집합은 코퍼스 따라 변한다)
                existing["queries"] = sorted(set(existing.get("queries", []))
                                             | set(hit_queries[serial]))
                save_manifest(manifest_path, manifest)
                skipped += 1
                continue

            item = {"name": serial, "kind": "expc", "label": row["label"],
                    "case_no": row["case_no"], "replied": row["replied"],
                    "req_org": row["req_org"], "ans_org": row["ans_org"],
                    "queries": sorted(set(hit_queries[serial])),
                    "url": api.case_url(serial), "status": "error"}
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
            laws = cited_laws(case_text(case), citable)
            item.update({
                "file": str(path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(path), "size": path.stat().st_size,
                "actual_format": detect_format(path.read_bytes()[:256]),
                "decided": case["decided"], "laws": laws, "status": "ok",
            })
            upsert_item(manifest, item)
            save_manifest(manifest_path, manifest)   # 건 단위 저장 — 중단돼도 진행분 보존
            ok += 1
            if not laws:
                unrelated += 1
    except CrawlAborted as e:
        aborted = True
        print(f"\n!! 차단 감지 — 전체 중단: {e}", file=sys.stderr)
        print("!! 재시도 전략을 임의로 바꾸지 말 것. 시간을 두고 원인 확인 후 재실행.",
              file=sys.stderr)

    print(f"\n완료: ok={ok} skipped={skipped} failed={failed}"
          f" (인용 없음 {unrelated}건 — 색인이 거른다)"
          f" 요청수={client.request_count}{' (중단됨)' if aborted else ''}")
    return 2 if aborted else (1 if failed and not ok else 0)


if __name__ == "__main__":
    sys.exit(main())
