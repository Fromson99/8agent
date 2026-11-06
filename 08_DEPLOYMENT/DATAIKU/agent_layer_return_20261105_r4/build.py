"""Seal the GENOS return API and the DSS-owned AIDP staging/loader flow."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

HERE=Path(__file__).resolve().parent
R2=HERE.parent/'agent_layer_async_20261105_r2'
R3=HERE.parent/'agent_layer_async_20261105_r3'
SERVER='GENOS_AGENT_RETURN_R4.zip'
FLOW='DATAIKU_AGENT_FLOW_R4.zip'

def sha(data):return hashlib.sha256(data).hexdigest()
def encode(obj):return (json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def replace(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)
def unpack(path,pin):
    assert sha(path.read_bytes())==pin
    with zipfile.ZipFile(path) as z:return {n:z.read(n) for n in z.namelist()}
def pack(path,files):
    with zipfile.ZipFile(path,'w') as z:
        for n,b in sorted(files.items()):
            assert Path(n).suffix.lower() not in ('.zip','.js','.jsx','.mjs','.cjs'),n
            z.writestr(zipfile.ZipInfo(n),b,compress_type=zipfile.ZIP_DEFLATED)
    return path.read_bytes()

def build():
    server=unpack(R2/'GENOS_AGENT_ASYNC_R2.zip','8f197834305fdf1bfe29ff69ada903cfc4a57832dc5ce8a45a237aad03e58e3d')
    flow=unpack(R2/'DATAIKU_AGENT_FLOW_R2.zip','da993fde1d7b54b8af96c5382ba9abfeb9cb39d815ef7835e2cb39088a797e6a')
    svc=server['service.py'].decode().replace('genos-agent-layer-v1','dataiku-agent-return-v1')
    start=svc.index('        import agent_stage\n',svc.index('def run_compute'))
    end=svc.index('    except BaseException as exc:',start)
    svc=svc[:start]+"""        with GUARD:
            h.update(state='COMPLETE', phase='RETURN_READY', result=result, lease_until=time.monotonic()+LEASE_SECONDS)
"""+svc[end:]
    svc=replace(svc,"kind not in ('log','audit')","kind not in ('log','result','audit')")
    svc=replace(svc,"'s3_access':False,", "'s3_access':False, 'oracle_access':False, 'result_destination':'DATAIKU',")
    server['service.py']=svc.encode()
    # Shared part/checksum contract remains identical; the obsolete ORDS publisher
    # is absent from both distributions. Only DSS invokes write_result now.
    stage=server['agent_stage.py'].decode()
    start=stage.index('def publish(')
    end=stage.index('def write_result(',start)
    stage=stage[:start]+stage[end:]
    server['agent_stage.py']=flow['agent_stage.py']=stage.encode()
    pins=json.loads(server.pop('CODE_PINS.json'))
    pins.update(revision='genos-dataiku-return-r4',files={k:sha(v) for k,v in server.items()})
    server['CODE_PINS.json']=encode(pins)
    code=pack(HERE/SERVER,server)
    flow.pop('FLOW_MANIFEST.json')
    runtime=flow['flow_runtime.py'].decode().replace('genos-agent-layer-v1','dataiku-agent-return-v1').replace('agent-layer-r2','agent-layer-return-r4')
    runtime=replace(runtime,"    return Wire(variables['AGENT_PIPELINE_URL'],variables['AGENT_PIPELINE_TOKEN'])", """    for prefix in ('AGENT_PIPELINE','LEGAL_PIPELINE'):
        url,token=variables.get(prefix+'_URL'),variables.get(prefix+'_TOKEN')
        if url or token:
            if not url or not token:
                raise ValueError(prefix+'_URL_AND_TOKEN_REQUIRED_TOGETHER')
            return Wire(url,token)
    raise ValueError('GENOS_PIPELINE_URL_AND_TOKEN_REQUIRED')""")
    start=runtime.index('def wait_ready(')
    end=runtime.index('def validate_intent(',start)
    runtime=runtime[:start]+"""def wait_ready(cfg, paths, folders, variables, trial):
    from dataiku_return import receive
    return receive(cfg,paths,folders,variables,trial)


"""+runtime[end:]
    flow['flow_runtime.py']=runtime.encode()
    flow['flow_install.py']=flow['flow_install.py'].replace(b'LGL_AGENT_R2_',b'LGL_AGENT_R4_')
    setup=flow['agent_setup.py'].decode()
    setup=setup[:setup.index('def setup(config):')].replace('Create the R2 staging table through a Dataiku Oracle connection, then verify it.','Verify the DSS-owned staging table schema.')
    flow['agent_setup.py']=setup.encode()
    for n in ('sample_setup.py','dataiku_return.py'):flow[n]=(HERE/n).read_bytes()
    flow['SERVER_PIN.txt']=(sha(server['CODE_PINS.json'])+'\n').encode()
    flow['FLOW_MANIFEST.json']=encode({'files':{k:sha(v) for k,v in flow.items()}})
    flowzip=pack(HERE/FLOW,flow)
    tree=ast.parse((R2/'DATAIKU_SETUP_R2.txt').read_text())
    boot=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id=='BOOTSTRAP'))
    boot=boot.replace('DATAIKU_AGENT_FLOW_R2.zip',FLOW).replace('da993fde1d7b54b8af96c5382ba9abfeb9cb39d815ef7835e2cb39088a797e6a',sha(flowzip))
    (HERE/'DATAIKU_SETUP_R4.txt').write_text("# Dataiku 새 Python 노트북. 세 ZIP을 올린 Managed Folder ID 한 곳만 입력합니다.\nCODE_FOLDER_ID = ''\nPARAMS = {'CODE_FOLDER_ID': CODE_FOLDER_ID}\nBOOTSTRAP = "+repr(boot)+"\nexec(BOOTSTRAP)\nfrom sample_setup import install_sample\ncfg = install_sample(CODE_FOLDER_ID,BOOTSTRAP)\n")
    deploy=(R3/'GENOS_DEPLOY_R3.txt').read_text()
    for a,b in [('GENOS_AGENT_ASYNC_R2.zip',SERVER),('8f197834305fdf1bfe29ff69ada903cfc4a57832dc5ce8a45a237aad03e58e3d',sha(code)),('02878fa366c0d4ba76b394b145ee7fc7c2d726ce603b886fc93d54f2471aa6cb',sha(server['CODE_PINS.json'])),('genos-agent-r2-overwrite-r3','genos-agent-return-r4'),('pinned R2 payload','pinned R4 return payload'),('Deploy R2 Agent Layer pipeline','Deploy R4 Dataiku result-return pipeline'),('R2_ZIP_HASH_MISMATCH','R4_ZIP_HASH_MISMATCH')]:
        assert a in deploy,a
        deploy=deploy.replace(a,b)
    (HERE/'GENOS_DEPLOY_R4.txt').write_text(deploy)
    for n in ('LAW_SAMPLE_R2.zip','SAMPLE_SUPPORT_R2.zip'):shutil.copyfile(R2/n,HERE/n)
    sample=json.loads(flow['SAMPLE.json'])
    (HERE/'RELEASE.json').write_bytes(encode(dict(code_zip=sha(code),code_pin=sha(server['CODE_PINS.json']),flow_zip=sha(flowzip),sample=sample,
        protocol='dataiku-agent-return-v1',database_writer='Dataiku SQLExecutor2 AIDP',database_login='PIDD2APP',agent_table='SIDDA.LGL_PIPE_RESULT_A',
        source_commit='002dcf07705688c637bc878b4b6f372231cb2c3c',field_revision=None)))

if __name__=='__main__':build()
