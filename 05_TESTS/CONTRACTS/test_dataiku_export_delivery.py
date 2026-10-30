"""Sealed R7: native DOCX plus skipped PDF/DOC, no parser/model requests."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import base64,gzip,hashlib,json,os,shutil,sqlite3,subprocess,sys,threading,zipfile
from pathlib import Path
from docx import Document
import fitz
import pytest
from test_dataiku_pipeline_delivery import support,selection,exporter,t

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_export_20261028_r8'
SERVICE='GENOS_DATAIKU_COMPUTE_20261028_R8'


@pytest.mark.parametrize('scenario',['mixed','native_only','pdf_only','corrupt_native'])
def test_actual_native_flow_without_preprocessor(tmp_path,term_glossary,scenario):
    with zipfile.ZipFile(DELIVERY/(SERVICE+'.zip')) as z:z.extractall(tmp_path)
    service=tmp_path/SERVICE;dev=tmp_path/'dev'
    blob=gzip.compress('실제 오류를 재현하는 합성 압축 응답'.encode(),mtime=0)
    with sqlite3.connect(term_glossary/'dictionary.sqlite') as db:
        db.execute('INSERT INTO source_request VALUES(?,?,?,?,?,?,?,?)',('fixture-response','fixture:day','{}','OK',blob,hashlib.sha256(gzip.decompress(blob)).hexdigest(),'[]',None))
    report=t.read(term_glossary/'report.json');report['dictionary_sha256']=t.sha(term_glossary/'dictionary.sqlite')
    knowledge=term_glossary.parent/'knowledge/manifest.json';manifest=t.read(knowledge);manifest['dictionary_sha256']=report['dictionary_sha256'];t.write(knowledge,manifest)
    report['knowledge_binding']['manifest_sha256']=t.sha(knowledge);t.write(term_glossary/'report.json',report)
    support(dev,term_glossary)
    raw=dev/'01_DATA/RAW/internal/test_team';raw.mkdir(parents=True)
    if scenario!='pdf_only':
        doc=Document();doc.add_paragraph('제1조(정의)');doc.add_paragraph('이 규정에서 영업일이란 은행이 영업하는 날을 말한다.')
        doc.add_paragraph('제2조(신청)');doc.add_paragraph('신청인은 영업일에 신청한다.')
        doc.save(raw/'직접규정(20250101).docx')
        if scenario=='corrupt_native':(raw/'직접규정(20250101).docx').write_bytes(b'not an office document')
    if scenario!='native_only':
        pdf=fitz.open();pdf.new_page().insert_text((40,40),'This PDF must never be sent to a parser.')
        pdf.save(raw/'건너뜀(20250101).pdf');pdf.close()
    if scenario=='mixed':(raw/'구형규정(20250101).doc').write_bytes(b'Legacy fixture must not trigger conversion')
    originals={p.name:t.sha(p) for p in raw.iterdir()}
    selection(dev,[{'document_id':n,'source_artifact_sha256':h,'is_latest':True} for n,h in originals.items()])
    exporter.export(dev,tmp_path/'export')
    shutil.copyfile(dev/'00_SYSTEM/GLOSSARY_PIPELINE.json',service/'00_SYSTEM/GLOSSARY_PIPELINE.json')
    pins=t.read(service/'CODE_PINS.json');pins['files']['00_SYSTEM/GLOSSARY_PIPELINE.json']=t.sha(service/'00_SYSTEM/GLOSSARY_PIPELINE.json');t.write(service/'CODE_PINS.json',pins)
    calls=[]
    class Trap(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):calls.append(self.path);self.send_error(500,'Forbidden parser/model request')
        def do_GET(self):calls.append(self.path);self.send_error(500,'Forbidden model metadata request')
    server=ThreadingHTTPServer(('127.0.0.1',0),Trap);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url='http://127.0.0.1:'+str(server.server_port)
    # Existing R6 env is intentionally stale and unusable. R7 must ignore it.
    env={**os.environ,'LEGAL_PIPELINE_PARSER_MODE':'existing-http','GENOS_PDF_PARSER':'preprocessor',
         'GENOS_PREPROCESSOR_TRANSPORT':'pod','GENOS_STRUCTURE_CONFIG':'/absent/parser.yaml',
         'GENOS_PREPROCESSOR_URL':url+'/run','GENOS_PREPROCESSOR_SHARED_ROOT':'/absent/shared',
         'GENOS_PDF_CONVERTER_URL':url+'/run','GENOS_LLM_URL':url,'LLM_BACKEND':'genos',
         'PYTHONDONTWRITEBYTECODE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
    compute=tmp_path/'compute';compute.mkdir();arcs={}
    for slot,name in [('raw','RAW_INPUT.zip'),('support','PIPELINE_SUPPORT.zip')]:
        shutil.copyfile(tmp_path/'export'/name,compute/(slot+'.zip'));p=compute/(slot+'.zip');arcs[slot]={'sha256':t.sha(p),'bytes':p.stat().st_size}
    try:
        status=subprocess.run([sys.executable,'-c',"import parser_config,json;from pathlib import Path;print(json.dumps(parser_config.require(Path.cwd())))"],cwd=service,env=env,text=True,capture_output=True,check=True)
        config=json.loads(status.stdout);assert config['preprocessor_enabled'] is False and config['required_environment']==[]
        result=subprocess.run([sys.executable,'-B',str(service/'worker.py'),'--compute',str(compute),'dku-native-r8',json.dumps(arcs),config['config_sha256']],cwd=service,env=env,text=True,capture_output=True,timeout=180)
        (tmp_path/'worker.log').write_text(result.stdout+result.stderr)
    finally:server.shutdown();server.server_close();thread.join(2)
    assert calls==[],calls
    assert {p.name:t.sha(p) for p in raw.iterdir()}==originals
    if scenario in {'pdf_only','corrupt_native'}:
        assert result.returncode!=0 and not (compute/'result.zip').exists()
        assert 'PHASE PREPARE' not in result.stdout
        assert 'PDF_PARSER_BYPASSED_BY_USER' in result.stdout+result.stderr
        assert not list((compute/'workspace/01_DATA/STRUCTURE').rglob('response.json'))
        outcome={'status':'EXPECTED_NO_SUCCESS_STOP','scenario':scenario}
    else:
        assert result.returncode==0,(result.stdout+result.stderr)[-12000:]
        assert 'PHASE_RESULT ' in result.stdout and 'DATABASE_READY' in result.stdout
        assert not (compute/'query/download').exists() and not (compute/'query/query-data.zip').exists()
        assert all('PHASE '+p in result.stdout for p in ['STRUCTURE','SELECT_VERIFIED_SUCCESSES','PREPARE','INDEX','RETURN'])
        with zipfile.ZipFile(compute/'result.zip') as z:
            coverage=json.loads(z.read('audit/pipeline-coverage.json'));manifest=json.loads(z.read('TRANSPORT.json'))
            assert coverage['selected_count']==1 and coverage['omitted_count']==(2 if scenario=='mixed' else 0)
            assert coverage['bypassed_count']==coverage['omitted_count'] and coverage['failed_count']==0
            assert coverage['preprocessor_enabled'] is False
            assert manifest['metadata']['reserved_model_calls']==0
            assert manifest['metadata']['coverage']['bypassed_count']==coverage['bypassed_count']
            csv=z.read('audit/excluded-documents.csv').decode('utf-8-sig')
            if scenario=='mixed':assert 'BYPASSED_BY_USER' in csv
            querydb=tmp_path/'query-result.sqlite';querydb.write_bytes(z.read('query/query-data.db'))
            with sqlite3.connect(querydb) as db:
                records=[json.loads(r[0]) for r in db.execute("SELECT body FROM query_row WHERE kind LIKE '%.source_request'")]
            assert records and all(base64.b64decode(r['value']['response'],validate=True)==blob for r in records)
            dbpath=tmp_path/'returned.sqlite';dbpath.write_bytes(z.read('generation/store.sqlite'))
            with sqlite3.connect(dbpath) as db:assert {r[0] for r in db.execute('SELECT document_id FROM document')}==set(coverage['selected_document_ids'])
        outcome={'status':'PASS','scenario':scenario,'coverage':coverage['coverage'],'selected':coverage['selected_count'],'bypassed':coverage['bypassed_count']}
    outcome.update(preprocessor_http_calls=0,converter_http_calls=0,model_http_calls=0,actual_model_calls=0,
       product_python_matches_sealed_zip=True,synthetic_glossary_policy_and_pin_rebound=True,field_tested=False)
    (DELIVERY/('NATIVE_'+scenario.upper()+'.json')).write_text(json.dumps(outcome,indent=2)+'\n')
