"""HWPX(OWPML zip) → markdown 사이드카 — 표를 md 표로 살린다.

    python -m core.hwpx_md corpus/law            # 디렉터리 아래 모든 hwpx → X.hwpx.md
    python -m core.hwpx_md path/to/file.hwpx     # 한 파일만
    python -m core.hwpx_md corpus/law --force

convert.py 는 hwp5(ole) 전용이고 hwpx 는 FORMAT 으로 보고만 한다(계약 §8-5).
law.go.kr 별표서식의 3할이 hwpx 라(실측 53/176, 표 있는 파일 29) 이 모듈이
그 나머지다. 사이드카 규약은 convert.py 와 동일: 원본 옆 `<이름>.md`,
첫머리 `# key: value` 출처 주석 (corpus_build 가 읽는 형태).

OWPML 실측 (corpus/law 별표):
- Contents/section*.xml 의 hs:sec 아래 hp:p 가 문단, 문단의 hp:run 아래 hp:t 가 글
- 표는 hp:run 안의 hp:tbl → hp:tr → hp:tc. 셀 위치는 hp:cellAddr(colAddr,rowAddr)
  + hp:cellSpan(colSpan,rowSpan) — 병합 셀은 앵커 칸에만 내용을 두고 덮인 칸은
  빈 칸으로 남긴다 (convert.py 의 hwp5 경로가 못 하는 정렬 보존이 여기선 된다)
- 셀 내용은 hp:subList 의 hp:p 들 — md 셀엔 개행이 없으므로 <br> 로 잇는다
- 셀 안에 또 표가 올 수 있다 — 안쪽 표는 ' / ' 로 이어 평문화한다 (드묾)
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def is_hwpx(path: Path) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return any(n.startswith("Contents/section") for n in names)


def _cell_text(tc: ET.Element) -> str:
    parts = []
    sub = tc.find(_q(HP, "subList"))
    for p in (sub.findall(_q(HP, "p")) if sub is not None else []):
        text, tables = _para_parts(p)
        if text:
            parts.append(text)
        for tbl in tables:                      # 셀 속의 표 — 평문화
            flat = [" ".join(filter(None, row)) for row in _table_grid(tbl)]
            parts.append(" / ".join(filter(None, flat)))
    return "<br>".join(parts).replace("|", "\\|")


def _table_grid(tbl: ET.Element) -> list[list[str]]:
    cells = []
    n_rows = n_cols = 0
    for tr in tbl.iter(_q(HP, "tr")):
        for tc in tr.findall(_q(HP, "tc")):
            addr = tc.find(_q(HP, "cellAddr"))
            span = tc.find(_q(HP, "cellSpan"))
            if addr is None:
                continue
            r, c = int(addr.get("rowAddr", 0)), int(addr.get("colAddr", 0))
            rs = int(span.get("rowSpan", 1)) if span is not None else 1
            cs = int(span.get("colSpan", 1)) if span is not None else 1
            cells.append((r, c, _cell_text(tc)))
            n_rows, n_cols = max(n_rows, r + rs), max(n_cols, c + cs)
    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for r, c, text in cells:
        if r < n_rows and c < n_cols:
            grid[r][c] = text
    return grid


def _table_md(tbl: ET.Element) -> list[str]:
    grid = _table_grid(tbl)
    if not grid:
        return []
    lines = ["| " + " | ".join(row) + " |" for row in grid]
    lines.insert(1, "|" + "---|" * len(grid[0]))
    return lines


def _para_parts(p: ET.Element) -> tuple[str, list[ET.Element]]:
    """문단 → (자기 글, 담긴 표들). 표 안의 글을 문단 글로 새면 안 된다."""
    texts: list[str] = []
    tables: list[ET.Element] = []
    for run in p.findall(_q(HP, "run")):
        for child in run:
            if child.tag == _q(HP, "t"):
                texts.append("".join(child.itertext()))
            elif child.tag == _q(HP, "tbl"):
                tables.append(child)
    return "".join(texts), tables


def hwpx_to_md(path: Path) -> str:
    """본문 → markdown. 문단은 줄, 표는 md 표."""
    out: list[str] = []
    with zipfile.ZipFile(path) as z:
        sections = sorted(n for n in z.namelist() if n.startswith("Contents/section"))
        for name in sections:
            root = ET.fromstring(z.read(name))
            # 본문 흐름의 문단은 hs:sec 의 **직계 자식**이다. 셀 문단은 표 아래
            # (run>tbl>tc>subList)에 갇혀 있어 여기 안 걸린다 — 표 쪽에서 처리한다.
            for p in root.findall(_q(HP, "p")):
                text, tables = _para_parts(p)
                if text.strip():
                    out.append(text.rstrip())
                for tbl in tables:
                    out.extend(_table_md(tbl))
                    out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------- 사이드카 CLI

def provenance_header(src: Path, info: dict | None) -> str:
    lines = []
    if info:
        for key in ("title", "regulation", "role", "source", "collected",
                    "enforced", "revision_date", "sha256"):
            if info.get(key):
                lines.append(f"# {key}: {info[key]}")
    else:
        lines.append(f"# title: {src.stem}")
    lines.append("# converted: hwpx(zip) → md, core/hwpx_md.py")
    return "\n".join(lines) + "\n\n"


def convert_file(src: Path, info: dict | None, force: bool) -> str:
    out = src.with_name(src.name + ".md")
    if not force and out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return "SKIP"
    if not is_hwpx(src):
        return "FORMAT"
    md = hwpx_to_md(src)
    out.write_text(provenance_header(src, info) + md, encoding="utf-8")
    return "OK"


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(REPO_ROOT))
    import convert as convert_mod      # manifest 출처 색인 재사용 (convert.py 규약)

    ap = argparse.ArgumentParser(description="hwpx → markdown 사이드카")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    paths = [Path(p).resolve() for p in args.paths]
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(x for x in p.rglob("*") if x.is_file()
                                and x.suffix.lower() in (".hwpx", ".hwp")
                                and is_hwpx(x)))
        else:
            files.append(p)
    index = convert_mod.manifest_index(paths)

    counts: dict[str, int] = {}
    for f in files:
        status = convert_file(f, index.get(f), args.force)
        counts[status] = counts.get(status, 0) + 1
        if status == "OK":
            print(f"OK   {f.name}")
    print(f"\n변환 {counts.get('OK', 0)} · skip {counts.get('SKIP', 0)}"
          f" · 형식 불일치 {counts.get('FORMAT', 0)} (총 {len(files)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
