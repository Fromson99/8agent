"""Compose two standalone, reproducible imports from the sealed R10 and R5 ZIPs."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
REPO=BASE.parents[1]
SERVICE='GENOS_AGENT_ASYNC_R1.zip'
FLOW='DATAIKU_AGENT_FLOW_R1.zip'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False)+'\n').encode()


def load(path, checksum, prefix=''):
    raw=path.read_bytes()
    if sha(raw)!=checksum:
        raise ValueError('PARENT_ARCHIVE_CHANGED:'+str(path))
    with zipfile.ZipFile(path) as z:
        return {i.filename.removeprefix(prefix):z.read(i) for i in z.infolist() if not i.is_dir()}


def replace(src, old, new):
    if src.count(old)!=1:
        raise ValueError('PARENT_CODE_CHANGED:'+old)
    return src.replace(old,new)


def pack(name,files):
    with zipfile.ZipFile(HERE/name,'w') as z:
        for f,raw in sorted(files.items()):
            z.writestr(zipfile.ZipInfo(f),raw,compress_type=zipfile.ZIP_DEFLATED,compresslevel=7)
    return sha((HERE/name).read_bytes())


def build():
    oldserver='GENOS_DATAIKU_COMPUTE_20261029_R10'
    server=load(BASE/'pipeline_single_cpu_20261029_r10'/(oldserver+'.zip'),
                'c9830f94791fbcf3a99c9131cc042953107f26b17523962ecd134039e8cf377c',oldserver+'/')
    recipes=load(BASE/'pipeline_single_cpu_20261029_r10/DATAIKU_COMPUTE_RECIPES_20261029_R10.zip',
                 '947c62bb1a8796ee6de1ee730d36cf3a93ec9b07417405f2259efb6926d9843c')
    gold=load(BASE/'gold_oneclick_prod_20261105_r5/DATAIKU_GOLD_ONECLICK_PROD_20261105_R5.zip',
              'f6060c4b2cd3a7ba2667095efe4dc8fe76e47f83579974823aa4620ffad742d0')
    parents=json.loads(server.pop('CODE_PINS.json'))
    assert {n:sha(b) for n,b in server.items()}==parents['files']
    service=server['service.py'].decode().replace("PROTOCOL = 'dataiku-owned-compute-v1'", "PROTOCOL = 'genos-agent-layer-v1'")
    service=replace(service,"        with GUARD:\n            h.update(state='COMPLETE', phase='RETURN', result=result)",
                    """        import agent_stage
        with GUARD:
            h['phase']='WRITING_AGENT_LAYER'
        try:
            agent_stage.publish(h, t.sha(ROOT/'CODE_PINS.json'), result, lambda: resource_check(h))
        except Exception as exc:
            # Never release Oracle exception text, tokens or binds to DSS.
            with (folder/'compute.log').open('a') as log:
                log.write('AGENT_STAGE_FAILED '+type(exc).__name__+'\\n')
                if isinstance(exc, RuntimeError):
                    match = re.search(r'ORA-[0-9]{5}',str(exc))
                    if match: log.write(match[0]+'\\n')
            raise RuntimeError('AGENT_STAGE_FAILED') from None
        with GUARD:
            h.update(state='COMPLETE', phase='READY_IN_AGENT_LAYER', result=result)""")
    service=replace(service,"if time.monotonic() >= h['lease_until']:\n        raise RuntimeError",
                    "if h['state'] != 'RUNNING' and time.monotonic() >= h['lease_until']:\n        raise RuntimeError")
    service=replace(service,"if time.monotonic() >= h['lease_until']]","if h['state'] != 'RUNNING' and time.monotonic() >= h['lease_until']]")
    service=replace(service,"if time.monotonic() >= h['lease_until']:\n        h['cancel']", "if h['state'] != 'RUNNING' and time.monotonic() >= h['lease_until']:\n        h['cancel']")
    service=service.replace("h.update(state='COMPLETE', phase='READY_IN_AGENT_LAYER', result=result)","h.update(state='COMPLETE', phase='READY_IN_AGENT_LAYER', result=result, lease_until=time.monotonic()+LEASE_SECONDS)")
    service=replace(service,"h.update(state='CANCELLED' if code","h.update(lease_until=time.monotonic()+LEASE_SECONDS, state='CANCELLED' if code")
    service=replace(service,"if kind not in ('log','result','audit')","if kind not in ('log','audit')")
    service=replace(service,"import sample_worker","import agent_stage\nimport sample_worker")
    service=replace(service,"        worker.verify_code(ROOT)\n        return", """        worker.verify_code(ROOT)
        support = agent_stage.mounted_support()
        return""")
    service=replace(service,"'probe_purpose':sample_worker.PURPOSE,", "'mounted_support':support[1] if support else None, 'probe_purpose':sample_worker.PURPOSE,")
    service=replace(service,"            if ident in HANDLES:", """            support = agent_stage.mounted_support()
            if support and archives['support']!=support[1]:
                raise ValueError('MOUNTED_SUPPORT_BINDING')
            if ident in HANDLES:""")
    service=replace(service,"            HANDLES[ident] = h", """            if support:
                (folder/'support.zip').symlink_to(support[0])
                h['received']['support']=support[1]['bytes']
                h['mounted_support']=True
            HANDLES[ident] = h""")
    service=replace(service,"            if slot not in ('raw','support')", "            if slot=='support' and h.get('mounted_support'):\n                raise ValueError('MOUNTED_SUPPORT_READ_ONLY')\n            if slot not in ('raw','support')")
    server['service.py']=service.encode()
    worker=server['worker.py'].decode()
    # Bind the exact received archive hashes to the result, in addition to R10's per-file proof.
    worker=replace(worker,"'code_sha256': t.sha(workspace / 'CODE_PINS.json'), 'pipeline':",
        """'code_sha256': t.sha(workspace / 'CODE_PINS.json'),
           'archives': t.read(output/'stage-inputs.json'),
           'input_manifest_hashes': {s:t.digest(t.read(output/('input-'+s+'.json'))) for s in ('raw','support')}, 'pipeline':""")
    # G19/R5 consumes the generation. Avoid writing an unused second copy of every projected
    # search row to Oracle staging; Dataiku uses the target-specific projection.
    worker=worker.replace(" as full, oracle_query_package as query"," as full").replace(
        "# Heavy SQL projection runs here in GENOS; Dataiku only imports verified rows.",
        "# Dataiku reads the staged generation and applies its environment-specific G19 projection.")
    worker=replace(worker,"    query.export(generation, output / 'query', seconds=21600, database_only=True)\n","")
    worker=replace(worker,"    paths['query/query-data.db'] = output / 'query/query-data.db'\n","")
    worker=replace(worker,"    workspace=folder/'workspace';workspace.mkdir()","    t.write(folder/'stage-inputs.json',archives)\n    workspace=folder/'workspace';workspace.mkdir()")
    server['worker.py']=worker.encode()
    for n in ('agent_stage.py','prepare_support.py'):
        server[n]=(HERE/n).read_bytes()
    server['02_BACKEND/semantic_runtime/oracle_ords.py']=(REPO/'02_BACKEND/semantic_runtime/oracle_ords.py').read_bytes()
    for obsolete in ('GENOS_PIPELINE_CHECK.txt','VERIFY_PIPELINE_RELEASE.py','GUIDE.txt'):
        server.pop(obsolete)
    parents.update(files={n:sha(b) for n,b in server.items()},revision='genos-agent-layer-r1')
    server['CODE_PINS.json']=encode(parents)
    server_hash=pack(SERVICE,server)
    flow={k:v for k,v in gold.items() if k.startswith('engine/') or k in ('prod_config.py','prod_pipeline.py','registration_current.json')}
    prod=flow['prod_pipeline.py'].decode()
    prod=replace(prod,"            _, _, info = parts(cfg)", "            agent = base.read(root/'restore.json')['agent']")
    prod=replace(prod,"'input': input_binding(info), 'target': identity","'input': agent, 'target': identity")
    flow['prod_pipeline.py']=prod.encode()
    for name in ('agent_stage.py','flow_install.py','flow_runtime.py','document_input.py'):
        flow[name]=(HERE/name).read_bytes()
    flow['FILENAME_EXCEPTIONS.json']=server['00_SYSTEM/FILENAME_EXCEPTIONS.json']
    for name in ('transport.py','pipeline_coverage.py'):
        flow[name]=server[name]
    # Reuse precisely the bounded TLS/response contract of the existing DSS caller.
    runtime=recipes['recipes_runtime.py'].decode()
    def definition(source,name):
        node=next(n for n in ast.parse(source).body if getattr(n,'name','')==name)
        return ast.get_source_segment(source,node)
    wire=definition(runtime,'CheckedClient').replace('class CheckedClient(client.Client):',
        'class Wire:\n    def __init__(self,url,token):\n        self.url,self.token=url,token')
    bounded=definition(recipes['client/managed_job.py'].decode(),'bounded_read')
    flow['stage_wire.py']=('import json, socket, ssl, re, hashlib\nimport urllib.error, urllib.parse, urllib.request\nimport transport as t\n'+bounded+'\n'+definition(runtime,'NoRedirect')+'\n'+wire+'\n').encode()
    guard=(BASE/'gold_dev_test_20261104_r1/package/dev_guard.py').read_text()
    flow['dev_guard.py']=('from pathlib import Path\n'+definition(guard,'location')+'\n'+definition(guard,'check_disjoint')+'\n').encode()
    flow['SERVER_PIN.txt']=(sha(server['CODE_PINS.json'])+'\n').encode()
    flow['FLOW_MANIFEST.json']=encode({'files':{n:sha(b) for n,b in flow.items()}})
    flow_hash=pack(FLOW,flow)
    # Use a private extraction directory per recipe process: no concurrent writes or stale imports.
    boot=(BASE/'gold_zip_flow_20261104_r1/bootstrap_template.py').read_text()
    boot=boot.replace('DATAIKU_GOLD_ZIP_FLOW_20261104_R1.zip',FLOW).replace('@@ZIP_SHA@@',flow_hash)
    boot=replace(boot,"Path(tempfile.gettempdir()) / ('gold-zip-flow-code-'+ZIP_SHA256[:16])","Path(_code_dir.name)")
    boot=replace(boot,'FLOW_PACKAGE = open_package()',"_code_dir = tempfile.TemporaryDirectory(prefix='agent-flow-code-')\nFLOW_PACKAGE = open_package()")
    install=(HERE/'params.py').read_text()+'\nBOOTSTRAP = '+repr(boot)+'\nexec(BOOTSTRAP)\nfrom flow_install import install\ninstall(PARAMS,BOOTSTRAP)\n'
    (HERE/'INSTALL_DATAIKU_R1.txt').write_text(install)
    (HERE/'CODE_MANIFEST.json').write_bytes(encode({'server_zip':server_hash,'flow_zip':flow_hash,'server_pin':sha(server['CODE_PINS.json']),
        'flow_manifest':sha(flow['FLOW_MANIFEST.json']), 'worker.py':sha(server['worker.py']),'service.py':sha(server['service.py']),
        'deployed_revision':None,'field_generation':None,'target_checkout_commit':None}))
    installer=(HERE/'install_genos.py').read_text().replace('@@ARCHIVE_SHA@@',server_hash)
    (HERE/'GENOS_INSTALL_R1.txt').write_text('set -eu\npython3 - "$@" <<\'PYINSTALL\'\n'+installer+'PYINSTALL\n')
    return server_hash,flow_hash


if __name__=='__main__':
    print(*build())
