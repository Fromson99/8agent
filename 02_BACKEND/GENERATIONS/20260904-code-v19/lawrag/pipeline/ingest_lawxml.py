"""수집된 law.go.kr 본문 XML → 구조 검수 스토어 등록 — core.ingest 의 CLI 낯.

    python -m lawrag.pipeline.ingest_lawxml                      # 01_DATA/INBOX/AUTHORING/corpus/law manifest 의 본문 전부
    python -m lawrag.pipeline.ingest_lawxml "01_DATA/INBOX/AUTHORING/corpus/law/금융투자업규정/금융투자업규정 본문.xml"
    python -m lawrag.pipeline.ingest_lawxml --store 01_DATA/INBOX/AUTHORING/structure --folder 법령

실제 이관은 lawrag/core/ingest.py(ingest_lawxml_bytes)가 한다 — 업로드 API 와 같은
문이다(코드단 일원화, docs/LINEAGE.md). 여기 남은 것은 CLI 인자와 01_DATA/INBOX/AUTHORING/corpus/law
manifest 를 대상 목록으로 펴는 일뿐이다.

구조는 XML 태그에서 결정적으로 옮긴다(lawrag/core/structure/lawxml.py). 좌표·페이지는
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

from lawrag.platform.paths import data_path, persisted_data_path, repository_root

REPO_ROOT = repository_root()
sys.path.insert(0, str(REPO_ROOT))

from lawrag.core.ingest import ingest_lawxml_bytes as ingest_bytes  # noqa: E402,F401 — 하위 호환 재수출


def _store(arg: str | None) -> Path:
    import os
    return Path(arg or os.environ.get("STRUCTURE_STORE") or data_path("INBOX", "AUTHORING", "structure"))


def ingest(xml_path: Path, name: str, store: Path, folder: str,
           extra_meta: dict | None = None, manifest_item: dict | None = None) -> dict:
    return ingest_bytes(xml_path.read_bytes(), name, store, folder,
                        extra_meta, manifest_item)


def manifest_targets() -> list[tuple[Path, str, dict, dict]]:
    m = json.loads(data_path("INBOX", "AUTHORING", "corpus", "law", "manifest.json").read_text("utf-8"))
    from lawrag.core.legal_generation import build_contract
    contract = build_contract(m)
    canonical = set(contract["canonical_document_ids"])
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
        sha = str(item.get("body_sha256") or "")
        extra = {"kind": item.get("kind"), "enforce": enforce,
                 "revised": item.get("revised"), "promul_no": item.get("promul_no"),
                 "dept": item.get("dept"), "law_serial": item.get("doc_no"),
                 "law_id": item.get("law_id"), "series": item.get("name"),
                 "status": "현행" if sha[:16] in canonical else "구판",
                 "canonical": sha[:16] in canonical,
                 "authority_generation": contract["generation_id"],
                 "authority_as_of": contract["as_of"],
                 "authority_mode": item.get("authority_mode", "manifest-canonical")}
        out.append((persisted_data_path(body), item["name"], extra, item))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="law.go.kr 본문 XML → 구조 스토어")
    ap.add_argument("paths", nargs="*", help="본문 XML (생략하면 01_DATA/INBOX/AUTHORING/corpus/law manifest 전부)")
    ap.add_argument("--name", help="문서 이름 (paths 가 1건일 때만)")
    ap.add_argument("--store", help="스토어 경로 (기본: $STRUCTURE_STORE 또는 01_DATA/INBOX/AUTHORING/structure)")
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
    if not failed and not args.paths:
        from lawrag.core.legal_generation import build_contract, synchronize_structure
        manifest = json.loads(data_path("INBOX", "AUTHORING", "corpus", "law", "manifest.json").read_text("utf-8"))
        sync = synchronize_structure(store, build_contract(manifest))
        print(f"canonical generation={sync['generation_id']} current={sync['current']} old={sync['old']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
