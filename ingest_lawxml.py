"""수집된 law.go.kr 본문 XML → 구조 검수 스토어 등록 (PDF 업로드와 같은 산출 형식).

    python ingest_lawxml.py                      # corpus/law manifest 의 본문 4건 전부
    python ingest_lawxml.py "corpus/law/금융투자업규정/금융투자업규정 본문.xml"
    python ingest_lawxml.py --store data/structure --folder 법령

구조는 XML 태그에서 결정적으로 옮긴다(core/structure/lawxml.py). 좌표·페이지는
합성 PDF 로 만들므로 검수 화면(트리·오버레이·페이지 렌더)이 그대로 동작한다.
같은 XML 은 같은 doc_id(sha256 앞 16자리)가 되어 재실행이 멱등이다.

원본 XML 은 문서 디렉토리에 source.xml 로 함께 남긴다 — 재해석은 PDF 추론이
아니라 이 파일에서 다시 옮기는 것이 맞다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))


def _store(arg: str | None) -> Path:
    import os
    return Path(arg or os.environ.get("STRUCTURE_STORE") or REPO_ROOT / "data" / "structure")


def _register_folder(store: Path, name: str) -> None:
    p = store / "folders.json"
    try:
        names = json.loads(p.read_text(encoding="utf-8")).get("folders", [])
    except Exception:
        names = []
    if name not in names:
        p.write_text(json.dumps({"folders": sorted({*names, name})},
                                ensure_ascii=False, indent=1), encoding="utf-8")


def annex_md_map(item: dict | None) -> dict[str, str]:
    """manifest 항목의 별표서식 첨부 → {"별표 14의1": 사이드카 md 본문}.

    사이드카(.md)는 convert.py(hwp5)·core/hwpx_md.py(hwpx) 가 만든다.
    없는 별표는 XML 별표내용으로 남는다 — 연결은 있는 것만, 조용한 누락 없이
    호출부가 개수를 보고한다.
    """
    import re
    if not item:
        return {}
    pat = re.compile(r"^\[(별표|별지|별첨|서식|부록)\s*(\d+(?:의\d+)?)\]")
    out: dict[str, str] = {}
    for a in item.get("attachments", []):
        m = pat.match(a.get("title") or "")
        if not m or not a.get("file"):
            continue
        sidecar = REPO_ROOT / (a["file"] + ".md")
        if sidecar.exists():
            out[f"{m.group(1)} {m.group(2)}"] = sidecar.read_text(encoding="utf-8")
    return out


def find_manifest_item(raw: bytes) -> dict | None:
    """업로드된 XML 이 corpus/law 수집분이면 그 manifest 항목을 찾는다.

    화면 업로드는 어느 규정인지 스스로 말하지 않는다 — 본문 sha256 이 수집분과
    일치하면 같은 문서다 (개정판이면 해시가 달라 안 잡히고, 별표 md 연결 없이
    XML 별표내용으로 들어간다 — 그때는 collect→convert 후 재인제스트가 맞다).
    """
    mp = REPO_ROOT / "corpus" / "law" / "manifest.json"
    if not mp.exists():
        return None
    sha = hashlib.sha256(raw).hexdigest()
    for item in json.loads(mp.read_text("utf-8"))["items"]:
        shas = {item.get("body_sha256")}
        shas.update(a.get("sha256") for a in item.get("attachments", [])
                    if a.get("role") == "body")
        if sha in shas:
            return item
    return None


def ingest_bytes(raw: bytes, name: str, store: Path, folder: str = "",
                 extra_meta: dict | None = None,
                 manifest_item: dict | None = None) -> dict:
    """본문 XML 바이트 → 스토어 등록. CLI 와 업로드 API 가 공유하는 유일한 경로."""
    from core.structure import lawxml, viewer

    doc_id = hashlib.sha256(raw).hexdigest()[:16]
    if manifest_item is None:
        manifest_item = find_manifest_item(raw)
    annex_md = annex_md_map(manifest_item)

    d = store / doc_id
    prev = {}
    if (d / "meta.json").exists():      # 재업로드 — 사람이 고친 이름·폴더를 지킨다
        try:
            prev = json.loads((d / "meta.json").read_text("utf-8"))
        except Exception:
            prev = {}
    name = prev.get("name") or name

    result, blocks, pdf_bytes, info = lawxml.build(raw.decode("utf-8"), name,
                                                   annex_md=annex_md)

    d.mkdir(parents=True, exist_ok=True)
    (d / "source.xml").write_bytes(raw)
    pdf = d / "source.pdf"
    pdf.write_bytes(pdf_bytes)

    data = viewer.payload(result, blocks, pdf_path=pdf)
    data["doc"] = name
    data["parser_warnings"] = []
    (d / "result.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    meta = {
        "doc_id": doc_id, "name": name, "bytes": len(raw),
        "pages": len(data["pages"]), "score": data["fitness"]["score"],
        "passed": data["fitness"]["passed"], "tier": data["fitness"]["tier"],
        "fingerprint": data.get("fingerprint", {}).get("key"),
        "used_llm": False, "source_kind": "lawxml",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **(extra_meta or {}),
    }
    if folder:
        meta["folder"] = folder
    elif prev.get("folder"):
        meta["folder"] = prev["folder"]
    if meta.get("folder"):
        _register_folder(store, meta["folder"])
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    # 컨테이너(다른 uid)가 페이지 캐시를 이 디렉토리에 쓴다 — 쓰기를 열어 둔다.
    # 상대편 uid 소유 항목(pages/ 캐시)은 chmod 가 안 되므로 조용히 건너뛴다.
    import os
    for p in (d, *d.iterdir()):
        try:
            os.chmod(p, 0o666 if p.is_file() else 0o777)
        except PermissionError:
            pass

    units = data["stats"]["units"]
    return {"doc_id": doc_id, "name": name, "pages": meta["pages"],
            "nodes": len(data["nodes"]), "blocks": len(data["blocks"]),
            "units": units, "annex_md": data["stats"].get("annex_md_used", 0),
            "annex_have": len(annex_md), "meta": meta}


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
