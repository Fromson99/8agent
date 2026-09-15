#!/usr/bin/env python3
"""ADR0350 read-only annex audit or Office-rendered VLM input preparation. No API calls."""
import argparse
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'02_BACKEND'))
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0350/visual'


def load_candidate():
    manifest=json.loads((CAND/'candidate.json').read_text())
    rev=next(r for r in manifest['revisions'] if r['revision_id']=='rev-001')
    if rev['revision_sha256']!='d39fe048505ebb811479947676a435bc4f537edace7a2423f792d20867938f45':
        raise ValueError('unexpected candidate revision')
    for row in rev['files']:
        if hashlib.sha256((ROOT/row['frozen_path']).read_bytes()).hexdigest()!=row['snapshot_sha256']:
            raise ValueError('candidate drift')
    path=CAND/'revisions/rev-001/snapshot/02_BACKEND/lawrag/core/document_visual.py'
    spec=importlib.util.spec_from_file_location('adr0350_visual',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def packet_from_render(receipt, pages):
    if receipt['status']!='rendered_unverified': raise ValueError('render unavailable')
    import fitz
    from lawrag.core import router
    from lawrag.core.parse_adapter import Element,ParseResult
    path=ROOT/'06_TOOLS/EXPERIMENTS/structure_recipe_probe.py'
    expected=json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-0348-structure-recipe-prototype/실험/manifest.json').read_text())['design']['code_isolation']['candidates'][0]['runner_sha256']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected: raise ValueError('parent runner drift')
    spec=importlib.util.spec_from_file_location('adr0348_parent_runner',path)
    parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
    recipe=parent.load_candidate()
    if not 1<=len(pages)<=4 or len(set(pages))!=len(pages): raise ValueError('select one to four unique pages')
    pdf_path=Path(receipt['pdf_path'])
    if load_candidate().sha(pdf_path)!=receipt['pdf_sha256']: raise ValueError('PDF changed')
    elements=[]; images=[]
    import base64
    with fitz.open(pdf_path) as pdf:
        if any(p<1 or p>pdf.page_count for p in pages): raise ValueError('page out of bounds')
        for n,page in enumerate(pdf,1):
            for line in page.get_text().splitlines():
                elements.append(Element(index=len(elements),type='text',text=line,page=n))
            # Retain empty/image-only pages as coordinates; no invented OCR text.
            if not any(e.page==n for e in elements):
                elements.append(Element(index=len(elements),type='text',text='',page=n))
        for page in pages:
            png=pdf[page-1].get_pixmap(matrix=fitz.Matrix(1,1)).tobytes('png')
            images.append(dict(page=page,source_sha256=receipt['pdf_sha256'],render_kind='original_page',
                               data_uri='data:image/png;base64,'+base64.b64encode(png).decode()))
    parsed=ParseResult(path=str(pdf_path),doc_id=receipt['pdf_sha256'][:16],parser='rendered-pdf-text',born_digital=False,elements=elements)
    catalog=recipe.marker_catalog([router.assets(r)[1] for r in router.load().routes])
    packet=recipe.request_packet(parsed,receipt['pdf_sha256'],catalog,images=images,supports_images=True)
    provenance={k:receipt[k] for k in ('source_path','source_sha256','pdf_sha256','render_kind','layout_fidelity','original_pagination_preserved')}
    packet['conversion_provenance']=provenance
    user=json.loads(packet['user']);user['conversion_provenance']=provenance
    packet['user']=json.dumps(user,ensure_ascii=False)
    packet['system']+=' Images are pages of a rendered PDF, not guaranteed original Office pagination. Never infer absent content from rendering gaps.'
    return packet


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('audit');a.add_argument('--root',type=Path,default=ROOT/'01_DATA/RAW/law');a.add_argument('--output',type=Path,required=True)
    r=sub.add_parser('render');r.add_argument('--source',type=Path,required=True);r.add_argument('--output',type=Path,required=True)
    r.add_argument('--page',action='append',type=int);r.add_argument('--timeout',type=int,default=120)
    args=p.parse_args();module=load_candidate()
    if args.mode=='audit':
        report=module.audit_annexes(args.root)
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/'annex-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        (args.output/'annex-audit.html').write_text('<meta charset="utf-8"><h1>별첨 가용성 감사 — 처리 성공 판정 아님</h1><pre>'+html.escape(json.dumps(report,ensure_ascii=False,indent=2))+'</pre>')
        print(json.dumps(report['summary'],ensure_ascii=False));return 0
    receipt=module.office_pdf(args.source,args.output,timeout=args.timeout)
    if receipt['status']=='rendered_unverified':
        packet=packet_from_render(receipt,args.page or [1])
        (args.output/'vlm-request.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False));return 0 if receipt['status']=='rendered_unverified' else 2


if __name__=='__main__':
    raise SystemExit(main())
