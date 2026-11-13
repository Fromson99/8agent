"""R8 재적재 Flow 설치 — 레시피 4개 + 시나리오 RUN_ALL. 설치는 실행하지 않는다.

입력 폴더(구조화 세대 ZIP 조각, S3 또는 OBS)는 레시피 입력으로만 연결한다(읽기만).
결과 폴더 4개는 쓰기 폴더(WRITE_FOLDER_ID, 비우면 코드 폴더)와 같은 연결에 만든다.

R4 (2026-11-13 개발계 화면): 코드로 만든 폴더에는 연결의 기본 버킷(개발계 AIDP-YNY-DEV-BUC-SRI — 없거나 권한 없음,
S3 404 NoSuchBucket)이 들어간다. 그래서 폴더를 만들 때 손으로 만든 코드 폴더(LGL_R8_CODE)의 실제 버킷·경로 규칙을
복사하고 열리는지 확인한다. 이미 만들어져 열리지 않는 폴더(버킷이 없어 데이터가 있을 수 없음)도 같은 값으로 맞춘다.
열리는 폴더는 건드리지 않는다. 같은 이름·같은 폴더의 이전 판(R1~R3) 레시피는 새 판 코드로 바꾼다.
"""
import re
from pathlib import Path

PREFIX = 'LGL_R8_RELOAD'
RUNTIME_MARK = 'from reload_runtime import run'
UNREACHABLE = ('NoSuchBucket', 'does not exist', 'not authorized', 'AccessDenied', 'Status Code: 404', 'Status Code: 403')


def validate(cfg):
    for key in ('CODE_FOLDER_ID', 'INPUT_FOLDER_ID', 'WRITE_FOLDER_ID', 'TARGET_CONNECTION', 'EMBED_MODEL',
                'EXPECTED_ARCHIVE'):
        if not isinstance(cfg.get(key), str) or not cfg[key].strip():
            raise ValueError(key+'_REQUIRED')
    if not str(cfg['EXPECTED_ARCHIVE']).lower().endswith('.zip'):
        raise ValueError('EXPECTED_ARCHIVE_ZIP')
    if type(cfg.get('EXPECTED_PARTS')) is not int or not 1 <= cfg['EXPECTED_PARTS'] <= 100000:
        raise ValueError('EXPECTED_PARTS_REQUIRED')
    if not cfg.get('WORK_DIR') or not Path(cfg['WORK_DIR']).is_absolute():
        raise ValueError('WORK_DIR_ABSOLUTE')
    if type(cfg.get('EMBED_DIMENSIONS')) is not int or not 1 <= cfg['EMBED_DIMENSIONS'] <= 4096:
        raise ValueError('EMBED_DIMENSIONS')
    if not re.fullmatch('[A-Z][A-Z0-9_]{0,29}', cfg.get('EXPECTED_DB_USER') or ''):
        raise ValueError('EXPECTED_DB_USER_REQUIRED')
    if cfg.get('SELECTION_CHANNEL') and not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', cfg['SELECTION_CHANNEL']):
        raise ValueError('SELECTION_CHANNEL_INVALID')
    if cfg.get('BUCKET') and not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{1,62}', cfg['BUCKET']):
        raise ValueError('BUCKET_INVALID')


def reachable(dataiku, folder_id):
    """폴더 목록을 읽을 수 있으면 True. 버킷이 없거나(404·NoSuchBucket) 권한이 없으면 False. 그 밖의 오류는 그대로."""
    try:
        dataiku.Folder(folder_id, ignore_flow=True).list_paths_in_partition()
        return True
    except Exception as exc:
        if any(k in str(exc) for k in UNREACHABLE):
            return False
        raise


def storage_target(dataiku, code, cfg):
    """손으로 만든 코드 폴더가 실제로 쓰는 버킷·경로 규칙. S3형 연결(OBS 등)이 아니면 맞출 것 없음(None)."""
    settings = code.get_settings()
    if settings.type != 'S3':
        return None
    raw = settings.get_raw_params()
    bucket = (cfg.get('BUCKET') or '').strip()
    if not bucket:
        info = dataiku.Folder(code.id, ignore_flow=True).get_info(sensitive_info=False)
        bucket = (info.get('accessInfo') or {}).get('bucket') or raw.get('bucket')
    if not bucket:
        raise ValueError('CODE_FOLDER_BUCKET_UNKNOWN: 코드 폴더 Settings의 Bucket 값을 설치 셀 PARAMS의 BUCKET 칸에 넣으세요')
    path = raw.get('path') or ''
    if '${odbId}' not in path:          # 폴더마다 다른 경로가 되게 — 코드 폴더 경로를 그대로 쓰면 겹친다
        path = '${projectKey}/${odbId}'
    return {'connection': raw.get('connection'), 'bucket': bucket, 'path': path}


