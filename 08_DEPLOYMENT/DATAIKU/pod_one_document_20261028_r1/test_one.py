import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import fitz
import pytest
from docling_core.types.doc import DoclingDocument,DocItemLabel,Size

HERE=Path(__file__).resolve().parent
CODE='8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

@pytest.fixture
def case(tmp_path):
    with zipfile.ZipFile(HERE/'GENOS_DATAIKU_COMPUTE_20261028_R4.zip') as z:z.extractall(tmp_path)
    root=tmp_path/'GENOS_DATAIKU_COMPUTE_20261028_R4'
    doc=DoclingDocument(name='synthetic')
    doc.add_page(page_no=1,size=Size(width=595,height=842))
    doc.add_text(label=DocItemLabel.TEXT,text='제1조 시험 문서의 파싱 결과입니다.')
    facade=root/'pod_vendor/genon/preprocessor/facade/parser_processor.py'
    # Only upstream model/parser and OS converter are mocked. R4 adapters, PDF
    # validation, manifest checks, process supervision and exports stay real.
    facade.write_text('''import os,time,subprocess,sys
class DocumentProcessor:
    def __init__(self,config_path):pass
    async def __call__(self,request,file_path,**kwargs):
        mode=os.environ.get('FIXTURE_CASE','ok')
        if mode=='hang':
            p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])
            open(os.environ['FIXTURE_PID'],'w').write(str(p.pid))
            time.sleep(120)
        if mode=='exit':os._exit(7)
        if mode=='parse_fail':raise RuntimeError('fixture parser failure')
        return '''+repr({'document':doc.model_dump(mode='json')})+'\n')
    pins=json.loads((root/'CODE_PINS.json').read_text());pins['files'][str(facade.relative_to(root))]=sha(facade)
    (root/'CODE_PINS.json').write_text(json.dumps(pins,sort_keys=True)+'\n')
    script=tmp_path/'test.txt';script.write_text((HERE/'GENOS_ONE_DOCUMENT_TEST.txt').read_text().replace(CODE,sha(root/'CODE_PINS.json')))
    binary=tmp_path/'bin';binary.mkdir();soffice=binary/'soffice'
    soffice.write_text('#!'+sys.executable+'''\nimport os,sys,fitz
from pathlib import Path
if os.environ.get('FIXTURE_CASE')=='convert_fail':raise SystemExit(1)
p=Path(sys.argv[-1]);out=Path(sys.argv[sys.argv.index('--outdir')+1])/p.with_suffix('.pdf').name
pdf=fitz.open();pdf.new_page(width=595,height=842);pdf.save(out)
''');soffice.chmod(0o755)
    # Bash TXT uses python3: use exactly the tested virtualenv interpreter.
    import shlex
    (binary/'python3').write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' "$@"\n')
    (binary/'python3').chmod(0o755)
    config=tmp_path/'parser.yaml';config.write_text('layout:\n  layout_model_type: genos_layout\n  genos_layout:\n    endpoint: http://fixture.invalid/layout\nocr:\n  ocr_mode: disable\nenrichment: []\noutput:\n  format: docling\n')
    source=tmp_path/'공백 있는 문서.docx';source.write_bytes(b'synthetic source; OS converter mocked')
    env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],'FIXTURE_PID':str(tmp_path/'child.pid')}
    return root,script,config,source,env,tmp_path


def run(case,scenario='ok',suffix=None,extra=()):
    root,script,config,source,env,tmp=case
    if suffix=='.pdf':
        source=source.with_suffix('.pdf');pdf=fitz.open();pdf.new_page();pdf.save(source)
    original=sha(source)
    result=subprocess.run(['bash',str(script),str(source),'--config',str(config),'--code-root',str(root),*extra],
                          cwd=tmp,env={**env,'FIXTURE_CASE':scenario},text=True,capture_output=True,timeout=30)
    folders=list(tmp.glob('pod-one-*'));assert len(folders)==1,(result.stdout,result.stderr)
    out=folders[0];summary=json.loads((out/'summary.json').read_text())
    assert sha(source)==original and summary['original_unchanged']
    assert not (root/'01_DATA/RAW').exists()
    return result,out,summary


@pytest.mark.parametrize('suffix',[None,'.pdf'])
def test_exact_txt_single_document_result(case,suffix):
    result,out,state=run(case,suffix=suffix)
    assert result.returncode==0,(out/'test.log').read_text()
    assert state['status']=='PASS' and state['parsing']['status']=='PASS'
    assert state['pdf_conversion']['status']==('PASS' if suffix is None else 'SKIPPED_ALREADY_PDF')
    assert state['conversion_tested']==(suffix is None)
    assert state['application_review_calls']==0 and state['database_writes'] is False
    assert '제1조' in (out/'parsed.txt').read_text()
    with fitz.open(out/'result.pdf') as pdf:assert len(pdf)==1
    with zipfile.ZipFile(out/'report.zip') as z:
        assert z.testzip() is None and 'result.pdf' in z.namelist()
        assert 'parsed.txt' in z.namelist() and 'summary.json' in z.namelist()
        assert not any(n.endswith(('.docx','.py','.js')) for n in z.namelist())


