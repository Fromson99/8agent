#!/usr/bin/env python3
"""예시 내규 md → docx 변환.

내규 md의 관례를 그대로 스타일에 사상한다:
  '# '   → 문서 제목 (Title)
  '## '  → 장 (Heading 1)
  '### ' → 조 (Heading 2)
  그 외  → 본문 (항·호는 문단 그대로)

실행:  <repo>/.venv/bin/python md_to_docx.py [파일.md ...]
인자 없이 실행하면 스크립트 위치 기준으로 internal-rules/*.md 와 uploads/*.md 를 모두 변환한다.
"""
import sys
from pathlib import Path

from docx import Document
from docx.shared import Pt


def convert(md_path: Path) -> Path:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "맑은 고딕"
    style.font.size = Pt(10)

    for line in md_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            doc.add_heading(stripped[4:], level=2)
        elif stripped.startswith("## "):
            doc.add_heading(stripped[3:], level=1)
        elif stripped.startswith("# "):
            doc.add_heading(stripped[2:], level=0)
        elif stripped.startswith("- "):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        else:
            doc.add_paragraph(stripped)

    out = md_path.with_suffix(".docx")
    doc.save(out)
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1:
        targets = [Path(p) for p in sys.argv[1:]]
    else:
        base = Path(__file__).resolve().parent
        targets = sorted(base.glob("*.md")) + sorted((base.parent / "uploads").glob("*.md"))
    for t in targets:
        print(convert(t))
