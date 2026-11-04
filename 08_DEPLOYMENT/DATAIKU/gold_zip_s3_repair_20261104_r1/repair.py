"""Pre-run R1 folder-location repair. No SQL, model call or scenario launch."""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import uuid


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')


def location(params):
    return {k: copy.deepcopy(params[k]) for k in ('connection', 'bucket', 'path') if k in params}


def apply_location(settings, wanted):
    params = settings.get_raw_params()
    for key in ('connection', 'bucket', 'path'):
        if key in wanted:
            params[key] = wanted[key]
        else:
            params.pop(key, None)
    settings.save()


def save(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('wb') as stream:
        stream.write(encode(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def repair(dataiku, bootstrap, stages, mode='REPAIR', backup_root=None):
    if mode not in ('REPAIR', 'ROLLBACK'):
        raise ValueError('MODE must be REPAIR or ROLLBACK')
    project = dataiku.api_client().get_default_project()
    if project.project_key != 'LEGAL_RAG':
        raise ValueError('PROJECT_MUST_BE_LEGAL_RAG')
    cfg = None
    # Parse literal configuration, never execute installed recipe code.
    for stage, code, label, table_keys in stages:
        settings = project.get_recipe('G19ZIP_' + code).get_settings()
        script = settings.get_code()
        tree = ast.parse(script)
        tail = tree.body[-1]
        if not isinstance(tail, ast.Expr) or not isinstance(tail.value, ast.Call):
            raise ValueError('RECIPE_LAYOUT_CHANGED:' + code)
        call = tail.value
        if not isinstance(call.func, ast.Name) or call.func.id != 'run' or len(call.args) != 2:
            raise ValueError('RECIPE_ENTRY_CHANGED:' + code)
        candidate = ast.literal_eval(call.args[1])
        if ast.literal_eval(call.args[0]) != stage or (cfg is not None and candidate != cfg):
            raise ValueError('RECIPE_CONFIG_CHANGED:' + code)
        cfg = candidate
        expected = ('PARAMS = ' + repr(cfg['params']) + '\n' + bootstrap
                    + '\nfrom zip_runtime import run\nrun(' + repr(stage) + ',' + repr(cfg) + ')\n')
        if script != expected:
            raise ValueError('RECIPE_CODE_CHANGED:' + code)
    if cfg['project'] != project.project_key or cfg['version'] != 'gold-zip-flow-20261104-r1':
        raise ValueError('FLOW_IDENTITY_CHANGED')
    expected_ids = cfg['folders']
    if set(expected_ids) != {row[0] for row in stages} or len(set(expected_ids.values())) != 8:
        raise ValueError('RESULT_FOLDER_IDS_INVALID')
    source_id = cfg['params']['CODE_FOLDER_ID']
    if source_id in expected_ids.values() or cfg['input_folder'] in expected_ids.values():
        raise ValueError('INPUT_RESULT_FOLDER_COLLISION')
    folders = project.list_managed_folders()
    for stage, code, _, _ in stages:
        found = [f for f in folders if f['name'] == 'G19ZIP_' + code + '_RESULT']
        if len(found) != 1 or found[0]['id'] != expected_ids[stage]:
            raise ValueError('RESULT_FOLDER_CHANGED:' + stage)
    scenario_name = 'G19ZIP_RUN_ALL · ZIP부터 Gold 벡터까지'
    found = [s for s in project.list_scenarios() if s['name'] == scenario_name]
    if len(found) != 1:
        raise ValueError('SCENARIO_NOT_UNIQUE')
    scenario = project.get_scenario(found[0]['id'])
    expected_scenario = 'from dataiku.scenario import Scenario\ns = Scenario()\n'
    for stage, code, label, _ in stages:
        expected_scenario += ('s.build_folder(' + repr(expected_ids[stage])
            + ',build_mode="NON_RECURSIVE_FORCED_BUILD",step_name=' + repr(code + ' · ' + label)
            + ',asynchronous=False,fail_fatal=True)\n')
    if scenario.get_settings().code != expected_scenario:
        raise ValueError('SCENARIO_CODE_CHANGED')

    def before_run_only():
        if scenario.get_current_run() is not None or scenario.get_last_runs(limit=1):
            raise ValueError('SCENARIO_ALREADY_STARTED: 기존 실행/체크포인트를 보존하고 중단합니다.')

    before_run_only()
    workspace = Path(cfg['params'].get('WORK_DIR') or
                     (Path(tempfile.gettempdir()) / 'legal-gold-zip-flow' / project.project_key))
    if (workspace / 'workspace.json').exists():
        raise ValueError('LOCAL_WORKSPACE_ALREADY_STARTED')
    source_settings = project.get_managed_folder(source_id).get_settings()
    wanted = location(source_settings.get_raw_params())
    if source_settings.type != 'S3' or wanted.get('path') != '/dataiku/${projectKey}/${odbId}':
        raise ValueError('SOURCE_S3_TEMPLATE_DIFFERS_FROM_FIELD_PHOTO')
    if not wanted.get('connection'):
        raise ValueError('SOURCE_CONNECTION_MISSING')
    # AccessInfo is filtered explicitly: never emit credentials or the whole settings object.
    source_info = dataiku.Folder(source_id, ignore_flow=True).get_info(sensitive_info=False)
    source_access = source_info.get('accessInfo', {})
    if not all(isinstance(source_access.get(k), str) and source_access[k] for k in ('bucket', 'root')):
        raise ValueError('SOURCE_EFFECTIVE_BUCKET_OR_ROOT_MISSING')
    print('업로드 폴더:', json.dumps({'id': source_id, **wanted,
          'resolved_bucket': source_access.get('bucket'), 'resolved_root': source_access.get('root')}, ensure_ascii=False))
    digest = hashlib.sha256(encode(cfg)).hexdigest()
    directory = Path(backup_root or (Path(tempfile.gettempdir()) / 'gold-zip-s3-repair')) / project.project_key / digest[:16]
    directory.mkdir(parents=True, exist_ok=True)
    journal_path = directory / 'repair-state.json'
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else None
    if journal is not None and (journal['cfg_sha256'] != digest or journal['wanted'] != wanted):
        raise ValueError('REPAIR_BINDING_CHANGED')
    if mode == 'ROLLBACK' and journal is None:
        raise ValueError('ROLLBACK_BACKUP_NOT_FOUND')
    observed = {}
    for stage, folder_id in expected_ids.items():
        settings = project.get_managed_folder(folder_id).get_settings()
        current = location(settings.get_raw_params())
        if settings.type != 'S3' or current.get('connection') != wanted['connection']:
            raise ValueError('RESULT_CONNECTION_CHANGED:' + stage)
        old_path = '/' + project.project_key + '/gold_zip_flow_20261104_r1/' + stage
        if journal is None:
            if current.get('path') != old_path:
                raise ValueError('EXPECTED_ORIGINAL_R1_PATH:' + stage)
        elif current not in (journal['before'][stage], wanted):
            raise ValueError('RESULT_LOCATION_CHANGED:' + stage)
        observed[stage] = current
        remote = dataiku.Folder(folder_id, ignore_flow=True)
        try:
            names = remote.list_paths_in_partition()
        except Exception as exc:
            # The photographed initial 404 may hide old storage contents. Preserve that
            # location and its config; never delete/move objects or assume it is empty.
            message = str(exc).lower()
            if current.get('path') != old_path or '404' not in message or 'bucket' not in message:
                raise
            print('이전 위치 목록 미확인(버킷404), 파일 이동/삭제 없음:', stage)
        else:
            unexpected = [n for n in names if n.lstrip('/') != 'installation.json'
                          and not n.lstrip('/').startswith('_gold_zip_s3_repair/')]
            if unexpected:
                raise ValueError('RESULT_HAS_EXISTING_DATA:' + stage)
    if journal is None:
        journal = {'cfg_sha256': digest, 'wanted': wanted, 'before': observed,
                   'folders': expected_ids, 'status': 'PLANNED', 'events': []}
        save(journal_path, journal)
    print('원복 설정/실행 기록:', str(journal_path))
    resolved_locations = set()
    try:
        for stage, folder_id in expected_ids.items():
            before_run_only()
            settings = project.get_managed_folder(folder_id).get_settings()
            if location(settings.get_raw_params()) not in (journal['before'][stage], wanted):
                raise ValueError('RESULT_CHANGED_DURING_REPAIR:' + stage)
            desired = wanted if mode == 'REPAIR' else journal['before'][stage]
            journal['status'] = 'APPLYING_' + mode
            journal['events'].append({'stage': stage, 'action': 'SAVE_PENDING', 'mode': mode})
            save(journal_path, journal)
            apply_location(settings, desired)
            if location(project.get_managed_folder(folder_id).get_settings().get_raw_params()) != desired:
                raise ValueError('SETTINGS_SAVE_NOT_CONFIRMED:' + stage)
            if mode == 'REPAIR':
                remote = dataiku.Folder(folder_id, ignore_flow=True)
                info = remote.get_info(sensitive_info=False).get('accessInfo', {})
                if not info.get('root') or info.get('root') == source_access.get('root'):
                    raise ValueError('RESULT_ROOT_UNRESOLVED_OR_INPUT_COLLISION:' + stage)
                if source_access.get('bucket') != info.get('bucket'):
                    raise ValueError('EFFECTIVE_BUCKET_MISMATCH:' + stage)
                resolved_key = (info.get('bucket'), info['root'])
                if resolved_key in resolved_locations:
                    raise ValueError('RESULT_ROOT_COLLISION:' + stage)
                resolved_locations.add(resolved_key)
                probe_path = '_gold_zip_s3_repair/' + uuid.uuid4().hex + '.json'
                probe = encode({'cfg_sha256': digest, 'folder_id': folder_id, 'stage': stage})
                remote.upload_stream(probe_path, io.BytesIO(probe))
                with remote.get_download_stream(probe_path) as stream:
                    if stream.read(len(probe) + 1) != probe:
                        raise ValueError('S3_READBACK_MISMATCH:' + stage)
                journal['events'].append({'stage': stage, 'action': 'READ_WRITE_OK',
                    'probe': probe_path, 'resolved_bucket': info.get('bucket'), 'resolved_root': info['root']})
                print('S3 읽기/쓰기 확인:', stage, info['root'])
            save(journal_path, journal)
        if mode == 'REPAIR':
            before_run_only()
            installation = dict(cfg, scenario=scenario.id)
            remote = dataiku.Folder(expected_ids['report'], ignore_flow=True)
            data = encode(installation)
            remote.upload_stream('installation.json', io.BytesIO(data))
            with remote.get_download_stream('installation.json') as stream:
                if stream.read(len(data) + 1) != data:
                    raise ValueError('INSTALLATION_READBACK_MISMATCH')
            remote.upload_stream('_gold_zip_s3_repair/backup-' + digest + '.json', io.BytesIO(encode(journal)))
        journal['status'] = mode + '_COMPLETE'; save(journal_path, journal)
    except BaseException as exc:
        journal['status'] = 'FAILED'; journal['events'].append({'action': 'FAILED', 'type': type(exc).__name__})
        save(journal_path, journal)
        print('복구 미완료. 같은 셀 재실행으로 확인/계속 가능. 원래 실패 셀은 재실행하지 마세요.')
        raise
    if mode == 'REPAIR':
        print('S3_REPAIR_COMPLETE: 결과8폴더 읽기/쓰기 및 installation.json 확인')
        print('다음: Scenarios → ' + scenario_name + ' → Run 한 번')
        print('기존 설치 셀은 재실행하지 마세요. 폴더 ID/레시피/원문34조각은 유지했습니다.')
    else:
        print('S3_ROLLBACK_COMPLETE: 이전 폴더 설정 복원. 파일 이동/삭제 없음.')
    return journal