@pytest.mark.parametrize('scenario,phase,pdf_exists',[
    ('convert_fail','pdf_conversion',False),('parse_fail','parsing',True),('bad_config','parsing',True),('exit','parsing',True)])
def test_failure_stage_and_partial_pdf(case,scenario,phase,pdf_exists):
    if scenario=='bad_config':case[2].write_text('invalid: true\n')
    result,out,state=run(case,scenario)
    assert result.returncode!=0 and state['status']=='FAILED' and state['phase']==phase
    assert state[phase]['status']=='FAILED'
    assert (out/'result.pdf').exists()==pdf_exists
    assert not (out/'parsed.txt').exists() and (out/'report.zip').is_file()
    if pdf_exists:assert state['pdf_conversion']['status']=='PASS'


def test_deadline_stops_parser_and_its_child(case):
    result,out,state=run(case,'hang',extra=('--timeout-seconds','4'))
    assert result.returncode==124 and state['status']=='TIMEOUT'
    pid=int(Path(case[4]['FIXTURE_PID']).read_text())
    stat=Path('/proc')/str(pid)/'stat'
    assert not stat.exists() or stat.read_text().rsplit(')',1)[1].split()[0]=='Z'
    assert (out/'result.pdf').is_file() and (out/'report.zip').is_file()


def test_input_directory_rejected_no_bulk_run(case):
    root,script,config,source,env,tmp=case
    r=subprocess.run(['bash',str(script),str(tmp),'--config',str(config),'--code-root',str(root)],cwd=tmp,env=env,capture_output=True)
    assert r.returncode and not list(tmp.glob('pod-one-*'))


def test_tampered_r4_rejected_before_any_document(case):
    root,script,config,source,env,tmp=case
    (root/'pod_parser.py').write_text('# changed')
    r=subprocess.run(['bash',str(script),str(source),'--config',str(config),'--code-root',str(root)],cwd=tmp,env=env,capture_output=True,text=True)
    assert r.returncode and 'R4_CODE_FILE_CHANGED' in r.stderr and not list(tmp.glob('pod-one-*'))


def test_default_archive_reads_exact_pins_and_preserves_checkout(tmp_path):
    # Run the unmodified deliverable with a real sealed archive. A missing fork
    # can fail parsing; source selection must still use the exact bundled code.
    code=(HERE/'GENOS_ONE_DOCUMENT_TEST.txt').read_text();assert '__RUNNER_SOURCE__' not in code
    python=code.split("<<'PY_ONE_DOCUMENT'\n",1)[1].rsplit('\nPY_ONE_DOCUMENT',1)[0]
    assert python==(HERE/'single_document.py').read_text()
    ns={'__name__':'test_loader'};exec(compile(python,'delivered.txt','exec'),ns)
    class Args:code_root=None;archive=str(HERE/'GENOS_DATAIKU_COMPUTE_20261028_R4.zip')
    with ns['code_root'](Args()) as root:
        assert ns['sha'](root/'CODE_PINS.json')==CODE
        assert root.is_dir()
    assert not root.exists()


def test_ctrl_c_stops_only_test_group_and_preserves_pdf(case):
    import signal
    root,script,config,source,env,tmp=case
    process=subprocess.Popen(['bash',str(script),str(source),'--config',str(config),'--code-root',str(root)],
        cwd=tmp,env={**env,'FIXTURE_CASE':'hang'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,start_new_session=True)
    pidfile=Path(env['FIXTURE_PID'])
    try:
        until=time.monotonic()+10
        while not pidfile.exists() and time.monotonic()<until:time.sleep(.05)
        assert pidfile.exists()
        os.killpg(process.pid,signal.SIGINT)
        stdout,stderr=process.communicate(timeout=10)
        out=next(tmp.glob('pod-one-*'));state=json.loads((out/'summary.json').read_text())
        assert state['status']=='CANCELLED' and state['original_unchanged']
        assert (out/'result.pdf').is_file() and (out/'report.zip').is_file()
        childstat=Path('/proc')/pidfile.read_text()/'stat'
        assert not childstat.exists() or childstat.read_text().rsplit(')',1)[1].split()[0]=='Z'
    finally:
        if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait()
