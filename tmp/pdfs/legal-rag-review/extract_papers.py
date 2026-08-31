from pathlib import Path

from pypdf import PdfReader


root = Path(__file__).resolve().parent
for pdf_path in sorted(root.glob("*.pdf")):
    reader = PdfReader(pdf_path)
    text = "\n\n".join(page.extract_text() or "" for page in reader.pages).replace("\x00", "")
    pdf_path.with_suffix(".txt").write_text(text, encoding="utf-8")
    print(f"{pdf_path.name}\tpages={len(reader.pages)}\tchars={len(text)}")
