"""수집된 조문 HTML → 구조 검수 스토어 등록 — core.ingest 의 CLI 낯.

    python ingest_rulehtml.py                    # corpus/krx manifest 의 조문 HTML 전부
    python ingest_rulehtml.py --source krx --targets "유가증권시장 상장규정"
    python ingest_rulehtml.py "corpus/krx/…/… 조문.html" --name "유가증권시장 상장규정"

실제 이관은 core/ingest.py(ingest_rulehtml_bytes)가 한다 — ingest_lawxml.py 와
같은 구도다. 여기 남은 것은 CLI 인자와 manifest 를 대상 목록으로 펴는 일뿐.

구조는 조문 HTML 의 클래스에서 결정적으로 옮긴다(core/structure/rulehtml.py).
같은 HTML 은 같은 doc_id(sha256 앞 16자리)가 되어 재실행이 멱등이고, manifest
의 body_html_sha256 과 결정적으로 이어진다. KOFIA 는 추출기가 등록되면
--source kofia 로 같은 문을 탄다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from core.ingest import ingest_rulehtml_bytes  # noqa: E402


def _store(arg: str | None) -> Path:
    import os
    return Path(arg or os.environ.get("STRUCTURE_STORE") or REPO_ROOT / "data" / "structure")


def manifest_targets(source: str) -> list[tuple[Path, str, dict]]:
    m = json.loads((REPO_ROOT / "corpus" / source / "manifest.json").read_text("utf-8"))
    out = []
    for item in m.get("items", []):
        body = item.get("body_html_file")
        if not body:
            continue
        extra = {"kind": item.get("kind"), "enforce": item.get("enforce"),
                 "revised": item.get("revised"), "dept": item.get("dept")}
        out.append((REPO_ROOT / body, item["name"],
                    {k: v for k, v in extra.items() if v}))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="조문 HTML → 구조 스토어")
    ap.add_argument("paths", nargs="*", help="조문 HTML (생략하면 manifest 전부)")
    ap.add_argument("--source", default="krx", help="corpus 출처 = 추출기 site (기본 krx)")
    ap.add_argument("--name", help="문서 이름 (paths 가 1건일 때만)")
    ap.add_argument("--targets", help="쉼표 구분 문서 이름 필터")
    ap.add_argument("--store", help="스토어 경로 (기본: $STRUCTURE_STORE 또는 data/structure)")
    ap.add_argument("--folder", default="상장규정", help="묶어 둘 폴더 라벨")
    args = ap.parse_args(argv)

    store = _store(args.store)
    if args.paths:
        targets = [(Path(p), args.name if (args.name and len(args.paths) == 1)
                    else Path(p).stem, {}) for p in args.paths]
    else:
        targets = manifest_targets(args.source)
    if args.targets:
        wanted = {t.strip() for t in args.targets.split(",")}
        targets = [t for t in targets if t[1] in wanted]

    failed = 0
    for path, name, extra in targets:
        try:
            r = ingest_rulehtml_bytes(path.read_bytes(), name, store, args.folder,
                                      extra_meta=extra, site=args.source)
        except Exception as e:
            failed += 1
            print(f"[{name}] 실패: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        u = " ".join(f"{k}{v}" for k, v in r["units"].items())
        print(f"[{name}] doc_id={r['doc_id']} pages={r['pages']} "
              f"nodes={r['nodes']} blocks={r['blocks']} ({u})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
