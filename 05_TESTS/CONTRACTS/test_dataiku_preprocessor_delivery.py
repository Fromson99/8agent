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
DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_preprocessor_20261027_r2'


@pytest.mark.parametrize('scenario',['success','chunks_only','http_error'])
def test_sealed_worker_remote_pdf_to_return_zip(tmp_path,term_glossary,scenario):
    with zipfile.ZipFile(DELIVERY/'GENOS_DATAIKU_COMPUTE_20261027_R2.zip') as z:z.extractall(tmp_path)
    service=tmp_path/'GENOS_DATAIKU_COMPUTE_20261027_R2'
    dev=tmp_path/'dev';support(dev,term_glossary)
    source=dev/'01_DATA/RAW/internal/test_team/모의규정(20250101).pdf'
    source.parent.mkdir(parents=True)
    pdf=fitz.open();page=pdf.new_page(width=595,height=842)
    page.insert_text((50,60),'Synthetic transport fixture only. No real internal document.')
    pdf.save(source);pdf.close()
    source_sha=t.sha(source)
    selection(dev,[{'document_id':'mock','source_artifact_sha256':source_sha,'is_latest':True}])
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
    if scenario=='chunks_only':body={'code':0,'data':[{'text':'incomplete chunk'}]}
    response=json.dumps(body,ensure_ascii=False).encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert self.path=='/parser'
                assert self.headers['Authorization']=='Bearer synthetic-private-key'
                assert data['file_path'].startswith('/server/shared/')
                local=shared/Path(data['file_path']).parent.name/'source.pdf'
                assert t.sha(local)==source_sha
                assert all(value==0 for value in data['params'].values())
                calls.append(data)
                self.send_response(500 if scenario=='http_error' else 200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(response)));self.end_headers();self.wfile.write(response)
            except Exception as exc:
                errors.append(repr(exc));self.send_response(500);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    environment={**os.environ,'GENOS_PDF_PARSER':'preprocessor',
                 'GENOS_PREPROCESSOR_URL':f'http://127.0.0.1:{server.server_port}/parser',
                 'GENOS_PREPROCESSOR_SHARED_ROOT':str(shared),'GENOS_PREPROCESSOR_REMOTE_ROOT':'/server/shared',
                 'GENOS_PREPROCESSOR_RESPONSE_MODE':'docling','GENOS_PREPROCESSOR_REVISION':'synthetic-parser-r2',
                 'GENOS_PREPROCESSOR_API_KEY':'synthetic-private-key','HF_HUB_OFFLINE':'1',
                 'TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
                 'PYTHONDONTWRITEBYTECODE':'1'}
    compute=tmp_path/'compute';compute.mkdir()
    arcs={}
    for slot,name in [('raw','RAW_INPUT.zip'),('support','PIPELINE_SUPPORT.zip')]:
        shutil.copyfile(tmp_path/'export'/name,compute/(slot+'.zip'))
        arc=compute/(slot+'.zip');arcs[slot]={'sha256':t.sha(arc),'bytes':arc.stat().st_size}
    try:
        check=subprocess.run([sys.executable,'-c',"import parser_config,json;from pathlib import Path;print(json.dumps(parser_config.require(Path.cwd())))"],
                             cwd=service,env=environment,text=True,capture_output=True,check=True)
        parser_sha=json.loads(check.stdout)['config_sha256']
        result=subprocess.run([sys.executable,str(service/'worker.py'),'--compute',str(compute),'dku-test-r2',json.dumps(arcs),parser_sha],
                              cwd=service,env=environment,text=True,capture_output=True,timeout=240)
        (tmp_path/'worker.log').write_text(result.stdout+result.stderr)
    finally:
        server.shutdown();server.server_close();thread.join(2)
    assert not errors and len(calls)==1
    assert 'synthetic-private-key' not in result.stdout+result.stderr
    if scenario!='success':
        assert result.returncode!=0 and not (compute/'result.zip').exists()
        assert 'PHASE STRUCTURE' in result.stdout and 'PHASE PREPARE' not in result.stdout
        assert 'LocalEntryNotFoundError' not in result.stdout+result.stderr
        error='requires data.document' if scenario=='chunks_only' else 'HTTP 500'
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
    assert 'genos' in combined.lower() and '은행 영업일' in combined
    receipts=list((compute/'workspace/01_DATA/STRUCTURE').rglob('receipt.json'))
    assert any(json.loads(p.read_text()).get('response_format')=='docling' for p in receipts)
    with zipfile.ZipFile(compute/'result.zip') as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('TRANSPORT.json'))
        assert manifest['metadata']['code_sha256']==t.sha(service/'CODE_PINS.json')
    observed={'status':'PASS','mock_parser_http_calls':len(calls),'input_sha256':source_sha,
              'actual_stages':['STRUCTURE','PREPARE','INDEX','RETURN'],'local_docling_model_calls':0,
              'real_model_calls':0,'field_server_tested':False,'oracle_retested':False,
              'fixture_glossary_and_pin_rebound':True,'product_python_bytes_unchanged':True,
              'result_zip_bytes':(compute/'result.zip').stat().st_size}
    (DELIVERY/'NATIVE_PDF_RESULT.json').write_text(json.dumps(observed,indent=2)+'\n')
