"""Seal the Dataiku data-ZIP starting point on the existing R5 Agent/Gold flow."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'agent_layer_ords_20261105_r5'
SERVER = 'GENOS_AGENT_ZIP_R6.zip'
FLOW = 'DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip'
PROTOCOL = 'genos-agent-zip-v1'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(obj): return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
def replace(text, old, new):
    if text.count(old) != 1: raise ValueError('PARENT_SOURCE_CHANGED:' + old[:80])
    return text.replace(old, new)
def unpack(name, pin):
    if sha((PARENT/name).read_bytes()) != pin: raise ValueError('PARENT_ZIP_HASH:' + name)
    with zipfile.ZipFile(PARENT/name) as z: return {n:z.read(n) for n in z.namelist()}
def pack(path, files):
    with zipfile.ZipFile(path, 'w') as z:
        for n, raw in sorted(files.items()):
            if Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'}: raise ValueError('NESTED_OR_JS_MEMBER')
            z.writestr(zipfile.ZipInfo(n), raw, compress_type=zipfile.ZIP_DEFLATED)
    return sha(path.read_bytes())


def build():
    server = unpack('GENOS_AGENT_ORDS_R5.zip','dd950062412ee948fab733b5920d62cb29486898fe38c97fa9c971590ad33eec')
    flow = unpack('DATAIKU_AGENT_GOLD_FLOW_R5.zip','092d06e0f7bc5b53574e72d45e3dcd286f74b366416a91cd14440be0f637e9a4')
    server['service.py'] = server['service.py'].replace(b'genos-agent-ords-v1',PROTOCOL.encode())
    worker = server['worker.py'].decode()
    worker = replace(worker, "        t.write(folder/('input-'+slot+'.json'),t.unpack(archive,workspace,prefixes=prefixes))", """        if slot == 'raw':
            from raw_zip_input import unpack as unpack_raw
            receipt = unpack_raw(archive, workspace)
        else:
            receipt = t.unpack(archive, workspace, prefixes=prefixes)
        t.write(folder/('input-'+slot+'.json'), receipt)""")
    server['worker.py'] = worker.encode()
    server['raw_zip_input.py'] = (HERE/'raw_zip_input.py').read_bytes()
    pins = json.loads(server.pop('CODE_PINS.json'))
    pins.update(revision='genos-agent-zip-r6', files={n:sha(b) for n,b in server.items()})
    server['CODE_PINS.json'] = encode(pins)
    server_sha = pack(HERE/SERVER,server)
    runtime = flow['flow_runtime.py'].decode().replace('genos-agent-ords-v1',PROTOCOL).replace('agent-layer-ords-r5','agent-layer-zip-r6')
    runtime = replace(runtime, "    if cfg['INPUT_MODE']=='SAMPLE_ZIP':\n        from sample_input import snapshot", "    if cfg['INPUT_MODE']=='ZIP':\n        from archive_input import snapshot\n    elif cfg['INPUT_MODE']=='SAMPLE_ZIP':\n        from sample_input import snapshot")
    runtime = replace(runtime, "raw = snapshot(folders['input'],paths,cfg['DOCUMENT_PREFIX'])", "raw = snapshot(folders['input'],paths,cfg if cfg['INPUT_MODE']=='ZIP' else cfg['DOCUMENT_PREFIX'])")
    runtime = replace(runtime, "    if cfg['INPUT_MODE']=='SAMPLE_ZIP':\n        from sample_input import INDEX\n        declared=archives(raw,None,INDEX['support'])", """    if cfg['INPUT_MODE']=='ZIP':
        from archive_input import support_declaration
        declared=archives(raw,None,support_declaration(folders['support'],cfg,raw))
    elif cfg['INPUT_MODE']=='SAMPLE_ZIP':
        from sample_input import INDEX
        declared=archives(raw,None,INDEX['support'])""")
    runtime = replace(runtime, "            if slot=='support' and cfg['INPUT_MODE']=='SAMPLE_ZIP':", "            if slot=='support' and cfg['INPUT_MODE']=='ZIP':\n                name=cfg.get('SUPPORT_ZIP_NAME','PIPELINE_SUPPORT.zip')\n            elif slot=='support' and cfg['INPUT_MODE']=='SAMPLE_ZIP':")
    flow['flow_runtime.py'] = runtime.encode()
    install = flow['flow_install.py'].decode().replace('LGL_AGENT_R5_','LGL_AGENT_R6_')
    install = replace(install, "not in ('SAMPLE_ZIP','LOOSE')", "not in ('ZIP','SAMPLE_ZIP','LOOSE')")
    install = replace(install, "    if cfg['INPUT_MODE']=='SAMPLE_ZIP'", "    if cfg['INPUT_MODE']=='ZIP':\n        from archive_input import archive_name\n        archive_name(cfg.get('DATA_ZIP_NAME'))\n        archive_name(cfg.get('SUPPORT_ZIP_NAME','PIPELINE_SUPPORT.zip'))\n    if cfg['INPUT_MODE']=='SAMPLE_ZIP'")
    install = replace(install, "sample=params['INPUT_MODE']=='SAMPLE_ZIP'", "sample=params['INPUT_MODE'] in ('ZIP','SAMPLE_ZIP')")
    flow['flow_install.py'] = install.encode()
    for n in ('archive_input.py','flow_setup.py'): flow[n] = (HERE/n).read_bytes()
    flow['SERVER_PIN.txt'] = (sha(server['CODE_PINS.json'])+'\n').encode()
    flow.pop('FLOW_MANIFEST.json')
    flow['FLOW_MANIFEST.json'] = encode({'files':{n:sha(b) for n,b in flow.items()}})
    flow_sha = pack(HERE/FLOW,flow)
    tree = ast.parse((PARENT/'DATAIKU_SETUP_R5.txt').read_text())
    boot = ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id=='BOOTSTRAP'))
    boot = boot.replace('DATAIKU_AGENT_GOLD_FLOW_R5.zip',FLOW).replace('092d06e0f7bc5b53574e72d45e3dcd286f74b366416a91cd14440be0f637e9a4',flow_sha)
    sample = json.loads(flow['SAMPLE.json'])
    params = dict(CODE_FOLDER_ID='',INPUT_FOLDER_ID='',DATA_ZIP_NAME=sample['raw']['file'],DATA_ZIP_SHA256=sample['raw']['sha256'],
                  SUPPORT_FOLDER_ID='',SUPPORT_ZIP_NAME=sample['support']['file'],DOCUMENT_PREFIX='',
                  GOLD_OWNER='SIDDS',AGENT_CONNECTION='AIDP',TARGET_CONNECTION='AIDP',EXPECTED_DB_USER='PIDD2APP',
                  EMBED_MODEL='openai:genos-embedding:embedding-kure-v1',EMBED_DIMENSIONS=1024)
    (HERE/'DATAIKU_SETUP_R6.txt').write_text('# 기존 예시 샘플 ZIP에서 시작합니다. CODE_FOLDER_ID 한 곳에 실제 폴더 ID를 입력하세요.\nPARAMS = '+repr(params)+'\nBOOTSTRAP = '+repr(boot)+"\nexec(BOOTSTRAP)\nfrom flow_setup import install_pipeline\ncfg = install_pipeline(PARAMS, BOOTSTRAP)\n")
    deploy = (PARENT/'GENOS_DEPLOY_R5.txt').read_text()
    for a,b in [('GENOS_AGENT_ORDS_R5.zip',SERVER),('dd950062412ee948fab733b5920d62cb29486898fe38c97fa9c971590ad33eec',server_sha),
                ('1138279c6ecdf2ec9af0cd57760077c2ed6e63569fc70a81e32cd360297951f9',sha(server['CODE_PINS.json'])),
                ('genos-agent-ords-r5','genos-agent-zip-r6'),('pinned R5 ORDS payload','pinned R6 data ZIP payload'),
                ('Deploy R5 GENOS ORDS Agent to Gold pipeline','Deploy R6 Dataiku ZIP GENOS Agent Gold pipeline'),
                ('R5_ZIP_HASH_MISMATCH','R6_ZIP_HASH_MISMATCH')]:
        if a not in deploy: raise ValueError('INSTALLER_PARENT_CHANGED:'+a)
        deploy = deploy.replace(a,b)
    (HERE/'GENOS_DEPLOY_R6.txt').write_text(deploy)
    (HERE/'DATAIKU_RESUME_STAGE_R6.txt').write_text((PARENT/'DATAIKU_RESUME_STAGE_R5.txt').read_text().replace('R5','R6'))
    pipeline = json.loads((PARENT/'PIPELINE.json').read_text())
    pipeline.update(protocol=PROTOCOL,dataiku_setup='DATAIKU_SETUP_R6.txt',manual_scenario='LGL_AGENT_R6_PROD_RUN_ALL',
                    input='Previously supplied LAW_SAMPLE_R2.zip and SAMPLE_SUPPORT_R2.zip in Dataiku Managed Folder; original bytes and digests sent to GENOS',
                    zip_formats=['legal-pipeline-files-v1 raw transport ZIP','ordinary raw-document ZIP with internal/team or declared external source paths'])
    pipeline['stages'].insert(0,dict(order=0,recipe='01_SUBMIT',entrypoint='archive_input.snapshot -> flow_runtime.submit PUT',
        output='Byte-identical existing data ZIP, SHA-256 binding, received-offset upload resume; no DSS unpack/recompress'))
    (HERE/'PIPELINE.json').write_bytes(encode(pipeline))
    sample_parent=HERE.parent/'agent_layer_return_20261105_r4'
    for key in ('raw','support'):
        item=sample[key]
        content=(sample_parent/item['file']).read_bytes()
        if len(content)!=item['bytes'] or sha(content)!=item['sha256']:
            raise ValueError('ORIGINAL_SAMPLE_CHANGED')
        shutil.copyfile(sample_parent/item['file'],HERE/item['file'])
    (HERE/'RELEASE.json').write_bytes(encode(dict(protocol=PROTOCOL,parent='agent_layer_ords_20261105_r5',
        code_zip=server_sha,code_pin=sha(server['CODE_PINS.json']),flow_zip=flow_sha,
        server_files=len(server),flow_files=len(flow),database_writer='GENOS ORDS',agent_table='SIDDA.LGL_PIPE_RESULT_A',
        gold_writer='Dataiku AIDP',input_mode='ZIP',sample=sample,dataiku_recompress=False,pipeline_sha256=sha(encode(pipeline)),
        actual_checkout_commit=None,field_revision=None,data_generation='per-job Dataiku data ZIP and support ZIP digests')))


if __name__=='__main__': build()
