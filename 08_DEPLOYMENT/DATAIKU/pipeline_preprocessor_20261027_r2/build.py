"""Focused successor of the sealed Dataiku-owned R1; never rebuild old releases."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'pipeline_stateless_20261027_r1'
SERVICE = 'GENOS_DATAIKU_COMPUTE_20261027_R2'
PACKAGE = 'DATAIKU_COMPUTE_RECIPES_20261027_R2.zip'
OLD_CODE = '868b23d7b0b4ac0d825a1a38644a582966118caad7796ca8b6e780df9f322dfa'


def sha(data): return hashlib.sha256(data).hexdigest()


def edit(source, before, after):
    if source.count(before) != 1:
        raise ValueError('SOURCE_ANCHOR: ' + before[:100])
    return source.replace(before, after)


def writezip(path, values):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in sorted(values.items()):
            if Path(name).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}:
                raise ValueError('JAVASCRIPT_EXCLUDED')
            info = zipfile.ZipInfo(name, (2026, 10, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, content)


def build():
    oldzip = BASE / 'GENOS_DATAIKU_COMPUTE_20261027_R1.zip'
    assert sha(oldzip.read_bytes()) == '516d594e54a619ab572febe89dec8d46a954fa3e4c6d39dc441ae7d2cfbd97db'
    with zipfile.ZipFile(oldzip) as z:
        original = {n.split('/', 1)[1]: z.read(n) for n in z.namelist()}
    assert sha(original['CODE_PINS.json']) == OLD_CODE
    oldpins = json.loads(original['CODE_PINS.json'])
    assert all(sha(original[n]) == h for n, h in oldpins['files'].items())
    payload = dict(original)
    worker = original['worker.py'].decode()
    worker = edit(worker, 'import transport as t', 'import transport as t\nimport parser_config')
    worker = edit(worker, ", '--pdf-parser', 'local'", '')
    worker = edit(worker, 'def compute(folder, run, archives):',
                  'def compute(folder, run, archives, parser_sha):')
    worker = edit(worker, '    pins=verify_code(root)\n    workspace=',
                  "    pins=verify_code(root)\n    parser_config.require(root, parser_sha)\n    print('PREPROCESSOR_CONFIG_OK: remote connectivity not yet checked', flush=True)\n    workspace=")
    worker = edit(worker, '    for phase,command in stage_commands(workspace,run):',
                  "    env.setdefault('GENOS_PDF_PARSER', 'preprocessor')\n    env.setdefault('GENOS_PREPROCESSOR_RESPONSE_MODE', 'docling')\n    for phase,command in stage_commands(workspace,run):")
    worker = edit(worker, "elif len(sys.argv)==5 and sys.argv[1]=='--compute':\n        compute(Path(sys.argv[2]),sys.argv[3],json.loads(sys.argv[4]))",
                  "elif len(sys.argv)==6 and sys.argv[1]=='--compute':\n        compute(Path(sys.argv[2]),sys.argv[3],json.loads(sys.argv[4]),sys.argv[5])")
    payload['worker.py'] = worker.encode()
    service = original['service.py'].decode()
    service = edit(service, 'import worker', 'import worker\nimport parser_config')
    service = edit(service, "json.dumps(h['archives'],sort_keys=True)]",
                   "json.dumps(h['archives'],sort_keys=True),h['parser_config_sha256']]")
    service = edit(service, "'s3_access':False, 'cancel_supported':True, 'replicas':1, 'workers':1}",
                   "'s3_access':False, 'cancel_supported':True, 'replicas':1, 'workers':1,\n                'preprocessor':parser_config.inspect(ROOT)}")
    service = edit(service, "            if ident in HANDLES:",
                   "            parser = parser_config.require(ROOT)\n            if data.get('parser_config_sha256') != parser['config_sha256']:\n                raise ValueError('PREPROCESSOR_CONFIG_CHANGED')\n            if ident in HANDLES:")
    service = edit(service, "h['max_rss_mb'] != memory:",
                   "h['max_rss_mb'] != memory or h['parser_config_sha256'] != parser['config_sha256']:")
    service = edit(service, "max_rss_mb=memory, state='RECEIVING'",
                   "parser_config_sha256=parser['config_sha256'], max_rss_mb=memory, state='RECEIVING'")
    service = edit(service, "            if h['state'] == 'RECEIVING':\n                if any(h['received']",
                   "            if h['state'] == 'RECEIVING':\n                parser_config.require(ROOT, h['parser_config_sha256'])\n                if any(h['received']")
    service = edit(service, "'phase':h.get('phase',''), 'error':h.get('error'), 'result':h.get('result'),",
                   "'phase':h.get('phase',''), 'error':h.get('error'), 'result':h.get('result'),\n            'parser_config_sha256':h['parser_config_sha256'],")
    payload['service.py'] = service.encode()
    payload['parser_config.py'] = (HERE / 'parser_config.py').read_bytes()
    pins = {**oldpins, 'files': {n: sha(b) for n, b in payload.items() if n != 'CODE_PINS.json'}}
    payload['CODE_PINS.json'] = (json.dumps(pins, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()
    code_sha = sha(payload['CODE_PINS.json'])
    writezip(HERE / (SERVICE + '.zip'), {SERVICE + '/' + n: b for n, b in payload.items()})
    for n in ('worker.py', 'service.py'):
        (HERE / n).write_bytes(payload[n])
    previous_package = BASE / 'DATAIKU_COMPUTE_RECIPES_20261027_R1.zip'
    assert sha(previous_package.read_bytes()) == 'e784f4236ae7945c94c4e60a731cbd2f0dbe418bc707707dc825ed50daf8e115'
    with zipfile.ZipFile(previous_package) as z:
        client = {n: z.read(n) for n in z.namelist()}
    controller = client['controller.py'].decode()
    controller = edit(controller, 'import recipes_runtime as r', 'import recipes_runtime as r\nimport checkpoint_upgrade')
    controller = edit(controller, "    store=ManagedJob(Scope(folder),name,identity)",
                      "    scoped=Scope(folder)\n    store=checkpoint_upgrade.open_store(scoped,name,identity,legacy_state(scoped,name))")
    controller = edit(controller, '    return value\n\n\ndef legacy_state',
                      "    parser=value.get('preprocessor') or {}\n    if parser.get('ready') is not True:\n        errors=parser.get('errors',[])\n        safe=[x for x in errors if isinstance(x,str) and re.fullmatch(r'PREPROCESSOR_[A-Z_]{1,60}',x)]\n        print('PREPROCESSOR_NOT_READY',','.join(safe),flush=True)\n        raise ValueError('GENOS_PREPROCESSOR_NOT_READY')\n    if not re.fullmatch(r'[0-9a-f]{64}',str(parser.get('config_sha256',''))):\n        raise ValueError('GENOS_PREPROCESSOR_HEALTH_CONTRACT')\n    return value\n\n\ndef legacy_state")
    controller = edit(controller, "    return {k:state[k] for k in ('instance','handle','handle_token','code_sha256')}",
                      "    value={k:state[k] for k in ('instance','handle','handle_token','code_sha256')}\n    if 'parser_config_sha256' in state:value['parser_config_sha256']=state['parser_config_sha256']\n    return value")
    controller = edit(controller, "    store=open_store(folders['structured'],name,identity);store.name=name",
                      "    prior=legacy_state(Scope(folders['structured']),name)\n    if prior and prior['value']['binding'] != identity:\n        health(wire)  # Check the new deployment before consuming the inherited retry.\n    store=open_store(folders['structured'],name,identity);store.name=name")
    controller = edit(controller, "'code_sha256':EXPECTED,'archives':{",
                      "'code_sha256':EXPECTED,'parser_config_sha256':h['preprocessor']['config_sha256'],'archives':{")
    controller = edit(controller, "{'binding','deadline','reserved_sql_calls','reserved_http_calls','migration_checked','legacy_checkpoint'}",
                      "{'binding','deadline','reserved_sql_calls','reserved_http_calls','migration_checked','legacy_checkpoint','upgrade_history'}")
    controller = edit(controller, "            raise ValueError('COMPUTE_'+current['state'])",
                      "            error=current.get('error','')\n            if isinstance(error,str) and re.fullmatch(r'[A-Z_]{1,80}',error):print('COMPUTE_ERROR',error,flush=True)\n            raise ValueError('COMPUTE_'+current['state'])")
    client['controller.py'] = controller.encode()
    client['checkpoint_upgrade.py'] = (HERE / 'checkpoint_upgrade.py').read_bytes()
    client['COMPUTE_CODE_SHA256.txt'] = (code_sha + '\n').encode()
    runtime = client['recipes_runtime.py'].decode()
    # Keep bounded public error codes; never echo arbitrary server text.
    runtime = edit(runtime, "'COMPUTE_AUTH'}", "'COMPUTE_AUTH','PREPROCESSOR_MODE_REQUIRED','PREPROCESSOR_ENDPOINT_REQUIRED','PREPROCESSOR_SHARED_ROOT_REQUIRED','PREPROCESSOR_CONFIG_INVALID','PREPROCESSOR_SHARED_ROOT_UNAVAILABLE','PREPROCESSOR_DOCLING_RESPONSE_REQUIRED','PREPROCESSOR_CONFIG_CHANGED'}")
    client['recipes_runtime.py'] = runtime.encode()
    updater = client['updater.py'].decode()
    updater = edit(updater, "        ('unpack','LEGAL_01_UNZIP_RAW_R1',('landing',),'raw'),\n", '')
    start = updater.index('def variants('); end = updater.index('\n\ndef update(', start)
    updater = updater[:start] + "def variants(stage,cfg,ref,resume):\n    return [ref['prior_compute_bootstrap']+'\\nrun_recipe('+repr(stage)+', '+repr(cfg)+')\\n']\n" + updater[end:]
    updater = edit(updater, "BACKUP='_pipeline/dataiku-owned-v1/install/before.json'",
                   "BACKUP='_pipeline/dataiku-owned-v1/install/preprocessor-r2-before.json'")
    client['updater.py'] = updater.encode()
    ref = json.loads(client['REFERENCE.json'])
    ref['prior_compute_bootstrap'] = (BASE / 'bootstrap.txt').read_text()
    client['REFERENCE.json'] = (json.dumps(ref) + '\n').encode()
    # Refresh the package's own inventory (it originally predates compute R1).
    client['PACKAGE_FILES.json'] = (json.dumps({n: sha(b) for n, b in client.items() if n != 'PACKAGE_FILES.json'}, sort_keys=True, indent=2) + '\n').encode()
    writezip(HERE / PACKAGE, client)
    for n in ('controller.py', 'updater.py'):
        (HERE / n).write_bytes(client[n])
    bootstrap = (BASE / 'bootstrap.txt').read_text()
    bootstrap = edit(bootstrap, 'DATAIKU_COMPUTE_RECIPES_20261027_R1.zip', PACKAGE)
    bootstrap = edit(bootstrap, sha(previous_package.read_bytes()), sha((HERE / PACKAGE).read_bytes()))
    bootstrap = edit(bootstrap, 'PACKAGE_BYTES = 280026', 'PACKAGE_BYTES = ' + str((HERE / PACKAGE).stat().st_size))
    (HERE / 'bootstrap.txt').write_text(bootstrap)
    install = "# LEGAL_RAG Python 노트북. 02를 중지한 뒤 새 셀에서 전체 실행.\nACTION = 'apply' # apply / inspect / rollback\n" + bootstrap + '\nBOOTSTRAP = ' + repr(bootstrap) + '''
work, root = verified_package()
sys.path.insert(0,str(root))
# A previous notebook may still hold R1's updater module. Load these verified bytes explicitly.
spec=importlib.util.spec_from_file_location('pipeline_preprocessor_r2_updater',root/'updater.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.update(dataiku.api_client().get_project('LEGAL_RAG'),root,BOOTSTRAP,ACTION)
print('PREPROCESSOR_R2_FLOW_READY: GENOS 환경변수/리비전 적용 뒤 00 → 02 → 03')
'''
    (HERE / 'DATAIKU_PREPROCESSOR_INSTALL_20261027_R2.txt').write_text(install)
    control = '# LEGAL_RAG Python 노트북. 기본값은 조회입니다.\nACTION = "status" # status / cancel / retry\n' + bootstrap + '''
work, root = verified_package()
sys.path[:0]=[str(root),str(root/'client'),str(root/'client/02_BACKEND')]
for name in ('control','controller','checkpoint_upgrade','recipes_runtime','updater'):
    sys.modules.pop(name,None)
import control
control.run(ACTION,root,work)
'''
    (HERE / 'DATAIKU_PREPROCESSOR_CONTROL_20261027_R2.txt').write_text(control)
    for name, content in payload.items():
        if name.endswith('.py'): compile(content, name, 'exec')
    for n in ('parser_config.py', 'checkpoint_upgrade.py', 'controller.py', 'updater.py',
              'DATAIKU_PREPROCESSOR_INSTALL_20261027_R2.txt', 'DATAIKU_PREPROCESSOR_CONTROL_20261027_R2.txt'):
        ast.parse((HERE / n).read_text(), feature_version=(3, 9))
    result = {'baseline_code_sha256': OLD_CODE, 'code_sha256': code_sha,
              'service_changed': [n for n, b in payload.items() if b != original.get(n)],
              'service_files': len(payload), 'service_unchanged': sum(payload.get(n) == b for n, b in original.items()),
              'files': {n: {'sha256': sha((HERE / n).read_bytes()), 'bytes': (HERE / n).stat().st_size}
                        for n in (SERVICE + '.zip', PACKAGE, 'DATAIKU_PREPROCESSOR_INSTALL_20261027_R2.txt', 'DATAIKU_PREPROCESSOR_CONTROL_20261027_R2.txt')}}
    (HERE / 'BUILD.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': build()
