# 개발계 Dataiku 노트북: "Gold 판본 선택 보완" 플로우(입력 폴더 1개 + Python 레시피 1개)를 만든다.
# 사용법: Dataiku에서 새 프로젝트를 직접 만들고, 그 프로젝트 안의 노트북에서 이 TXT 전체를 셀 하나로 실행한다.
# 지금 프로젝트에 폴더·레시피만 만든다(프로젝트 생성·ZIP 내보내기·DB·모델 실행 없음).
# 레시피는 입력 폴더(버킷)를 읽기만 하고 Oracle Gold만 UPDATE한다. 폴더·버킷에는 쓰지 않는다.
# 순서: (1) 이 셀 실행 → (2) 생긴 gold_selection_input 폴더에 판본 선택 JSON 업로드 → (3) 이 셀 다시 실행(JSON 확인)
#       → (4) 프로젝트 메뉴 Export에서 '관리 폴더(Managed folders) 내용 포함'을 켜고 ZIP 받기. JSON이 ZIP에 같이 들어간다.
PARAMS = {
    # 비워 두면 DSS 서버 디스크(filesystem_folders)에 폴더를 만든다. 권장: ZIP에 폴더 내용이 들어가고, 운영 가져오기 때 버킷에 쓰지 않는다.
    # S3에 꼭 만들어야 하면 '프로젝트키.폴더ID'(예: 'LEGAL_RAG.ehA8dpVm')로 그 폴더의 연결·버킷을 복사한다.
    'REFERENCE_FOLDER': '',
    # 운영에서 쓸 값. 이 프로젝트 변수(GOLD_FIX_*)로 들어가며 프로젝트 설정 > 변수에서 바꿀 수 있다.
    'ORACLE_CONNECTION': 'AIDP',
    'EXPECTED_DB_USER': 'PIDD2APP',
    'GOLD_OWNER': 'SIDDG',
}

import hashlib
import re
import dataiku

INPUT_FOLDER = 'gold_selection_input'
OUTPUT_FOLDER = 'gold_selection_noop'   # Dataiku가 python 레시피에 출력을 요구해 연결만 한다. 레시피는 쓰지 않는다
RECIPE = 'GOLD_SELECTION_FIX_R7'
RECIPE_SHA256 = '__RECIPE_SHA256__'
RECIPE_CODE = __RECIPE_CODE__
if hashlib.sha256(RECIPE_CODE.encode()).hexdigest() != RECIPE_SHA256: raise ValueError('RECIPE_CODE_CHANGED')


def say(*a): print(*a, flush=True)


