"""Opt-in exact delivery/native worker/JDBC bridge against disposable local Oracle."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import pytest
from test_dataiku_pipeline_delivery import support,selection,exporter,t

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_mapped_20261023_r1'
pytestmark=pytest.mark.skipif(os.environ.get('A8_MAPPED_ORACLE_LIVE')!='1',reason='local task Oracle only')


def test_packaged_async_pipeline_to_real_oracle(tmp_path,term_glossary):
    details=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert details['Config']['Labels']['a8.task']=='legal-mapped-20261023'
    assert details['NetworkSettings']['Ports']['1521/tcp']==[{'HostIp':'127.0.0.1','HostPort':'11524'}]
    for archive in ['GENOS_PIPELINE_SERVICE_20261022_R2','DATAIKU_PIPELINE_CLIENT_20261023_R1']:
        with zipfile.ZipFile(DELIVERY/(archive+'.zip')) as z:z.extractall(tmp_path)
    service=tmp_path/'GENOS_PIPELINE_SERVICE_20261022_R2';client=tmp_path/'DATAIKU_PIPELINE_CLIENT_20261023_R1'
    dev=tmp_path/'dev';support(dev,term_glossary)
    raw=dev/'01_DATA/RAW/external/test_team'/('가'*80+'.xml');raw.parent.mkdir(parents=True)
    raw.write_text('''<?xml version="1.0" encoding="UTF-8"?><법령><기본정보><법령명_한글>모의법</법령명_한글><법령ID>999</법령ID><시행일자>20261022</시행일자></기본정보><조문><조문단위 조문키="0001001"><조문번호>1</조문번호><조문여부>조문</조문여부><조문제목>정의</조문제목><조문내용>제1조(정의) 영업일은 은행이 영업하는 날을 말한다.</조문내용></조문단위><조문단위 조문키="0002001"><조문번호>2</조문번호><조문여부>조문</조문여부><조문제목>신청</조문제목><조문내용>제2조(신청) 신청인은 제1조에 따른 영업일에 신청한다.</조문내용></조문단위></조문></법령>''')
    selection(dev,[]);exporter.export(dev,tmp_path/'export')
    shutil.copyfile(dev/'00_SYSTEM/GLOSSARY_PIPELINE.json',service/'00_SYSTEM/GLOSSARY_PIPELINE.json')
    pins=t.read(service/'CODE_PINS.json');pins['files']['00_SYSTEM/GLOSSARY_PIPELINE.json']=t.sha(service/'00_SYSTEM/GLOSSARY_PIPELINE.json');t.write(service/'CODE_PINS.json',pins)
    # Fixture knowledge requires only configuration/code-pin rebinding. Executables remain byte-identical.
    (client/'SERVICE_CODE_SHA256.txt').write_text(t.sha(service/'CODE_PINS.json')+'\n')
    restored=tmp_path/'inputs'
    import importlib.util
    spec=importlib.util.spec_from_file_location('mapped_transport',client/'transport.py');transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
    for name in ['RAW_INPUT.zip','PIPELINE_SUPPORT.zip']:transport.unpack(tmp_path/'export'/name,restored)
    work=tmp_path/'work';work.mkdir()
    env={**os.environ,'PIPELINE_SCRATCH':str(tmp_path/'scratch'),'PYTHONDONTWRITEBYTECODE':'1'}
    p=subprocess.run([sys.executable,str(ROOT/'05_TESTS/CONTRACTS/mapped_pipeline_live_runner.py'),str(client),str(service),str(work),str(restored),str(tmp_path/'export')],env=env,text=True,capture_output=True,timeout=240)
    (work/'execution.log').write_text(p.stdout+p.stderr)
    if p.returncode:
        for log in (tmp_path/'scratch').rglob('*.log'):print(log.name,log.read_text()[-5000:])
    assert p.returncode==0,(p.stdout+p.stderr)[-14000:]
    result=json.loads((work/'RESULT.json').read_text());assert result['status']=='PASS'
    (DELIVERY/'LOCAL_ORACLE_E2E_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
