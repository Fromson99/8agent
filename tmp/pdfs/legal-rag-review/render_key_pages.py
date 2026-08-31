from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageDraw


root = Path(__file__).resolve().parent
pages = {
    "01_lbox_open.pdf": 6,
    "02_legalgraphrag.pdf": 7,
    "03_rar_agent.pdf": 8,
    "04_kbl.pdf": 9,
    "05_legalsearchlm.pdf": 8,
    "06_calrk_bench.pdf": 5,
    "07_legalbench_rag.pdf": 6,
    "08_reasoning_legal_retrieval.pdf": 10,
    "09_claimrag_law.pdf": 6,
}

thumbs = []
for filename, page_index in pages.items():
    pdf = pdfium.PdfDocument(root / filename)
    page = pdf[page_index]
    image = page.render(scale=1.6).to_pil().convert("RGB")
    out = root / f"{Path(filename).stem}_key.png"
    image.save(out)
    image.thumbnail((600, 800))
    canvas = Image.new("RGB", (640, 860), "white")
    canvas.paste(image, ((640 - image.width) // 2, 40))
    ImageDraw.Draw(canvas).text((20, 10), filename, fill="black")
    thumbs.append(canvas)

sheet = Image.new("RGB", (640 * 3, 860 * 3), "#dddddd")
for idx, thumb in enumerate(thumbs):
    sheet.paste(ImageOps.expand(thumb, border=2, fill="black"), ((idx % 3) * 640, (idx // 3) * 860))
sheet.save(root / "key_pages_contact_sheet.png")
