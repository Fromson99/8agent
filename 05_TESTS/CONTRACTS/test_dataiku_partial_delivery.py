"""Actual sealed R2 worker -> mock HTTP Docling -> structure/index/result ZIP."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import zipfile

import fitz
import pytest
from docling_core.types.doc import (DoclingDocument, DocItemLabel, Size,
                                    ProvenanceItem, BoundingBox, TableCell, TableData)
from test_dataiku_pipeline_delivery import support, selection, exporter, t

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_partial_20261028_r6'


@pytest.mark.parametrize('scenario',['chunks','docling','complete','invalid_chunks','http_error'])
def test_partial_worker_remote_pdf_to_return_zip(tmp_path,term_glossary,scenario):
    with zipfile.ZipFile(DELIVERY/'GENOS_DATAIKU_COMPUTE_20261028_R6.zip') as z:z.extractall(tmp_path)
    service=tmp_path/'GENOS_DATAIKU_COMPUTE_20261028_R6'
    dev=tmp_path/'dev';support(dev,term_glossary)
    source=dev/'01_DATA/RAW/internal/test_team/모의규정(20250101).pdf'
    source.parent.mkdir(parents=True)
    pdf=fitz.open();page=pdf.new_page(width=595,height=842)
    page.insert_text((50,60),'Synthetic transport fixture only. No real internal document.')
    pdf.save(source);pdf.close()
    source_sha=t.sha(source)
    rows=[{'document_id':'mock','source_artifact_sha256':source_sha,'is_latest':True}]
    if scenario in {'chunks','docling'}:
        bad=source.with_name('실패규정(20250101).pdf')
        pdf=fitz.open();page=pdf.new_page();page.insert_text((50,60),'Deliberate parser failure fixture.');pdf.save(bad);pdf.close()
        rows.append({'document_id':'bad','source_artifact_sha256':t.sha(bad),'is_latest':True})
    selection(dev,rows)
    exporter.export(dev,tmp_path/'export')
    # Only synthetic glossary configuration is rebound; product Python bytes stay exact.
    shutil.copyfile(dev/'00_SYSTEM/GLOSSARY_PIPELINE.json',service/'00_SYSTEM/GLOSSARY_PIPELINE.json')
    pins=t.read(service/'CODE_PINS.json')
    pins['files']['00_SYSTEM/GLOSSARY_PIPELINE.json']=t.sha(service/'00_SYSTEM/GLOSSARY_PIPELINE.json')
    t.write(service/'CODE_PINS.json',pins)
    shared=tmp_path/'shared';shared.mkdir();calls=[];errors=[]
    doc=DoclingDocument(name='모의규정')
    doc.add_page(page_no=1,size=Size(width=595,height=842))
    def prov(y):return ProvenanceItem(page_no=1,charspan=(0,1),bbox=BoundingBox(l=50,t=y,r=500,b=y+30,coord_origin='TOPLEFT'))
    doc.add_text(label=DocItemLabel.SECTION_HEADER,text='제1조(정의)',prov=prov(50))
    doc.add_text(label=DocItemLabel.TEXT,text='이 규정에서 영업일이란 은행이 영업하는 날을 말한다.',prov=prov(90))
    doc.add_text(label=DocItemLabel.SECTION_HEADER,text='제2조(신청)',prov=prov(130))
    doc.add_text(label=DocItemLabel.TEXT,text='신청인은 제1조에 따른 영업일에 신청한다.',prov=prov(170))
    cells=[TableCell(text='영업일',start_row_offset_idx=0,end_row_offset_idx=1,start_col_offset_idx=0,end_col_offset_idx=1),
           TableCell(text='은행 영업일',start_row_offset_idx=0,end_row_offset_idx=1,start_col_offset_idx=1,end_col_offset_idx=2)]
    doc.add_table(data=TableData(num_rows=1,num_cols=2,table_cells=cells),prov=prov(220))
    body={'code':0,'data':{'document':doc.model_dump(mode='json')}}
    if scenario=='chunks':
        body={'code':0,'data':[{'text':'제1조(정의)\n이 규정에서 영업일이란 은행이 영업하는 날을 말한다.\n제2조(신청)\n신청인은 영업일에 신청한다.', 'i_chunk_on_doc':0,'n_chunk_of_doc':1,'i_page':1,'e_page':1,'n_page':0,'chunk_bboxes':None,'media_files':None}]}
    if scenario=='invalid_chunks':body={'code':0,'data':[{'text':'incomplete chunk'}]}
    model_calls=[]
    response=json.dumps(body,ensure_ascii=False).encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path=='/v1/chat/completions':
                    model_calls.append(data)
                    schema=data['response_format']['json_schema']['schema']
                    content=data['messages'][-1]['content']
                    if isinstance(content,list):content=next(x['text'] for x in content if x['type']=='text')
                    user=json.loads(content)
                    if 'corrections' in schema['properties']:
                        answer={'verdict':'approve','corrections':[], 'summary':'Synthetic contract approval'}
                    elif 'opinions' in schema['properties']:
                        answer={'opinions':[], 'summary':'Synthetic contract approval'}
                    elif 'regions' in schema['properties']:
                        answer={'regions':[{'start_block':0,'template_id':'body','label':'body','reason':'synthetic'}]}
                    elif 'families' in schema['properties']:
                        answer={'families':{f:{'parent_family':'$document','heading_position':'line_start','sequence':'consecutive','reset_scope':'parent','rationale':'synthetic'} for f in user['catalog']}}
                    else:
                        answer={'opinion_decisions':[], 'verdict':'approve','issues':[], 'reviewed_state_id':user['reviewed_state_id'],'template_changes':[]}
                    event={'id':'fixture','model':'synthetic-contract-model','choices':[{'index':0,'delta':{'content':json.dumps(answer,ensure_ascii=False)},'finish_reason':'stop'}], 'usage':{'prompt_tokens':10,'completion_tokens':10}}
                    wire=('data: '+json.dumps(event,ensure_ascii=False)+'\n\ndata: [DONE]\n\n').encode()
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(wire)));self.end_headers();self.wfile.write(wire)
                    return
                assert self.path=='/run'
                assert self.headers['Authorization']=='Bearer synthetic-private-key'
                assert data['file_path'].startswith('/server/shared/')
                local=shared/Path(data['file_path']).parent.name/'source.pdf'
                assert t.sha(local) in {r['source_artifact_sha256'] for r in rows}
                assert all(value==0 for value in data['params'].values())
                calls.append(data)
                response=json.dumps({'code':1,'message':'synthetic document parser failure'}).encode() if t.sha(local)!=source_sha else json.dumps(body,ensure_ascii=False).encode()
                self.send_response(500 if scenario=='http_error' else 200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(response)));self.end_headers();self.wfile.write(response)
            except Exception as exc:
                errors.append(repr(exc));self.send_response(500);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    environment={**os.environ,'GENOS_PDF_PARSER':'preprocessor','LEGAL_PIPELINE_PARSER_MODE':'existing-http',
                 'GENOS_PREPROCESSOR_URL':f'http://127.0.0.1:{server.server_port}/run',
                 'GENOS_PREPROCESSOR_SHARED_ROOT':str(shared),'GENOS_PREPROCESSOR_REMOTE_ROOT':'/server/shared',
                 'GENOS_PREPROCESSOR_RESPONSE_MODE':'auto','GENOS_PREPROCESSOR_REVISION':'synthetic-parser-r2',
                 'GENOS_PREPROCESSOR_API_KEY':'synthetic-private-key','HF_HUB_OFFLINE':'1',
                 'TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
                 'PYTHONDONTWRITEBYTECODE':'1','LLM_BACKEND':'genos','STRUCTURE_RECIPE_VLM':'on',
                 'GENOS_LLM_URL':f'http://127.0.0.1:{server.server_port}', 'GENOS_LLM_MODEL':'synthetic-contract-model',
                 'GENOS_LLM_KEY':'synthetic-private-key','STRUCTURE_RECIPE_ACCEPT_WARNINGS':'off'}
    compute=tmp_path/'compute';compute.mkdir()
    arcs={}
    for slot,name in [('raw','RAW_INPUT.zip'),('support','PIPELINE_SUPPORT.zip')]:
        shutil.copyfile(tmp_path/'export'/name,compute/(slot+'.zip'))
        arc=compute/(slot+'.zip');arcs[slot]={'sha256':t.sha(arc),'bytes':arc.stat().st_size}
    try:
        check=subprocess.run([sys.executable,'-c',"import parser_config,json;from pathlib import Path;print(json.dumps(parser_config.require(Path.cwd())))"],
                             cwd=service,env=environment,text=True,capture_output=True,check=True)
        parser_sha=json.loads(check.stdout)['config_sha256']
        result=subprocess.run([sys.executable,str(service/'worker.py'),'--compute',str(compute),'dku-test-r3',json.dumps(arcs),parser_sha],
                              cwd=service,env=environment,text=True,capture_output=True,timeout=240)
        (tmp_path/'worker.log').write_text(result.stdout+result.stderr)
    finally:
        server.shutdown();server.server_close();thread.join(2)
    assert not errors and len(calls)==len(rows)
    assert 'synthetic-private-key' not in result.stdout+result.stderr
    if scenario in {'invalid_chunks','http_error'}:
        assert result.returncode!=0 and not (compute/'result.zip').exists()
        assert 'PHASE STRUCTURE' in result.stdout and 'PHASE PREPARE' not in result.stdout
        assert 'LocalEntryNotFoundError' not in result.stdout+result.stderr
        error='integer indices' if scenario=='invalid_chunks' else 'HTTP 500'
        assert error in result.stdout+result.stderr
        assert list(shared.glob('*/source.pdf'))
        observed={'status':'EXPECTED_FAILURE','scenario':scenario,'mock_parser_http_calls':1,
                  'local_fallback':False,'result_published':False,'shared_input_retained':True,
                  'model_calls':0,'field_server_tested':False}
        (DELIVERY/('NATIVE_PDF_'+scenario.upper()+'.json')).write_text(json.dumps(observed,indent=2)+'\n')
        return
    assert result.returncode==0,(result.stdout+result.stderr)[-14000:]
    assert all('PHASE '+phase in result.stdout for phase in ['STRUCTURE','PREPARE','INDEX','RETURN'])
    assert (compute/'result.zip').is_file()
    parsed=list((compute/'workspace/01_DATA/STRUCTURE').rglob('parse.json'))
    assert parsed
    combined='\n'.join(p.read_text() for p in parsed)
    assert 'genos' in combined.lower() and '영업일' in combined
    receipts=list((compute/'workspace/01_DATA/STRUCTURE').rglob('receipt.json'))
    assert any(json.loads(p.read_text()).get('response_format')==('docling' if scenario=='complete' else scenario) for p in receipts)
    assert model_calls, 'Existing PDF review must actually reach mock GENOS HTTP'
    with zipfile.ZipFile(compute/'result.zip') as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('TRANSPORT.json'))
        assert manifest['metadata']['code_sha256']==t.sha(service/'CODE_PINS.json')
        assert manifest['metadata']['reserved_model_calls']==len(model_calls)
        assert 'model_calls' not in manifest['metadata']
        coverage=json.loads(z.read('audit/pipeline-coverage.json'))
        assert coverage['selected_count']==1 and coverage['omitted_count']==len(rows)-1
        assert coverage['coverage']==('PARTIAL' if len(rows)>1 else 'COMPLETE')
        assert 'audit/excluded-documents.csv' in z.namelist()
        assert len(coverage['selected_document_ids'])==1
        if len(rows)>1:
            assert coverage['original_structure_ok'] is False
            assert coverage['omitted_documents'][0]['phases']['structure']['state']=='FAILED'
            original=compute/'workspace/01_DATA/LOGS/dku-test-r3/structure-selection.json'
            assert json.loads(original.read_text())['completed'] is False
        import sqlite3
        dbpath=tmp_path/'returned-store.sqlite';dbpath.write_bytes(z.read('generation/store.sqlite'))
        with sqlite3.connect(dbpath) as db:
            assert {r[0] for r in db.execute('SELECT document_id FROM document')}==set(coverage['selected_document_ids'])
        assert any('/model-calls/' in n for n in z.namelist())
        assert any(n.endswith('final-restructured-tree.json') for n in z.namelist())
        assert any(n.endswith('response.json') and '/preprocessor/' in n for n in z.namelist())
    observed={'status':'PASS','mock_parser_http_calls':len(calls),'input_sha256':source_sha,
              'actual_stages':['STRUCTURE','SELECT_VERIFIED_SUCCESSES','PREPARE','INDEX','RETURN'],'selected':1,'omitted':len(rows)-1,'local_docling_model_calls':0,
              'mock_model_http_calls':len(model_calls),'real_model_calls':0,'field_server_tested':False,'oracle_retested':False,
              'fixture_glossary_and_pin_rebound':True,'product_python_bytes_unchanged':True,
              'result_zip_bytes':(compute/'result.zip').stat().st_size}
    (DELIVERY/('NATIVE_PDF_'+scenario.upper()+'.json')).write_text(json.dumps(observed,indent=2)+'\n')
