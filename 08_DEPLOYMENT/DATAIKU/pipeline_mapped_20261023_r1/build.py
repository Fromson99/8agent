"""Pair the sealed GENOS R2 worker with the mapped Dataiku importer and SQL."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import build_mapping
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
OLD=HERE.parent/'pipeline_service_20261022_r1';R3=HERE.parent/'pipeline_service_20261022_r3'
CLIENT='DATAIKU_PIPELINE_CLIENT_20261023_R1'
SERVICE='GENOS_PIPELINE_SERVICE_20261022_R2.zip'
def sha(b):return hashlib.sha256(b).hexdigest()
def archive(path,files,prefix):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(files.items()):
            item=zipfile.ZipInfo(prefix+'/'+name,date_time=(2026,10,23,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(item,raw)
def build():
    build_mapping.build()
    base=OLD/'DATAIKU_PIPELINE_CLIENT_20261022_R1.zip'
    assert sha(base.read_bytes())=='f57ab052f15ea031487d7f61b2c9f780d15a9dda813fb6ac2d86945c43db4b0b'
    with zipfile.ZipFile(base) as z:files={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    for name in ['lawrag/pipeline/oracle_migration.py','lawrag/pipeline/oracle_query_package.py',
                 'lawrag/pipeline/oracle_query_publish.py','lawrag/pipeline/oracle_query_dataiku.py',
                 'semantic_runtime/oracle_dp_io.py','semantic_runtime/oracle_dp_assets.py',
                 'semantic_runtime/oracle_query_catalog.py','semantic_runtime/physical_mapping.py']:
        files['02_BACKEND/'+name]=(REPO/'02_BACKEND'/name).read_bytes()
    for name in ['dataiku_run.py','managed_job.py']:files[name]=(HERE/'src'/name).read_bytes()
    files['transport.py']=(R3/'src/transport.py').read_bytes()
    manifest=json.loads((R3/'CODE_MANIFEST.json').read_text())
    service=(R3/SERVICE).read_bytes()
    assert sha(service)==manifest['service_zip_sha256']
    files['SERVICE_CODE_SHA256.txt']=(manifest['service_code_sha256']+'\n').encode()
    for name in ['physical_mapping.yaml','MAPPING_BINDING.json']:files[name]=(HERE/name).read_bytes()
    files['requirements.txt']=b'PyYAML>=6.0,<7\n# dataiku and pandas are supplied by the Dataiku code environment.\n'
    files['GUIDE.txt']=(HERE/'GUIDE.txt').read_bytes()
    files.pop('CODE_PINS.json',None)
    files['CODE_PINS.json']=json.dumps({'files':{n:sha(b) for n,b in sorted(files.items())}},indent=2).encode()
    archive(HERE/(CLIENT+'.zip'),files,CLIENT)
    runner=(HERE/'runner_template.py').read_text()
    runner=runner.replace('__CLIENT_SHA256__',sha((HERE/(CLIENT+'.zip')).read_bytes())).replace('__CLIENT_BYTES__',str((HERE/(CLIENT+'.zip')).stat().st_size))
    compile(runner,'DATAIKU_PIPELINE_RUN_20261023_R1.txt','exec')
    (HERE/'DATAIKU_PIPELINE_RUN_20261023_R1.txt').write_text(runner)
    shutil.copyfile(R3/SERVICE,HERE/SERVICE)
    shutil.copyfile(R3/'install_here_20261022_r1/GENOS_PIPELINE_INSTALL_HERE_20261022_R1.txt',HERE/'GENOS_PIPELINE_INSTALL_HERE_20261022_R1.txt')
    names=[CLIENT+'.zip',SERVICE,'GENOS_PIPELINE_INSTALL_HERE_20261022_R1.txt','DATAIKU_PIPELINE_RUN_20261023_R1.txt',
           '01_CREATE_TABLES.sql','02_COMMENTS.sql','physical_mapping.yaml','MAPPING_BINDING.json','GUIDE.txt']
    for name in ['VALIDATION.json','LOCAL_ORACLE_E2E_RESULT.json','CONTRACT_TESTS.xml','ORACLE_E2E_TEST.xml','LEGACY_REGRESSION_TESTS.xml']:
        if (HERE/name).exists():names.append(name)
    pins={n:sha((HERE/n).read_bytes()) for n in names}
    metadata={'version':'pipeline-mapped-20261023-r1','files':pins,'genos_code_sha256':manifest['service_code_sha256'],
              'client_code_sha256':sha(files['CODE_PINS.json']),'genos_worker_changed':False,'connection':'AIDP','owner':'SIDDA',
              'main_changed':False,'field_deployed':False,'gold_approved':False}
    (HERE/'DELIVERY_MANIFEST.json').write_text(json.dumps(metadata,indent=2)+'\n')
    archive(HERE/'LEGAL_PIPELINE_E2E_20261023_R1.zip',{n:(HERE/n).read_bytes() for n in [*names,'DELIVERY_MANIFEST.json']},'LEGAL_PIPELINE_E2E_20261023_R1')
    print(json.dumps({'files':len(files),'client_bytes':(HERE/(CLIENT+'.zip')).stat().st_size,'genos_code_sha256':manifest['service_code_sha256']}))
if __name__=='__main__':build()