def install(params, bootstrap):
    import dataiku
    from reload_runtime import STEPS
    cfg = dict(params)
    validate(cfg)
    project = dataiku.api_client().get_default_project()

    def find(ref):
        listed = project.list_managed_folders()
        found = [f for f in listed if f['id'] == ref] or [f for f in listed if f['name'] == ref]
        if len(found) > 1:
            raise ValueError('AMBIGUOUS_FOLDER_NAME:'+ref+' — 같은 이름 폴더가 여럿입니다. 폴더 ID를 넣으세요')
        return project.get_managed_folder(found[0]['id']) if found else None

    code = find(cfg['CODE_FOLDER_ID'])
    if code is None:
        raise ValueError('FOLDER_NOT_FOUND:'+cfg['CODE_FOLDER_ID']+' — 코드 ZIP을 올린 폴더가 이 프로젝트에 없습니다')
    if not reachable(dataiku, code.id):
        raise ValueError('CODE_FOLDER_UNREACHABLE: 코드 폴더를 읽을 수 없습니다')
    target = storage_target(dataiku, code, cfg)
    fixed = []

    def pin(folder, label, *, created):
        """새로 만든 폴더, 또는 열리지 않는 폴더만 코드 폴더의 버킷·경로 규칙으로 맞춘다."""
        if not created and reachable(dataiku, folder.id):
            return
        if target is None:
            if not reachable(dataiku, folder.id):
                raise ValueError('FOLDER_UNREACHABLE:'+label)
            return
        settings = folder.get_settings()
        raw = settings.get_raw_params()
        if raw.get('connection') != target['connection']:
            raise ValueError('FOLDER_CONNECTION_DIFFERS:'+label+' — 열리지 않는 폴더가 코드 폴더와 다른 연결입니다. 폴더를 지우고 다시 설치')
        before = {k: raw.get(k) for k in ('bucket', 'path')}
        raw['bucket'], raw['path'] = target['bucket'], target['path']
        settings.save()
        again = project.get_managed_folder(folder.id).get_settings().get_raw_params()
        if again.get('bucket') != target['bucket'] or again.get('path') != target['path']:
            raise ValueError('FOLDER_STORAGE_SAVE_UNCONFIRMED:'+label)
        if not reachable(dataiku, folder.id):
            raise ValueError('FOLDER_STILL_UNREACHABLE:'+label+' — 버킷 '+target['bucket']+'으로도 열리지 않습니다')
        fixed.append(label)
        print('FOLDER_STORAGE_SET', label, before, '->', {'bucket': target['bucket'], 'path': target['path']},
              '(새로 만듦)' if created else '(열리지 않던 폴더 고침)', flush=True)

    def create(name, like):
        settings = like.get_settings()
        made = project.create_managed_folder(name, folder_type=settings.type,
                                             connection_name=settings.get_raw_params().get('connection'))
        pin(made, name, created=True)
        return made

    source = find(cfg['INPUT_FOLDER_ID'])
    if source is None:
        source = create(cfg['INPUT_FOLDER_ID'], code)
        print('INPUT_FOLDER_CREATED', cfg['INPUT_FOLDER_ID'], source.id,
              '— 여기에 구조화 세대 ZIP 조각과 ORIGINAL.sha256·PARTS.sha256을 올리세요', flush=True)
    elif not reachable(dataiku, source.id):
        if source.get_settings().get_raw_params().get('connection') != code.get_settings().get_raw_params().get('connection'):
            raise ValueError('INPUT_FOLDER_UNREACHABLE: 조각 폴더를 읽을 수 없습니다(다른 연결)')
        pin(source, cfg['INPUT_FOLDER_ID'], created=False)
    write_folder = find(cfg['WRITE_FOLDER_ID'])
    if write_folder is None:
        raise ValueError('FOLDER_NOT_FOUND:'+cfg['WRITE_FOLDER_ID'])
    if write_folder.id == source.id:
        raise ValueError('WRITE_FOLDER_IS_INPUT_FOLDER: 쓰기 폴더는 조각이 있는 입력 폴더와 다른 폴더여야 합니다')
    if write_folder.id != code.id and not reachable(dataiku, write_folder.id):
        raise ValueError('WRITE_FOLDER_UNREACHABLE: 쓰기 폴더를 읽을 수 없습니다 — WRITE_FOLDER_ID를 비우세요')
    cfg.update(CODE_FOLDER_ID=code.id, INPUT_FOLDER_ID=source.id, WRITE_FOLDER_ID=write_folder.id)
    connection = write_folder.get_settings().get_raw_params().get('connection')
    if not connection:
        raise ValueError('WRITE_FOLDER_CONNECTION_REQUIRED')
    recipes = {r['name'] for r in project.list_recipes()}
    cfg.update(project=project.project_key, folders={})
    flow = project.get_flow()
    zone = next((z for z in flow.list_zones() if z.name == PREFIX), None) or flow.create_zone(PREFIX)
    for stage, step in STEPS:
        name = PREFIX+'_'+step+'_OUT'
        folder = find(name)
        if folder is not None:
            if folder.get_settings().get_raw_params().get('connection') != connection:
                raise ValueError('OUTPUT_FOLDER_CONFLICT:'+name)
            pin(folder, name, created=False)
        elif write_folder.id == code.id:
            folder = create(name, code)
        else:
            ws = write_folder.get_settings()
            folder = project.create_managed_folder(name, folder_type=ws.type, connection_name=connection)
            if not reachable(dataiku, folder.id):
                raise ValueError('OUTPUT_FOLDER_UNREACHABLE:'+name+' — WRITE_FOLDER_ID를 비우면 코드 폴더 설정을 따릅니다')
        if folder.id in {code.id, source.id, *cfg['folders'].values()}:
            raise ValueError('OUTPUT_OVERLAPS_INPUT')
        folder.move_to_zone(zone)
        cfg['folders'][stage] = folder.id
    from dev_guard import location, check_disjoint
    places = []
    for ref in dict.fromkeys([code.id, source.id, *cfg['folders'].values()]):
        c = project.get_managed_folder(ref).get_settings().get_raw_params().get('connection')
        places.append((ref, location(dataiku.Folder(ref, ignore_flow=True), c)))
    check_disjoint(places)
    previous = source.id
    for stage, step in STEPS:
        name = PREFIX+'_'+step
        inputs = list(dict.fromkeys([code.id, previous]))
        output = cfg['folders'][stage]
        script = ('PARAMS = '+repr({'CODE_FOLDER_ID': code.id})+'\n'+bootstrap+
                  '\n'+RUNTIME_MARK+'\nrun('+repr(stage)+','+repr(cfg)+')\n')
        if name in recipes:
            r = project.get_recipe(name)
            settings = r.get_settings()
            if set(settings.get_flat_input_refs()) != set(inputs) or set(settings.get_flat_output_refs()) != {output}:
                raise ValueError('RECIPE_CONFLICT:'+name+' — 입력·출력 폴더가 다릅니다. 레시피를 지우고 다시 설치')
            if settings.get_code() != script:
                if RUNTIME_MARK not in (settings.get_code() or ''):
                    raise ValueError('RECIPE_CONFLICT:'+name+' — 이 설치기가 만든 레시피가 아닙니다')
                settings.set_code(script)      # 같은 이름·같은 폴더의 이전 판(R1~R3) 레시피를 새 판 코드로
                settings.save()
                print('RECIPE_UPDATED', name, flush=True)
        else:
            b = project.new_recipe('python', name)
            for ref in inputs:
                b.with_input(ref)
            r = b.with_output(output, append=True).with_script(script).create()
            settings = r.get_settings()
            settings.set_code_env(inherit=True)
            settings.save()
        r.move_to_zone(zone)
        previous = output
    name = PREFIX+'_RUN_ALL'
    script = 'from dataiku.scenario import Scenario\ns=Scenario()\n'
    for stage, step in STEPS:
        script += ('s.build_folder('+repr(cfg['folders'][stage])+', build_mode="NON_RECURSIVE_FORCED_BUILD", step_name='+
                   repr(step)+', asynchronous=False, fail_fatal=True)\n')
    found = [s for s in project.list_scenarios() if s['name'] == name]
    if len(found) > 1:
        raise ValueError('SCENARIO_AMBIGUOUS')
    if found:
        if project.get_scenario(found[0]['id']).get_settings().code != script:
            raise ValueError('SCENARIO_CONFLICT')
    else:
        scenario = project.create_scenario(name, 'custom_python')
        settings = scenario.get_settings()
        settings.code = script
        settings.active = False
        settings.save()
    print('FLOW_INSTALLED', name, '결과 폴더(쓰기 연결 '+connection+')', cfg['folders'],
          '버킷 맞춤: '+(', '.join(fixed) if fixed else '없음'), flush=True)
    return cfg


def install_reload(params, bootstrap):
    import dataiku
    from gold_owner import resolve
    gold = resolve(dataiku.get_custom_variables())
    print('GOLD_TARGET', gold['GOLD_OWNER']+'.'+(gold['TABLE_PREFIX'] or 'IDD_B003_LGL_')+'*',
          '(프로젝트 변수 LGL_GOLD_OWNER — 실행 때마다 다시 읽음)', flush=True)
    cfg = dict(params)
    cfg.setdefault('WORK_DIR', dataiku.get_custom_variables().get('AGENT_FLOW_WORK_DIR') or str(Path.home()/'.dataiku-agent-work'))
    if not cfg.get('WRITE_FOLDER_ID'):
        cfg['WRITE_FOLDER_ID'] = cfg.get('CODE_FOLDER_ID')   # 비우면 코드 폴더와 같은 연결·버킷
    return install(cfg, bootstrap)
