"""R8 재적재 Flow 설치 — 레시피 4개 + 시나리오 RUN_ALL. 설치는 실행하지 않는다.

입력 폴더(구조화 세대 ZIP 조각, S3 또는 OBS)는 레시피 입력으로만 연결한다(읽기만).
결과 폴더 4개는 쓰기 폴더(WRITE_FOLDER_ID, 비우면 코드 폴더)와 같은 연결에 만든다.

R5 (2026-11-13 개발계 확인 셀 결과): 버킷은 모든 폴더가 같다(AIDP-YNY-DEV-BUC-SRI). 화면으로 만든 코드 폴더는
경로가 /dataiku/${projectKey}/${odbId}, 코드(dataikuapi)로 만든 폴더는 /${projectKey}/${odbId}이고, 이 연결은
/dataiku/ 밑에만 쓸 수 있어 코드로 만든 폴더에 쓰면 404 NoSuchBucket(권한 없음도 404)이 난다. 목록 읽기는 되므로
R4의 '목록이 읽히면 열림' 검사는 이걸 못 잡았다. R5는 쓰기 폴더마다 작은 파일을 써 보고(바로 지움) 막혔으면 경로를
코드 폴더의 경로 규칙으로 바꾼다. 비어 있지 않은 폴더나 다른 연결(S3 원본 등)의 폴더는 바꾸지 않는다.
같은 이름·같은 폴더의 이전 판(R1~R4) 레시피는 새 판 코드로 바꾼다.
"""
import re
from pathlib import Path

PREFIX = 'LGL_R8_RELOAD'
RUNTIME_MARK = 'from reload_runtime import run'
DENIED = ('NoSuchBucket', 'does not exist', 'not authorized', 'AccessDenied', 'Status Code: 404', 'Status Code: 403')
PROBE = '.lgl_r8_write_check'


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
    if cfg.get('FOLDER_PATH') and not re.fullmatch(r'/?[A-Za-z0-9_.\-/]*\$\{projectKey\}/\$\{odbId\}', cfg['FOLDER_PATH']):
        raise ValueError('FOLDER_PATH_INVALID: 예) /dataiku/${projectKey}/${odbId}')


def denied(exc):
    return any(k in str(exc) for k in DENIED)


def reachable(dataiku, folder_id):
    """폴더 목록을 읽을 수 있으면 True. 버킷이 없거나 권한이 없으면(404·403) False. 그 밖의 오류는 그대로."""
    try:
        dataiku.Folder(folder_id, ignore_flow=True).list_paths_in_partition()
        return True
    except Exception as exc:
        if denied(exc):
            return False
        raise


def files_in(dataiku, folder_id):
    return dataiku.Folder(folder_id, ignore_flow=True).list_paths_in_partition()


def writable(dataiku, folder_id):
    """작은 파일을 써 보고 바로 지운다. 쓰기가 거절(404·403)되면 False. 지우기 실패 등 그 밖의 오류는 그대로."""
    folder = dataiku.Folder(folder_id, ignore_flow=True)
    try:
        folder.upload_data(PROBE, b'r8 reload write check\n')
    except Exception as exc:
        if denied(exc):
            return False
        raise
    folder.delete_path(PROBE)
    return True


