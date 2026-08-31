from pathlib import Path
import sys

import pypdfium2 as pdfium
from PIL import Image, ImageDraw


pdf_path = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)

pdf = pdfium.PdfDocument(str(pdf_path))
thumbs = []
for idx in range(len(pdf)):
    page = pdf[idx]
    bitmap = page.render(scale=1.75)
    image = bitmap.to_pil().convert("RGB")
    page_path = out_dir / f"page-{idx + 1:03d}.png"
    image.save(page_path, quality=95)

    thumb = image.copy()
    thumb.thumbnail((420, 594))
    canvas = Image.new("RGB", (440, 630), "white")
    x = (440 - thumb.width) // 2
    canvas.paste(thumb, (x, 10))
    ImageDraw.Draw(canvas).text((12, 606), f"Page {idx + 1}", fill="black")
    thumbs.append(canvas)

for start in range(0, len(thumbs), 6):
    group = thumbs[start:start + 6]
    sheet = Image.new("RGB", (1320, 1260), "#d9dde3")
    for offset, thumb in enumerate(group):
        x = (offset % 3) * 440
        y = (offset // 3) * 630
        sheet.paste(thumb, (x, y))
    sheet.save(out_dir / f"contact-{start + 1:03d}-{start + len(group):03d}.png", quality=92)

print(f"pages={len(pdf)} contacts={(len(thumbs) + 5) // 6}")
