"""Local DOCX parsing and existing synthetic pagination; no external calls."""
from pathlib import Path
from dataclasses import asdict
import copy,hashlib,json,re,shutil,sys,time
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0439-internal-mock-v33-gemini';ART=ADR/'artifacts';DATA=ART/'dataset'
SOURCE=ROOT/'01_DATA/RAW/internal/.staging/internal-rules-20260916-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 if (DATA/'cases.json').exists():raise RuntimeError('Dataset exists; do not overwrite')
 DATA.mkdir(exist_ok=True);manifest=json.loads((SOURCE/'package.mock.json').read_text());docs=json.loads((SOURCE/'mock/documents.json').read_text())['documents']
 selected=[SOURCE/f'mock/{d["document_id"]}.docx' for d in docs]
 write(ART/'export-authorization.json',{'schema_version':'scoped-user-export-authorization-v1','authorized_by':'user','authorization_text':'외부 반출해도됨 gemini로 실험해봐','session_id':'01a0a8dd-9081-7ce2-b988-459e7b9e2a0d','source_package':str((SOURCE/'package.mock.json').relative_to(ROOT)),'source_package_sha256':sha(SOURCE/'package.mock.json'),'original_export_policy_preserved':manifest['export_policy'],'scope':'Only five synthetic mock documents and their locally derived text/images for this experiment; excludes source photos and golden questions','destination':'https://generativelanguage.googleapis.com/v1beta','model':'gemini-3.1-flash-lite','documents':[{'id':p.stem,'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in selected]})
 sys.path.insert(0,str(ROOT/'02_BACKEND'));import lawrag.core
 cp=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0439/v33/candidate.json';cm=json.loads(cp.read_text());rev=cm['revisions'][-1]
 core=next(ROOT/r['frozen_path'] for r in rev['files'] if r['frozen_path'].endswith('/core/parse_adapter.py')).parent
 lawrag.core.__path__.insert(0,str(core));from lawrag.core import parse_adapter
 from lawrag.core.structure import synthpdf
 from lawrag.core.structure.model import Block
 from docx import Document
 import fitz
 cases=[];gold={};beg=time.monotonic()
 for info,src in zip(docs,selected):
  cid=src.stem;dest=DATA/(cid+'.docx');shutil.copyfile(src,dest);expected=next(x['sha256'] for x in manifest['artifacts'] if x['path']=='mock/'+src.name);assert sha(dest)==expected
  shutil.copyfile(src.with_suffix('.md'),DATA/(cid+'.md'))
  start=time.monotonic();parsed=parse_adapter.parse_docx(dest);pdf=DATA/(cid+'.pdf');pdf.write_bytes(synthpdf.paginate(parsed.elements));blocks=Block.from_elements(parsed.elements)
  write(DATA/(cid+'.parse.json'),parse_adapter.result_to_dump(parsed));bf=DATA/(cid+'.blocks.json');write(bf,[asdict(b) for b in blocks])
  expected_parents={};article=None;article_count=0;circled_count=0
  for b in blocks:
   if b.kind!='text':continue
   if re.match(r'^제\d+조(?:의\d+)?\s*[（(]',b.text):
    expected_parents[str(b.idx)]=None;article=b.idx;article_count+=1
   elif re.match(r'^[①-⑳]',b.text) and article is not None:
    expected_parents[str(b.idx)]=article;circled_count+=1
  independent_articles=re.findall(r'^## (제\d+조[^\n]*)',src.with_suffix('.md').read_text(),re.M);assert len(independent_articles)==info['article_count']==article_count,(cid,article_count)
  independent_circled=re.findall(r'^[①-⑳]',src.with_suffix('.md').read_text(),re.M);assert len(independent_circled)==circled_count
  d=Document(dest);sourcecells=sorted(c.text.strip() for t in d.tables for row in t.rows for c in row.cells);parsedcells=sorted(c.text.strip() for e in parsed.elements if e.table for c in e.table.cells)
  with fitz.open(pdf) as f:pages=len(f)
  cases.append({'case_id':cid,'title':info['title'],'docx':str(dest.relative_to(ROOT)),'docx_sha256':sha(dest),'pdf':str(pdf.relative_to(ROOT)),'pdf_sha256':sha(pdf),'blocks':str(bf.relative_to(ROOT)),'hints':{},'pages':pages,'block_count':len(blocks),'text_chars':sum(len(b.text) for b in blocks),'article_count':article_count,'circled_count':circled_count,'tables':len(d.tables),'parsed_tables':sum(e.table is not None for e in parsed.elements),'table_cell_texts_match':sourcecells==parsedcells,'parse_layout_seconds':round(time.monotonic()-start,3),'parser':parsed.parser,'layout':'existing synthpdf, not original Word pagination'})
  gold[cid]={'parents_by_block':expected_parents,'scope':'Article roots and circled paragraphs only, nearest tracked ancestor; authored MD counts crosschecked before model calls; not full table/hierarchy gold'}
  print(json.dumps(cases[-1],ensure_ascii=False),flush=True)
 write(DATA/'cases.json',cases);write(DATA/'gold.json',gold);write(ART/'preparation.json',{'seconds':round(time.monotonic()-beg,3),'documents':len(cases),'production_code_modified':False,'source_manifest_sha256':sha(SOURCE/'package.mock.json'),'warning':'DOCX direct ingest does not invoke this PDF VLM branch. Research explicitly invokes existing revise_pdf on local synthesized pages; no GENOS preprocessor test.'})
if __name__=='__main__':main()