def path_rule(dataiku, code, project_key, cfg):
    """화면으로 만든 코드 폴더가 쓰는 경로 규칙(개발계 /dataiku/${projectKey}/${odbId}). S3형 연결이 아니면 None."""
    if cfg.get('FOLDER_PATH'):
        return cfg['FOLDER_PATH']
    settings = code.get_settings()
    if settings.type != 'S3':
        return None
    path = settings.get_raw_params().get('path') or ''
    if '${odbId}' in path:
        return path
    info = dataiku.Folder(code.id, ignore_flow=True).get_info(sensitive_info=False)
    root = ((info.get('accessInfo') or {}).get('root') or '').rstrip('/')
    tail = '/'+project_key+'/'+code.id
    if root.endswith(tail):
        return root[:-len(tail)]+'/${projectKey}/${odbId}'
    raise ValueError('CODE_FOLDER_PATH_UNKNOWN: 코드 폴더 경로 규칙을 못 정했습니다. LGL_R8_CODE > Settings의 '
                     'Path in bucket 값(예: /dataiku/${projectKey}/${odbId})을 설치 셀 PARAMS의 FOLDER_PATH 칸에 넣으세요')


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

    def connection_of(folder):
        return folder.get_settings().get_raw_params().get('connection')

    code = find(cfg['CODE_FOLDER_ID'])
    if code is None:
        raise ValueError('FOLDER_NOT_FOUND:'+cfg['CODE_FOLDER_ID']+' — 코드 ZIP을 올린 폴더가 이 프로젝트에 없습니다')
    if not reachable(dataiku, code.id):
        raise ValueError('CODE_FOLDER_UNREACHABLE: 코드 폴더를 읽을 수 없습니다')
    code_raw = code.get_settings().get_raw_params()
    rule = path_rule(dataiku, code, project.project_key, cfg)
    fixed = []

    def make_writable(folder, label, *, created):
        """쓰기가 되면 그대로 둔다. 새로 만든 폴더나 쓰기가 막힌 빈 폴더는 코드 폴더의 경로 규칙으로 바꾸고 다시 써 본다."""
        settings = folder.get_settings()
        raw = settings.get_raw_params()
        same = rule is not None and raw.get('connection') == code_raw.get('connection')
        if not (created and same and raw.get('path') != rule) and writable(dataiku, folder.id):
            return
        if not same:
            raise ValueError('FOLDER_NOT_WRITABLE:'+label+' — 이 폴더에 쓸 수 없고, 코드 폴더와 다른 연결이라 자동으로 고치지 않습니다')
        if not created and files_in(dataiku, folder.id):
            raise ValueError('FOLDER_NOT_WRITABLE_HAS_FILES:'+label+' — 쓰기가 막혀 있는데 파일이 있어 경로를 바꾸지 않았습니다. '
                             '이 폴더 Settings의 Path in bucket을 LGL_R8_CODE와 같게 직접 바꿔 주세요')
        before = raw.get('path')
        raw['path'] = rule
        if 'bucket' in code_raw:
            raw['bucket'] = code_raw['bucket']
        settings.save()
        again = project.get_managed_folder(folder.id).get_settings().get_raw_params()
        if again.get('path') != rule:
            raise ValueError('FOLDER_PATH_SAVE_UNCONFIRMED:'+label)
        if not writable(dataiku, folder.id):
            raise ValueError('FOLDER_STILL_NOT_WRITABLE:'+label+' — 경로 '+rule+'로도 쓸 수 없습니다. '
                             'LGL_R8_CODE와 이 폴더의 Settings 화면 사진을 보내 주세요')
        fixed.append(label)
        print('FOLDER_PATH_SET', label, before, '->', rule, '(새로 만듦)' if created else '(쓰기가 막혀 있던 폴더 고침)', flush=True)

    def create(name, like):
        settings = like.get_settings()
        made = project.create_managed_folder(name, folder_type=settings.type,
                                             connection_name=settings.get_raw_params().get('connection'))
        make_writable(made, name, created=True)
        return made

    source = find(cfg['INPUT_FOLDER_ID'])
    if source is None:
        source = create(cfg['INPUT_FOLDER_ID'], code)
        print('INPUT_FOLDER_CREATED', cfg['INPUT_FOLDER_ID'], source.id,
              '— 여기에 구조화 세대 ZIP 조각과 ORIGINAL.sha256·PARTS.sha256을 올리세요', flush=True)
    else:
        if not reachable(dataiku, source.id):
            raise ValueError('INPUT_FOLDER_UNREACHABLE: 조각 폴더를 읽을 수 없습니다')
        if rule is not None and connection_of(source) == code_raw.get('connection') and not files_in(dataiku, source.id):
            make_writable(source, cfg['INPUT_FOLDER_ID'], created=False)   # 비어 있는 업로드 폴더 — 올릴 수 있게
    write_folder = find(cfg['WRITE_FOLDER_ID'])
    if write_folder is None:
        raise ValueError('FOLDER_NOT_FOUND:'+cfg['WRITE_FOLDER_ID'])
    if write_folder.id == source.id:
        raise ValueError('WRITE_FOLDER_IS_INPUT_FOLDER: 쓰기 폴더는 조각이 있는 입력 폴더와 다른 폴더여야 합니다')
    if write_folder.id != code.id and not reachable(dataiku, write_folder.id):
        raise ValueError('WRITE_FOLDER_UNREACHABLE: 쓰기 폴더를 읽을 수 없습니다 — WRITE_FOLDER_ID를 비우세요')
    cfg.update(CODE_FOLDER_ID=code.id, INPUT_FOLDER_ID=source.id, WRITE_FOLDER_ID=write_folder.id)
    connection = connection_of(write_folder)
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
            if connection_of(folder) != connection:
                raise ValueError('OUTPUT_FOLDER_CONFLICT:'+name)
            make_writable(folder, name, created=False)
        else:
            folder = create(name, write_folder)
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
                settings.set_code(script)      # 같은 이름·같은 폴더의 이전 판(R1~R4) 레시피를 새 판 코드로
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
          '경로 맞춤: '+(', '.join(fixed) if fixed else '없음(모든 폴더 쓰기 확인)'), flush=True)
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
        cfg['WRITE_FOLDER_ID'] = cfg.get('CODE_FOLDER_ID')   # 비우면 코드 폴더와 같은 연결·경로 규칙
    return install(cfg, bootstrap)
