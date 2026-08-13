"""수집된 law.go.kr 본문 XML → 구조 검수 스토어 등록 — core.ingest 의 CLI 낯.

    python ingest_lawxml.py                      # corpus/law manifest 의 본문 전부
    python ingest_lawxml.py "corpus/law/금융투자업규정/금융투자업규정 본문.xml"
    python ingest_lawxml.py --store data/structure --folder 법령

실제 이관은 core/ingest.py(ingest_lawxml_bytes)가 한다 — 업로드 API 와 같은
문이다(코드단 일원화, docs/LINEAGE.md). 여기 남은 것은 CLI 인자와 corpus/law
manifest 를 대상 목록으로 펴는 일뿐이다.

구조는 XML 태그에서 결정적으로 옮긴다(core/structure/lawxml.py). 좌표·페이지는
합성 PDF 로 만들므로 검수 화면(트리·오버레이·페이지 렌더)이 그대로 동작한다.
같은 XML 은 같은 doc_id(sha256 앞 16자리)가 되어 재실행이 멱등이다.

원본 XML 은 문서 디렉토리에 source.xml 로 함께 남는다 — 재해석은 PDF 추론이
아니라 이 파일에서 다시 옮기는 것이 맞다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from core.ingest import ingest_lawxml_bytes as ingest_bytes  # noqa: E402,F401 — 하위 호환 재수출


def _store(arg: str | None) -> Path:
    import os
    return Path(arg or os.environ.get("STRUCTURE_STORE") or REPO_ROOT / "data" / "structure")


def ingest(xml_path: Path, name: str, store: Path, folder: str,
           extra_meta: dict | None = None, manifest_item: dict | None = None) -> dict:
    return ingest_bytes(xml_path.read_bytes(), name, store, folder,
                        extra_meta, manifest_item)


def manifest_targets() -> list[tuple[Path, str, dict, dict]]:
    m = json.loads((REPO_ROOT / "corpus" / "law" / "manifest.json").read_text("utf-8"))
    out = []
    for item in m["items"]:
        body = item.get("body_file")
        if not body:
            # 초기 수집분은 .xml 본문이 attachments 에 role=body 로 남아 있다
            body = next((a["file"] for a in item.get("attachments", [])
                         if a.get("role") == "body"
                         and str(a.get("file", "")).endswith(".xml")), None)
        if not body:
            continue
        enforce = item.get("enforce", "")
        extra = {"kind": item.get("kind"), "enforce": enforce,
                 "revised": item.get("revised"), "promul_no": item.get("promul_no"),
                 "dept": item.get("dept"), "law_serial": item.get("doc_no")}
        out.append((REPO_ROOT / body, item["name"], extra, item))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="law.go.kr 본문 XML → 구조 스토어")
    ap.add_argument("paths", nargs="*", help="본문 XML (생략하면 corpus/law manifest 전부)")
    ap.add_argument("--name", help="문서 이름 (paths 가 1건일 때만)")
    ap.add_argument("--store", help="스토어 경로 (기본: $STRUCTURE_STORE 또는 data/structure)")
    ap.add_argument("--folder", default="법령·규정", help="묶어 둘 폴더 라벨")
    args = ap.parse_args(argv)

    store = _store(args.store)
    if args.paths:
        targets = [(Path(p), args.name if (args.name and len(args.paths) == 1)
                    else Path(p).stem, {}, None) for p in args.paths]
    else:
        targets = manifest_targets()

    failed = 0
    for xml_path, name, extra, item in targets:
        try:
            r = ingest(xml_path, name, store, args.folder, extra, item)
        except Exception as e:
            failed += 1
            print(f"[{name}] 실패: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        u = " ".join(f"{k}{v}" for k, v in r["units"].items())
        print(f"[{name}] doc_id={r['doc_id']} pages={r['pages']} "
              f"nodes={r['nodes']} blocks={r['blocks']} "
              f"별표md {r['annex_md']}/{r['annex_have']} ({u})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
