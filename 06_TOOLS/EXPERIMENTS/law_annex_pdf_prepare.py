"""ADR0352 research-only HWP HTML derivative; not original-layout certification."""
from pathlib import Path
import json
import hashlib
import time
from urllib.parse import urlparse, unquote
from weasyprint import HTML, CSS
from weasyprint.urls import URLFetcher
from weasyprint.text.fonts import FontConfiguration
import fitz

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'04_EXPERIMENTS/ADR/ADR-0352-law-annex-pdf-vlm/artifacts'
FONT=Path('/mnt/c/Windows/Fonts/malgun.ttf')
SOURCE=next((ROOT/'01_DATA/RAW/law/금융복합기업집단의 감독에 관한 법률/별표서식').glob('*.hwp'))

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

class LocalFetcher(URLFetcher):
    def fetch(self,url,headers=None):
        u=urlparse(url)
        p=Path(unquote(u.path)).resolve()
        if u.scheme!='file' or not (p.is_relative_to(OUT/'converted') or p==FONT):
            raise ValueError('Only converted local assets and exact Korean font allowed')
        return super().fetch(url,headers)

fetch=LocalFetcher(allowed_protocols={'file'},fail_on_errors=True)

if __name__=='__main__':
    dest=OUT/'annex-derived-v2.pdf'
    if dest.exists(): raise FileExistsError(dest)
    t=time.perf_counter()
    font_config=FontConfiguration()
    css=CSS(string=f'@font-face {{font-family: AuditKorean; src: url("{FONT.as_uri()}");}} '
                   '@page {size:A4; margin:0;} * {font-family: AuditKorean !important;}',url_fetcher=fetch,font_config=font_config)
    HTML(filename=str(OUT/'converted/index.xhtml'),url_fetcher=fetch).write_pdf(dest,stylesheets=[css],font_config=font_config)
    receipt={'source':str(SOURCE.relative_to(ROOT)),'source_sha256':sha(SOURCE),'pdf_sha256':sha(dest),
             'font_sha256':sha(FONT),'conversion':'pyhwp hwp5html -> WeasyPrint70.0; font substitution Malgun Gothic',
             'seconds_pdf_render':time.perf_counter()-t,'original_pagination_verified':False,
             'status':'derived_render_unverified','network_resource_loading':False}
    with fitz.open(dest) as d:
        receipt['pages']=len(d)
        for i,p in enumerate(d,1):
            p.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(OUT/f'v2-page-{i:03d}.png')
            lines=[{'line':n,'text':s} for n,s in enumerate(p.get_text().splitlines(),1)]
            (OUT/f'v2-page-{i:03d}.json').write_text(json.dumps(lines,ensure_ascii=False,indent=2))
            print('PAGE',i,'lines',len(lines),p.get_text()[:180])
    (OUT/'conversion-v2.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps(receipt,ensure_ascii=False))
