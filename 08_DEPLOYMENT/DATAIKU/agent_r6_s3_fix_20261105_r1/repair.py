"""Repair existing R6 output storage using its readable input folder's S3 location.

Preserves folder IDs, installed recipes, source ZIPs and the original request.
Never calls GENOS, Oracle, a model or a scenario. No object is moved or deleted.
"""
import ast
from contextlib import ExitStack
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import uuid

PREFIX = 'LGL_AGENT_R6_PROD'
STEPS = [('submit', '01_SUBMIT'), ('wait', '02_WAIT_AGENT'), ('load', '03_LOAD')]
PROBE = '_agent_r6_s3_fix/'
SAMPLES = {
    'LAW_SAMPLE_R2.zip': (16437, '2871a145d2cdac71ec15087b0bd92f5ac989bd1945e8a8333db4cf755c14f7bb'),
    'SAMPLE_SUPPORT_R2.zip': (7627, 'a8cbad59c476ef19b4c453f81c914505e23ecb20663db1e9cbb14adae98ebcf4'),
}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def location(params):
    return {k: copy.deepcopy(params[k]) for k in ('connection', 'bucket', 'path') if k in params}


def save(path, value):
    temporary = path.with_name('.repair-' + uuid.uuid4().hex)
    with temporary.open('xb') as stream:
        os.chmod(temporary, 0o600)
        stream.write(encode(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def effective(folder, connection):
    info = folder.get_info(sensitive_info=False)
    access = info.get('accessInfo', {})
    bucket, root = access.get('bucket'), access.get('root')
    if (info.get('type') != 'S3' or not isinstance(bucket, str) or not bucket
            or not isinstance(root, str) or not root or '${' in root):
        raise ValueError('RESOLVED_S3_BUCKET_AND_ROOT_REQUIRED')
    return (connection, bucket, '/' + root.strip('/') + '/')


def disjoint(locations):
    for i, (name, loc) in enumerate(locations):
        for other, ref in locations[:i]:
            if loc[:2] == ref[:2] and (loc[2].startswith(ref[2]) or ref[2].startswith(loc[2])):
                raise ValueError('S3_LOCATION_OVERLAP:' + other + ':' + name)


def installed(project, bootstrap):
    cfg = None
    for operation, step in STEPS:
        settings = project.get_recipe(PREFIX + '_' + step).get_settings()
        script = settings.get_code()
        tree = ast.parse(script)
        tail = tree.body[-1]
        call = tail.value if isinstance(tail, ast.Expr) else None
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != 'run' or len(call.args) != 2:
            raise ValueError('R6_RECIPE_ENTRY_CHANGED:' + operation)
        candidate = ast.literal_eval(call.args[1])
        if ast.literal_eval(call.args[0]) != operation or (cfg is not None and candidate != cfg):
            raise ValueError('R6_RECIPE_CONFIG_CHANGED:' + operation)
        expected = 'PARAMS = ' + repr({'CODE_FOLDER_ID': candidate['CODE_FOLDER_ID']}) + '\n' + bootstrap
        expected += '\nfrom flow_runtime import run\nrun(' + repr(operation) + ',' + repr(candidate) + ')\n'
        if script.rstrip() != expected.rstrip():
            raise ValueError('R6_RECIPE_CODE_CHANGED:' + operation)
        cfg = candidate
    if cfg['project'] != project.project_key or cfg['ENVIRONMENT'] != 'PROD' or cfg['INPUT_MODE'] != 'ZIP':
        raise ValueError('R6_PROJECT_OR_INPUT_CHANGED')
    if set(cfg['folders']) != {'submit', 'wait', 'load'} or len(set(cfg['folders'].values())) != 3:
        raise ValueError('R6_OUTPUT_FOLDER_IDS_INVALID')
    inputs = {cfg[k] for k in ('CODE_FOLDER_ID', 'INPUT_FOLDER_ID', 'SUPPORT_FOLDER_ID') if cfg[k]}
    if inputs.intersection(cfg['folders'].values()):
        raise ValueError('R6_INPUT_OUTPUT_COLLISION')
    folders = project.list_managed_folders()
    for operation, step in STEPS:
        found = [f['id'] for f in folders if f['name'] == PREFIX + '_' + step + '_OUT']
        if found != [cfg['folders'][operation]]:
            raise ValueError('R6_OUTPUT_FOLDER_CHANGED:' + operation)
    scenarios = [s for s in project.list_scenarios() if s['name'] == PREFIX + '_RUN_ALL']
    if len(scenarios) != 1:
        raise ValueError('R6_SCENARIO_NOT_UNIQUE')
    scenario = project.get_scenario(scenarios[0]['id'])
    expected = 'from dataiku.scenario import Scenario\ns=Scenario()\n'
    for operation, step in STEPS:
        expected += 's.build_folder(' + repr(cfg['folders'][operation]) + ', build_mode="NON_RECURSIVE_FORCED_BUILD", step_name=' + repr(step) + ', asynchronous=False, fail_fatal=True)\n'
    if scenario.get_settings().code != expected:
        raise ValueError('R6_SCENARIO_CODE_CHANGED')
    return cfg, scenario


def idle(project, scenario, cfg):
    if scenario.get_current_run() is not None:
        raise ValueError('R6_SCENARIO_IS_RUNNING')
    for job in project.list_jobs():
        definition = job.get('def', {})
        relevant = PREFIX in str(definition.get('id', '')) or any(
            o.get('id') in cfg['folders'].values() for o in definition.get('outputs', []))
        if relevant and job.get('stableState') is not True and job.get('state') not in ('DONE', 'FAILED', 'ABORTED'):
            raise ValueError('R6_JOB_IS_RUNNING')


def repair(dataiku, bootstrap, mode='REPAIR'):
    if mode not in ('REPAIR', 'ROLLBACK'):
        raise ValueError('MODE_MUST_BE_REPAIR_OR_ROLLBACK')
    project = dataiku.api_client().get_default_project()
    cfg, scenario = installed(project, bootstrap)
    idle(project, scenario, cfg)
    variables = dataiku.get_custom_variables()
    trial = variables.get('AGENT_FLOW_TRIAL', 'trial-001')
    if not isinstance(trial, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}', trial):
        raise ValueError('R6_TRIAL_INVALID')
    work = Path(cfg['WORK_DIR'])
    if not work.is_absolute():
        raise ValueError('R6_SHARED_WORK_DIR_REQUIRED')
    flow_dir = work / 'agent-layer-zip-r6' / project.project_key / 'PROD' / trial
    if not flow_dir.is_dir():
        raise ValueError('ORIGINAL_R6_SHARED_WORK_DIR_REQUIRED')
    with ExitStack() as stack:
        lock = stack.enter_context((flow_dir / 'flow.lock').open('a'))
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _repair(dataiku, project, scenario, cfg, bootstrap, mode, work, flow_dir)


def _repair(dataiku, project, scenario, cfg, bootstrap, mode, work, flow_dir):
    source_id = cfg['CODE_FOLDER_ID']
    source_settings = project.get_managed_folder(source_id).get_settings()
    source_location = location(source_settings.get_raw_params())
    if source_settings.type != 'S3' or not source_location.get('connection') or '${odbId}' not in source_location.get('path', ''):
        raise ValueError('SOURCE_S3_FOLDER_ID_PATH_TEMPLATE_REQUIRED')
    source = dataiku.Folder(source_id, ignore_flow=True)
    source_effective = effective(source, source_location['connection'])
    # Pin the actual readable bucket, even when the input inherits it implicitly.
    wanted = dict(source_location, bucket=source_effective[1])
    for name, (size, checksum) in SAMPLES.items():
        with source.get_download_stream(name) as stream:
            raw = stream.read(size + 1)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError('ORIGINAL_SAMPLE_ZIP_NOT_READABLE_OR_CHANGED:' + name)
    print('읽기 확인된 ZIP 폴더:', json.dumps({'id': source_id, **wanted,
          'effective_bucket': source_effective[1], 'effective_root': source_effective[2]}, ensure_ascii=False))
    binding = digest({'cfg': cfg, 'bootstrap_sha256': hashlib.sha256(bootstrap.encode()).hexdigest()})
    directory = work / 'agent-r6-s3-fix' / project.project_key / binding[:16]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    journal_path = directory / 'repair-state.json'
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else None
    if journal and (journal['binding'] != binding or journal['wanted'] != wanted or journal['source_id'] != source_id):
        raise ValueError('REPAIR_BINDING_CHANGED')
    if mode == 'ROLLBACK' and journal is None:
        raise ValueError('ROLLBACK_BACKUP_NOT_FOUND')
    observed, listing = {}, {}
    for operation, folder_id in cfg['folders'].items():
        settings = project.get_managed_folder(folder_id).get_settings()
        current = location(settings.get_raw_params())
        if settings.type != 'S3' or current.get('connection') != wanted['connection']:
            raise ValueError('R6_RESULT_CONNECTION_CHANGED:' + operation)
        if journal and current not in (journal['before'][operation], wanted):
            raise ValueError('RESULT_CHANGED_SINCE_BACKUP:' + operation)
        observed[operation] = current
        changing = current != (wanted if mode == 'REPAIR' else journal['before'][operation])
        remote = dataiku.Folder(folder_id, ignore_flow=True)
        try:
            names = remote.list_paths_in_partition()
        except Exception as exc:
            if '404' not in str(exc) or 'bucket' not in str(exc).lower():
                raise
            listing[operation] = 'UNKNOWN_BUCKET_404'
        else:
            listing[operation] = 'READABLE'
            if changing and any(not n.lstrip('/').startswith(PROBE) for n in names):
                raise ValueError('RESULT_HAS_EXISTING_CHECKPOINTS:' + operation)
    relocating = any(v != wanted for v in observed.values())
    if mode == 'REPAIR' and relocating:
        request = flow_dir / 'request.json'
        if not request.is_file():
            raise ValueError('ORIGINAL_PRE_OPEN_REQUEST_REQUIRED')
        state = json.loads(request.read_text())
        if state.get('opened'):
            raise ValueError('GENOS_JOB_ALREADY_OPENED_PRESERVE_CURRENT_LOCATIONS')
        if state.get('intent', {}).get('context', {}).get('project') != project.project_key:
            raise ValueError('ORIGINAL_REQUEST_PROJECT_CHANGED')
    if journal is None:
        journal = {'binding': binding, 'source_id': source_id, 'wanted': wanted,
                   'before': observed, 'old_listing': listing, 'folders': cfg['folders'], 'events': [], 'status': 'PLANNED'}
        save(journal_path, journal)
    print('원래 설정 백업:', str(journal_path))
    try:
        for operation, folder_id in cfg['folders'].items():
            idle(project, scenario, cfg)
            settings = project.get_managed_folder(folder_id).get_settings()
            if location(settings.get_raw_params()) not in (journal['before'][operation], wanted):
                raise ValueError('RESULT_CHANGED_DURING_REPAIR:' + operation)
            desired = wanted if mode == 'REPAIR' else journal['before'][operation]
            journal['status'] = 'APPLYING_' + mode
            journal['events'].append({'operation': operation, 'action': 'SAVE_PENDING', 'mode': mode})
            save(journal_path, journal)
            params = settings.get_raw_params()
            for key in ('connection', 'bucket', 'path'):
                if key in desired: params[key] = desired[key]
                else: params.pop(key, None)
            settings.save()
            if location(project.get_managed_folder(folder_id).get_settings().get_raw_params()) != desired:
                raise ValueError('STORAGE_SAVE_UNCONFIRMED:' + operation)
        if mode == 'REPAIR':
            locations = [(source_id, source_effective)]
            for folder_id in dict.fromkeys([cfg['INPUT_FOLDER_ID'], cfg['SUPPORT_FOLDER_ID']]):
                if folder_id and folder_id != source_id:
                    settings = project.get_managed_folder(folder_id).get_settings()
                    locations.append((folder_id, effective(dataiku.Folder(folder_id, ignore_flow=True), settings.get_raw_params()['connection'])))
            for operation, folder_id in cfg['folders'].items():
                current = effective(dataiku.Folder(folder_id, ignore_flow=True), wanted['connection'])
                if current[1] != source_effective[1]:
                    raise ValueError('OUTPUT_EFFECTIVE_BUCKET_MISMATCH:' + operation)
                locations.append((folder_id, current))
            disjoint(locations)
            for operation, folder_id in cfg['folders'].items():
                idle(project, scenario, cfg)
                remote = dataiku.Folder(folder_id, ignore_flow=True)
                probe_path = PROBE + binding[:16] + '/' + uuid.uuid4().hex + '.json'
                probe = encode({'folder_id': folder_id, 'operation': operation, 'binding': binding})
                remote.upload_stream(probe_path, io.BytesIO(probe))
                with remote.get_download_stream(probe_path) as stream:
                    if stream.read(len(probe) + 1) != probe:
                        raise ValueError('S3_PROBE_READBACK_MISMATCH:' + operation)
                journal['events'].append({'operation': operation, 'action': 'READ_WRITE_OK', 'probe': probe_path})
                save(journal_path, journal)
                print('결과 폴더 읽기/쓰기 확인:', operation, folder_id)
        journal['status'] = mode + '_COMPLETE'; save(journal_path, journal)
    except BaseException as exc:
        journal['status'] = 'FAILED'
        journal['events'].append({'action': 'FAILED', 'type': type(exc).__name__})
        save(journal_path, journal)
        print('복구 미완료. 설정 백업과 기존 작업 기록을 보존했습니다.')
        raise
    print('R6_S3_REPAIR_COMPLETE' if mode == 'REPAIR' else 'R6_S3_ROLLBACK_COMPLETE')
    if mode == 'REPAIR': print('다음: LGL_AGENT_R6_PROD_RUN_ALL을 같은 trial로 다시 실행하세요.')
    return journal