def main():
    client = dataiku.api_client()
    project = client.get_default_project()
    # 1) 새 폴더에 쓸 저장 연결: 정상 동작하는 기존 폴더에서 복사
    folder_type, connection, bucket = None, 'filesystem_folders', None
    ref_text = PARAMS['REFERENCE_FOLDER'].strip()
    if ref_text:
        if ref_text.count('.') != 1: raise ValueError("REFERENCE_FOLDER 는 '프로젝트키.폴더ID' 형식")
        ref_key, ref_id = ref_text.split('.')
        ref = client.get_project(ref_key).get_managed_folder(ref_id).get_settings()
        raw = ref.get_raw_params()
        folder_type, connection, bucket = ref.type, raw['connection'], raw.get('bucket')
    say('폴더 저장 연결:', folder_type or 'Filesystem', connection, bucket or '')
    # 2) 지금 프로젝트는 새로 만든 빈 프로젝트여야 한다(이 설치가 만든 것만 허용)
    folders = {f['name'] for f in project.list_managed_folders()}
    recipes = {r['name'] for r in project.list_recipes()}
    datasets = [d['name'] for d in project.list_datasets()]
    if not folders <= {INPUT_FOLDER, OUTPUT_FOLDER, 'gold_selection_result'} or not recipes <= {RECIPE} or datasets:
        raise ValueError('PROJECT_NOT_EMPTY: '+project.project_key+' 안에 있는 것 - 폴더 '+str(sorted(folders))+
                         ', 레시피 '+str(sorted(recipes))+', 데이터셋 '+str(sorted(datasets))+
                         '. 새로 만든 빈 프로젝트의 노트북에서 실행하세요.')
    say('설치 프로젝트:', project.project_key)
    # 3) 입력 폴더(그리고 필요할 때만 빈 출력 폴더)
    def folder(name):
        existing = {f['name']: f['id'] for f in project.list_managed_folders()}
        if name in existing:
            f = project.get_managed_folder(existing[name])
            if f.get_settings().get_raw_params().get('connection') != connection: raise ValueError('FOLDER_CONNECTION_DIFFERS: '+name)
            say('폴더 재사용:', name); return f
        f = project.create_managed_folder(name, folder_type=folder_type, connection_name=connection)
        if folder_type == 'S3':
            s = f.get_settings(); raw = s.get_raw_params()
            raw['path'] = '/${projectKey}/' + name
            if bucket: raw['bucket'] = bucket
            s.save()
        say('폴더 생성:', name); return f
    made = {INPUT_FOLDER: folder(INPUT_FOLDER)}
    # 4) Python 레시피: 입력 폴더 + 빈 출력 폴더(Dataiku는 python 레시피에 출력 'main'을 요구. 레시피는 출력에 쓰지 않는다)
    made[OUTPUT_FOLDER] = folder(OUTPUT_FOLDER)
    names = {r['name'] for r in project.list_recipes()}
    if RECIPE in names:
        settings = project.get_recipe(RECIPE).get_settings()
        outputs = set(settings.get_flat_output_refs())
        if set(settings.get_flat_input_refs()) != {made[INPUT_FOLDER].id} or len(outputs) > 1:
            raise ValueError('RECIPE_INPUT_OUTPUT_DIFFER: '+RECIPE)
        if not outputs:
            # 앞선 설치본(출력 없음)을 고친다
            settings.add_output('main', made[OUTPUT_FOLDER].id)
            say('레시피에 빈 출력 폴더 연결:', OUTPUT_FOLDER)
        if settings.get_code() != RECIPE_CODE:
            settings.set_code(RECIPE_CODE); say('레시피 코드 갱신:', RECIPE)
        settings.save()
        say('레시피 재사용:', RECIPE)
    else:
        recipe = (project.new_recipe('python', RECIPE).with_input(made[INPUT_FOLDER].id)
                  .with_output(made[OUTPUT_FOLDER].id, append=True).with_script(RECIPE_CODE).create())
        settings = recipe.get_settings(); settings.set_code_env(inherit=True); settings.save()
        say('레시피 생성:', RECIPE, '(출력 폴더', OUTPUT_FOLDER, '연결, 쓰지 않음)')
    # 6) 실행 설정(프로젝트 변수). 이미 있으면 그대로 둔다.
    variables = project.get_variables(); std = variables.setdefault('standard', {})
    wanted = {'GOLD_FIX_MODE': 'APPLY', 'GOLD_FIX_ORACLE_CONNECTION': PARAMS['ORACLE_CONNECTION'],
              'GOLD_FIX_EXPECTED_DB_USER': PARAMS['EXPECTED_DB_USER'], 'GOLD_FIX_GOLD_OWNER': PARAMS['GOLD_OWNER']}
    changed = False
    for k, v in wanted.items():
        if k not in std: std[k] = v; changed = True
    if changed: project.set_variables(variables)
    say('프로젝트 변수:', {k: std[k] for k in wanted})
    # 7) 입력 폴더의 JSON 확인(읽기만)
    import json as _json
    files = [x for x in made[INPUT_FOLDER].list_contents()['items'] if x['path'].lower().endswith('.json')]
    if not files:
        say('입력 폴더가 비어 있습니다. gold_selection_input 에 판본 선택 JSON을 올린 뒤 이 셀을 다시 실행하세요.')
    elif len(files) > 1:
        raise ValueError('INPUT_FOLDER_HAS_MANY_JSON: '+str([x['path'] for x in files])+' 하나만 남기세요.')
    else:
        with made[INPUT_FOLDER].get_file(files[0]['path']) as resp: raw = resp.content
        v = _json.loads(raw.decode('utf-8-sig'))
        if v.get('schema_version') != 'filename-search-selection-v2': raise ValueError('SELECTION_NOT_V2: '+files[0]['path'])
        say('입력 JSON 확인:', files[0]['path'], 'sha256', hashlib.sha256(raw).hexdigest(), v.get('generation_id'),
            'manifest', str(v.get('manifest_sha256'))[:16], '빠지는 옛 판본', len(v.get('excluded') or []))
    say('FLOW_READY', project.project_key, '레시피', RECIPE, '코드 sha256', RECIPE_SHA256[:16])
    say("다음: 프로젝트 메뉴 > Export 에서 '관리 폴더(Managed folders) 내용 포함'을 켜고 ZIP을 받으세요.")
    return {'project': project.project_key, 'recipe': RECIPE, 'input': made[INPUT_FOLDER].id, 'output': made[OUTPUT_FOLDER].id}


RESULT = main()
