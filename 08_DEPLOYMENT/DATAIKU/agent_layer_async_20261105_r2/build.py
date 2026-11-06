"""Build independent code, public law transport and synthetic demo support attachments."""
import ast
import hashlib
import io
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'agent_layer_async_20261105_r1'
REPO=HERE.parents[2]
FIX=REPO/'09_ARTIFACTS/TEMP/single-cpu-r10-native/test_actual_native_flow_withou1'
FLOW='DATAIKU_AGENT_FLOW_R2.zip'
SERVER='GENOS_AGENT_ASYNC_R2.zip'
RAW='LAW_SAMPLE_R2.zip'
SUPPORT='SAMPLE_SUPPORT_R2.zip'

def sha(data):return hashlib.sha256(data).hexdigest()

def encode(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()

def pack(path,files):
    with zipfile.ZipFile(path,'w') as z:
        for n,b in sorted(files.items()):
            z.writestr(zipfile.ZipInfo(n),b,compress_type=zipfile.ZIP_DEFLATED)
    return path.read_bytes()

def unpack(path,pin):
    assert sha(path.read_bytes())==pin
    with zipfile.ZipFile(path) as z:return {n:z.read(n) for n in z.namelist()}

def replace(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)

def build():
    server=unpack(BASE/'GENOS_AGENT_ASYNC_R1.zip','f3188966270ec39e9845a0b98d2ff745600195bf0753495022d02a771eeb103d')
    flow=unpack(BASE/'DATAIKU_AGENT_FLOW_R1.zip','296a785f7ab1f12954743c140336916793a57f7cddf40f1dd3cbd7b730e419e9')
    source=REPO/'01_DATA/RAW/law/중소기업기본법/중소기업기본법 본문.xml'
    raw_path='01_DATA/RAW/external/sample_team/law/'+source.parent.name+'/'+source.name
    src=source.read_bytes()
    inventory={raw_path.removeprefix('01_DATA/RAW/'):{'raw_path':raw_path,'sha256':sha(src),'bytes':len(src)}}
    files={raw_path:src,'01_DATA/INPUT_MAPPING/documents.json':encode(inventory),
           '01_DATA/INPUT_MAPPING/filename-exceptions.json':flow['FILENAME_EXCEPTIONS.json']}
    files['TRANSPORT.json']=encode({'format':'legal-pipeline-files-v1','files':{
        n:{'bytes':len(b),'sha256':sha(b)} for n,b in files.items()},
        'metadata':{'document_count':1,'format':'local-law-sample-r2','inventory':sha(encode(inventory))}})
    raw=pack(HERE/RAW,files)
    with zipfile.ZipFile(FIX/'export/PIPELINE_SUPPORT.zip') as z:
        support_files={n:z.read(n) for n in z.namelist()}
    catalog='01_DATA/CATALOG/TEAM_LAYOUT.json'
    support_files[catalog]=encode({'schema_version':'team-raw-v1','files':{raw_path.removeprefix('01_DATA/'):{
        'source':'external','team':'sample_team','external_source':'law','kind':'law','role':'body',
        'name':'중소기업기본법','original_path':source.relative_to(REPO/'01_DATA').as_posix(),
        'sha256':sha(src),'security_class':'public','export_allowed':False}}})
    sm=json.loads(support_files['TRANSPORT.json'])
    sm['files'][catalog]={'bytes':len(support_files[catalog]),'sha256':sha(support_files[catalog])}
    support_files['TRANSPORT.json']=encode(sm)
    support=pack(HERE/SUPPORT,support_files)
    profile=(FIX/'dev/00_SYSTEM/GLOSSARY_PIPELINE.json').read_bytes()
    with zipfile.ZipFile(io.BytesIO(support)) as z:
        assert json.loads(z.read('TRANSPORT.json'))['metadata']['glossary_config_sha256']==sha(profile)
    sample={'raw':{'file':RAW,'bytes':len(raw),'sha256':sha(raw)},'support':{'file':SUPPORT,'bytes':len(support),'sha256':sha(support)},
            'document':raw_path,'document_sha256':sha(src)}
    for n,b in [('sample_inputs.json',encode(sample)),('sample_glossary_policy.json',profile)]:server[n]=b
    worker=server['worker.py'].decode()
    worker=replace(worker,"    if t.read(folder/'input-support.json')", """    # A pinned local sample may use its small, labelled glossary. The production
    # policy in the deployment checkout is immutable. Only this job workspace
    # selects the sample policy after both received archives passed verification.
    sample=t.read(root/'sample_inputs.json')
    if archives['support']['sha256']==sample['support']['sha256']:
        if archives['raw']['sha256']!=sample['raw']['sha256']:
            raise ValueError('DEMO_SUPPORT_REQUIRES_EXACT_SAMPLE')
        shutil.copyfile(root/'sample_glossary_policy.json',workspace/'00_SYSTEM/GLOSSARY_PIPELINE.json')
    if t.read(folder/'input-support.json')""")
    server['worker.py']=worker.encode()
    svc=server['service.py'].decode()
    svc=replace(svc,"            support = agent_stage.mounted_support()", """            sample=t.read(ROOT/'sample_inputs.json')
            sample_pair=all(archives[k]['sha256']==sample[k]['sha256'] for k in ('raw','support'))
            support = None if sample_pair else agent_stage.mounted_support()""")
    server['service.py']=svc.encode()
    pins=json.loads(server.pop('CODE_PINS.json'))
    pins.update(revision='genos-agent-layer-r2',files={k:sha(v) for k,v in server.items()})
    server['CODE_PINS.json']=encode(pins)
    server_zip=pack(HERE/SERVER,server)
    flow.pop('FLOW_MANIFEST.json')
    doc=flow['document_input.py'].decode().replace("EXTERNAL={'law'", "EXTERNAL={'external','law'")
    flow['document_input.py']=doc.encode()
    flow['SERVER_PIN.txt']=(sha(server['CODE_PINS.json'])+'\n').encode()
    flow['SAMPLE.json']=encode(sample)
    for n in ('sample_input.py','agent_setup.py'):flow[n]=(HERE/n).read_bytes()
    install=flow['flow_install.py'].decode().replace('LGL_AGENT_R1_','LGL_AGENT_R2_')
    install=replace(install,"    support=[params['SUPPORT_FOLDER_ID']]", """    sample=params['INPUT_MODE']=='SAMPLE_ZIP'
    support=[params['SUPPORT_FOLDER_ID']]""")
    install=replace(install,'    if source.id in [code.id,*support]:','    if not sample and source.id in [code.id,*support]:')
    install=replace(install,"    if cfg['ENVIRONMENT'] not", """    if cfg['INPUT_MODE'] not in ('SAMPLE_ZIP','LOOSE'):
        raise ValueError('INPUT_MODE_INVALID')
    if cfg['INPUT_MODE']=='SAMPLE_ZIP' and cfg['ENVIRONMENT']!='DEV':
        raise ValueError('DEMO_GLOSSARY_IS_FOR_DEV_SILVER')
    if cfg['ENVIRONMENT'] not""")
    flow['flow_install.py']=install.encode()
    runtime=flow['flow_runtime.py'].decode().replace('agent-layer-r1','agent-layer-r2')
    runtime=replace(runtime,'    from document_input import snapshot',"""    if cfg['INPUT_MODE']=='SAMPLE_ZIP':
        from sample_input import snapshot
    else:
        from document_input import snapshot""")
    runtime=replace(runtime,'    declared = archives(raw,folders.get(\'support\'),mounted)',"""    if cfg['INPUT_MODE']=='SAMPLE_ZIP':
        from sample_input import INDEX
        declared=archives(raw,None,INDEX['support'])
    else:
        declared = archives(raw,folders.get('support'),mounted)""")
    runtime=replace(runtime,"            accepted = current['received'][slot]", """            if slot=='support' and cfg['INPUT_MODE']=='SAMPLE_ZIP':
                from sample_input import INDEX
                name=INDEX['support']['file']
            accepted = current['received'][slot]""")
    flow['flow_runtime.py']=runtime.encode()
    flow['FLOW_MANIFEST.json']=encode({'files':{k:sha(v) for k,v in flow.items()}})
    flow_zip=pack(HERE/FLOW,flow)
    old=(BASE/'INSTALL_DATAIKU_R1.txt').read_text()
    boot=ast.literal_eval(next(n.value for n in ast.parse(old).body if isinstance(n,ast.Assign) and n.targets[0].id=='BOOTSTRAP'))
    boot=boot.replace('DATAIKU_AGENT_FLOW_R1.zip',FLOW).replace('296a785f7ab1f12954743c140336916793a57f7cddf40f1dd3cbd7b730e419e9',sha(flow_zip))
    params="""# Dataiku 노트북 새 커널. 세 ZIP을 업로드하고 아래 실제 값들을 입력합니다.
PARAMS = {
    'CODE_FOLDER_ID': '',          # 세 ZIP을 올린 Managed Folder ID
    'WORK_DIR': '',                # 여러 레시피가 함께 쓰는 영속 POSIX 절대 경로
    'SETUP_CONNECTION': 'AIDP',    # SIDDA DDL/GRANT 가능 연결 또는 이미 권한을 가진 owner
    'EXPECTED_SETUP_USER': '',     # 위 연결의 실제 Oracle 로그인
    'GENOS_DB_USER': '',           # GENOS ORDS가 SQL을 실행하는 실제 DB 계정
    'AGENT_CONNECTION': 'AIDP',    # 중간 결과 SELECT용 Dataiku 연결
    'TARGET_CONNECTION': 'AIDP', 'EXPECTED_DB_USER': 'PIDD2APP',
    'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1', 'EMBED_DIMENSIONS': 1024,
    'INPUT_MODE': 'SAMPLE_ZIP', 'ENVIRONMENT': 'DEV',
    'INPUT_FOLDER_ID': '', 'SUPPORT_FOLDER_ID': '', 'DOCUMENT_PREFIX': '', 'GOLD_OWNER': '',
}
"""
    startup="""from flow_install import install, validate
from agent_setup import setup
cfg=dict(PARAMS)
for k in ('SETUP_CONNECTION','EXPECTED_SETUP_USER','GENOS_DB_USER'):
    cfg.pop(k)
if cfg['INPUT_MODE']=='SAMPLE_ZIP':
    cfg['INPUT_FOLDER_ID']=cfg['SUPPORT_FOLDER_ID']=cfg['CODE_FOLDER_ID']
    from sample_input import INDEX
    source=dataiku.Folder(cfg['CODE_FOLDER_ID'],ignore_flow=True)
    for item in (INDEX['raw'],INDEX['support']):
        with source.get_download_stream(item['file']) as f:
            b=f.read(item['bytes']+1)
        if len(b)!=item['bytes'] or hashlib.sha256(b).hexdigest()!=item['sha256']:
            raise ValueError('UPLOAD_ORIGINAL_ZIP:'+item['file'])
validate(cfg)
setup(PARAMS)
install(cfg,BOOTSTRAP)
"""
    (HERE/'DATAIKU_SETUP_R2.txt').write_text(params+'\nBOOTSTRAP = '+repr(boot)+'\nexec(BOOTSTRAP)\n'+startup)
    installer=(BASE/'install_genos.py').read_text().replace('@@ARCHIVE_SHA@@',sha(server_zip)).replace('GENOS_AGENT_ASYNC_R1.zip',SERVER)
    gitpub=(HERE/'genos_publish.py').read_text()
    (HERE/'GENOS_DEPLOY_R2.txt').write_text('''set -eu
checkout=${1:-"$HOME/DEV"}
remote=${2:-origin}
'''+''.join('python3 - '+op+' "$checkout" <<\'PYINSTALL\'\n'+installer+'PYINSTALL\n' for op in ['check','apply','verify'])+
        'python3 - "$checkout" "$remote" <<\'PYPUBLISH\'\n'+gitpub+'PYPUBLISH\n')
    (HERE/'RELEASE.json').write_bytes(encode({'code_zip':sha(server_zip),'code_pin':sha(server['CODE_PINS.json']),
        'flow_zip':sha(flow_zip),'sample':sample,'field_revision':None}))

if __name__=='__main__':build()
