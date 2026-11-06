"""Extend the exact R4 delivery; leave all historical packages unchanged."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'agent_layer_return_20261105_r4'
SERVER = 'GENOS_AGENT_ORDS_R5.zip'
FLOW = 'DATAIKU_AGENT_GOLD_FLOW_R5.zip'
PROTOCOL = 'genos-agent-ords-v1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError('PARENT_SOURCE_CHANGED:' + old[:80])
    return text.replace(old, new)


def unpack(name, expected):
    raw = (PARENT / name).read_bytes()
    if sha(raw) != expected:
        raise ValueError('PARENT_ZIP_HASH:' + name)
    with zipfile.ZipFile(PARENT / name) as z:
        return {n: z.read(n) for n in z.namelist()}


def pack(path, files):
    with zipfile.ZipFile(path, 'w') as z:
        for n, raw in sorted(files.items()):
            if Path(n).suffix.lower() in {'.zip', '.js', '.jsx', '.mjs', '.cjs'}:
                raise ValueError('NESTED_OR_JS_MEMBER:' + n)
            z.writestr(zipfile.ZipInfo(n), raw, compress_type=zipfile.ZIP_DEFLATED)
    return sha(path.read_bytes())


def build():
    server = unpack('GENOS_AGENT_RETURN_R4.zip', '0488bd8c0546217f916815250a87cbb0328f0cc74a5a6353371711ff1e00e8af')
    flow = unpack('DATAIKU_AGENT_FLOW_R4.zip', '654d41f28916b07b897210d43e8b329561cf884d613027edb1bf33c299a5ee04')
    svc = server['service.py'].decode().replace('dataiku-agent-return-v1', PROTOCOL)
    svc = replace(svc, 'import agent_stage\n', 'import agent_stage\nimport agent_ords\n')
    svc = replace(svc, '        import json\n        command=', "        agent_ords.preflight(h, t.sha(ROOT/'CODE_PINS.json'))\n        import json\n        command=")
    svc = replace(svc, "        with GUARD:\n            h.update(state='COMPLETE', phase='RETURN_READY', result=result, lease_until=time.monotonic()+LEASE_SECONDS)", "        h['computed_result'] = result\n        run_publish(h)")
    at = svc.index('\ndef reap():')
    svc = svc[:at] + '''
def run_publish(h):
    try:
        resource_check(h)
        worker.verify_code(ROOT)
        h['phase'] = 'ORDS_AGENT_WRITE'
        agent_ords.publish(h, t.sha(ROOT/'CODE_PINS.json'), h['computed_result'], lambda: resource_check(h))
        with GUARD:
            h.update(state='COMPLETE', phase='AGENT_READY', result=h['computed_result'], error=None,
                     lease_until=time.monotonic()+LEASE_SECONDS)
    except BaseException as exc:
        code = str(exc)
        if not re.fullmatch(r'[A-Z_]{1,80}', code):
            code = 'AGENT_WRITE_' + type(exc).__name__.upper()
        with GUARD:
            h.update(state='CANCELLED' if h['cancel'].is_set() else 'STAGE_PENDING',
                     phase='AGENT_WRITE_PENDING', error=code, lease_until=time.monotonic()+LEASE_SECONDS)
    finally:
        h['ended'] = time.time()

''' + svc[at:]
    svc = replace(svc, "'oracle_access':False, 'result_destination':'DATAIKU'", "'oracle_access':True, 'result_destination':agent_stage.TABLE, 'agent_layer':agent_ords.configuration()")
    svc = replace(svc, "        elif op == 'CANCEL':", """        elif op == 'PUBLISH':
            if h['state'] == 'STAGE_PENDING':
                resource_check(h)
                if not h.get('computed_result'):
                    raise ValueError('NO_SAVED_RESULT_TO_RESUME')
                if sum(x['state']=='RUNNING' for x in HANDLES.values()) >= MAX_RUNNING:
                    raise ValueError('COMPUTE_CAPACITY')
                h['state']='RUNNING'
                threading.Thread(target=run_publish,args=(h,),daemon=True).start()
            elif h['state'] not in ('RUNNING','COMPLETE'):
                raise ValueError('NO_SAVED_RESULT_TO_RESUME')
        elif op == 'CANCEL':""")
    svc = replace(svc, "            if h['state'] == 'RECEIVING':\n                h.update(state='CANCELLED'", "            if h['state'] in ('RECEIVING','STAGE_PENDING'):\n                h.update(state='CANCELLED'")
    # Result data is consumed exclusively from Oracle Agent; HTTP READ remains
    # available for existing compute logs and failure audits.
    svc = replace(svc, "kind not in ('log','result','audit')", "kind not in ('log','audit')")
    server['service.py'] = svc.encode()
    server['agent_ords.py'] = (HERE / 'agent_ords.py').read_bytes()
    pins = json.loads(server.pop('CODE_PINS.json'))
    pins.update(revision='genos-agent-ords-r5', files={n: sha(b) for n, b in server.items()})
    server['CODE_PINS.json'] = encode(pins)
    server_sha = pack(HERE / SERVER, server)
    runtime = flow['flow_runtime.py'].decode().replace('dataiku-agent-return-v1', PROTOCOL).replace('agent-layer-return-r4', 'agent-layer-ords-r5')
    runtime = replace(runtime, "not health['preprocessor']['ready']:", "not health['preprocessor']['ready'] or not health.get('agent_layer',{}).get('configured'):")
    runtime = replace(runtime, '    from dataiku_return import receive', '    from agent_wait import receive')
    runtime = replace(runtime, "'load':{'wait','load'}}[operation]", "'load':{'wait','load'},'resume':{'submit','wait'}}[operation]")
    runtime = replace(runtime, "result={'submit':submit,'wait':wait_ready,'load':load}[operation]", "from agent_wait import resume\n        result={'submit':submit,'wait':wait_ready,'load':load,'resume':resume}[operation]")
    flow['flow_runtime.py'] = runtime.encode()
    flow['flow_install.py'] = flow['flow_install.py'].replace(b'LGL_AGENT_R4_', b'LGL_AGENT_R5_')
    flow.pop('dataiku_return.py')
    for name in ('agent_wait.py', 'flow_setup.py'):
        flow[name] = (HERE / name).read_bytes()
    flow['SERVER_PIN.txt'] = (sha(server['CODE_PINS.json']) + '\n').encode()
    flow.pop('FLOW_MANIFEST.json')
    flow['FLOW_MANIFEST.json'] = encode({'files': {n: sha(b) for n, b in flow.items()}})
    flow_sha = pack(HERE / FLOW, flow)
    tree = ast.parse((PARENT / 'DATAIKU_SETUP_R4.txt').read_text())
    bootstrap = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == 'BOOTSTRAP'))
    bootstrap = bootstrap.replace('DATAIKU_AGENT_FLOW_R4.zip', FLOW).replace('654d41f28916b07b897210d43e8b329561cf884d613027edb1bf33c299a5ee04', flow_sha)
    params = dict(CODE_FOLDER_ID='', INPUT_FOLDER_ID='', SUPPORT_FOLDER_ID='', DOCUMENT_PREFIX='',
                  GOLD_OWNER='SIDDS', AGENT_CONNECTION='AIDP', TARGET_CONNECTION='AIDP', EXPECTED_DB_USER='PIDD2APP',
                  EMBED_MODEL='openai:genos-embedding:embedding-kure-v1', EMBED_DIMENSIONS=1024)
    (HERE / 'DATAIKU_SETUP_R5.txt').write_text('# Dataiku Python 노트북: 기존 실제 폴더 ID와 운영 설정을 입력합니다.\nPARAMS = ' + repr(params) + '\nBOOTSTRAP = ' + repr(bootstrap) + "\nexec(BOOTSTRAP)\nfrom flow_setup import install_pipeline\ncfg = install_pipeline(PARAMS, BOOTSTRAP)\n")
    (HERE / 'DATAIKU_RESUME_STAGE_R5.txt').write_text("# R5 설치 셀을 실행한 같은 프로젝트·trial에서 저장만 명시적으로 재개합니다.\n# 계산과 모델은 다시 실행하지 않습니다. cfg는 설치 셀의 기존 값을 사용합니다.\nfrom flow_runtime import run\nRESULT = run('resume', cfg)\n")
    deploy = (PARENT / 'GENOS_DEPLOY_R4.txt').read_text()
    for old, new in [('GENOS_AGENT_RETURN_R4.zip', SERVER), ('0488bd8c0546217f916815250a87cbb0328f0cc74a5a6353371711ff1e00e8af', server_sha),
                     ('edf50a1925b58bf9148fd9f74b1e766c15f465f2bb25427d010b7d7c8ce41d8e', sha(server['CODE_PINS.json'])),
                     ('genos-agent-return-r4', 'genos-agent-ords-r5'), ('pinned R4 return payload', 'pinned R5 ORDS payload'),
                     ('Deploy R4 Dataiku result-return pipeline', 'Deploy R5 GENOS ORDS Agent to Gold pipeline'), ('R4_ZIP_HASH_MISMATCH', 'R5_ZIP_HASH_MISMATCH')]:
        if old not in deploy:
            raise ValueError('INSTALLER_PARENT_CHANGED:' + old)
        deploy = deploy.replace(old, new)
    (HERE / 'GENOS_DEPLOY_R5.txt').write_text(deploy)
    pipeline = dict(schema_version='agent-layer-gold-delivery-v1', protocol=PROTOCOL,
        server_entrypoint='service.py:service', dataiku_setup='DATAIKU_SETUP_R5.txt',
        manual_scenario='LGL_AGENT_R5_PROD_RUN_ALL',
        input='Existing loose-document folder and exact production PIPELINE_SUPPORT.zip/receipt',
        stages=[
            dict(order=1, recipe='01_SUBMIT', entrypoint='flow_runtime.run:submit',
                 output='Bound raw/support upload and asynchronous GENOS job'),
            dict(order=2, entrypoint='service.run_compute -> agent_ords.publish', writer='GENOS ORDS',
                 output='SIDDA.LGL_PIPE_RESULT_A immutable parts; SEQ_NO=0 READY last',
                 batch_parts=8, part_bytes=72000, consumer='02_WAIT_AGENT'),
            dict(order=3, recipe='02_WAIT_AGENT', entrypoint='flow_runtime.run:wait -> agent_wait.receive',
                 output='Oracle READY receipt; no result HTTP READ or DSS Agent INSERT'),
            dict(order=4, recipe='03_LOAD', entrypoint='flow_runtime.run:load -> prod_pipeline.execute',
                 writer='Dataiku TARGET_CONNECTION',
                 output='Explicit owner Gold source/search/publication/vector tables and verified report.json')],
        failure_contract=dict(automatic_write_retries=0, recompute_on_publish_resume=False,
            resume_entrypoint="flow_runtime.run('resume', cfg) -> authenticated PUBLISH",
            retained='Original deadline, job, code/input digests, computed result, SQL journal and partial rows',
            conflicts='Rollback; preserve original bytes; no UPDATE/DELETE/TRUNCATE',
            pod_loss_before_READY='Original handle cannot be resumed; retain failure and use a new trial',
            ready_recovery='DSS wait/load read Agent even when GENOS is unavailable'),
        field_activation='Explicit new GENOS revision and manual DSS scenario; no local RAG MAIN activation')
    (HERE / 'PIPELINE.json').write_bytes(encode(pipeline))
    (HERE / 'RELEASE.json').write_bytes(encode(dict(protocol=PROTOCOL, parent='agent_layer_return_20261105_r4',
        code_zip=server_sha, code_pin=sha(server['CODE_PINS.json']), flow_zip=flow_sha,
        database_writer='GENOS ORDS', agent_table='SIDDA.LGL_PIPE_RESULT_A', gold_writer='Dataiku AIDP',
        gold_owner='SIDDS (explicit PARAMS)', field_revision=None, actual_checkout_commit=None,
        pipeline_spec='PIPELINE.json', pipeline_sha256=sha(encode(pipeline)),
        data_generation='per-job raw/support digest binding', server_files=len(server), flow_files=len(flow))))


if __name__ == '__main__':
    build()
