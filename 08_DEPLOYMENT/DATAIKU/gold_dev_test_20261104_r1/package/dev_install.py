"""Readable native Flow with bounded sample input and connection-owned locations."""
import io
import json
from zip_config import STAGES
from dev_guard import check, seed_sample, probe, location, check_disjoint

PREFIX = 'GTEST'
GROUPS = {
    'inspect':'01 예시 입력 · 연결 확인',
    'restore':'02 복원 · 적재 준비', 'prepare':'02 복원 · 적재 준비',
    'source':'03 원문 · 검색 적재', 'search':'03 원문 · 검색 적재',
    'publish':'04 게시 기록', 'vector':'05 벡터 적재', 'report':'06 결과 확인',
}


def install(params, bootstrap):
    import dataiku
    project = dataiku.api_client().get_default_project()
    target = check(params, project.project_key)
    code = project.get_managed_folder(params['CODE_FOLDER_ID'])
    base = code.get_settings()
    connection = base.get_raw_params().get('connection')
    if base.type not in {'S3','Filesystem'} or not connection:
        raise ValueError('CODE_FOLDER_CONNECTION_REQUIRED')
    known = project.list_managed_folders()
    flow = project.get_flow()
    zones = {z.name:z for z in flow.list_zones()}
    def zone(name):
        if name not in zones: zones[name] = flow.create_zone(name)
        return zones[name]
    def folder(name):
        found = [f for f in known if f['name']==name]
        if len(found)>1: raise ValueError('FOLDER_NAME_CONFLICT:'+name)
        if found:
            f = project.get_managed_folder(found[0]['id'])
            s = f.get_settings()
            if s.type != base.type or s.get_raw_params().get('connection') != connection:
                raise ValueError('FOLDER_CONNECTION_CONFLICT:'+name)
        else:
            # DSS applies its connection bucket/path/naming rule; no invented prefix.
            f = project.create_managed_folder(name, folder_type=base.type, connection_name=connection)
        return f
    code.move_to_zone(zone('90 실행 코드'))
    inp = folder('GTEST_SAMPLE_2_PARTS')
    inp.move_to_zone(zone(GROUPS['inspect']))
    stable = {k:v for k,v in params.items() if k != 'RUN_AFTER_INSTALL'}
    cfg = {'version':'gold-dev-test-20261104-r1','project':project.project_key,
           'params':stable, 'input_folder':inp.id, 'folders':{}, 'target':target}
    for stage, step, label, keys in STAGES:
        f = folder(PREFIX+'_'+step+'_RESULT')
        cfg['folders'][stage] = f.id
        f.move_to_zone(zone(GROUPS[stage]))
    locations = [(ref, location(dataiku.Folder(ref, ignore_flow=True), connection))
                 for ref in [code.id, inp.id, *cfg['folders'].values()]]
    check_disjoint(locations)
    result = dataiku.Folder(cfg['folders']['report'], ignore_flow=True)
    from zip_runtime import read_folder
    saved = read_folder(result, 'installation.json')
    if saved is not None and {k:v for k,v in saved.items() if k!='scenario'} != cfg:
        raise ValueError('EXISTING_INSTALLATION_CHANGED: 원래 설정을 복구하세요.')
    # List/write/read every output before any Oracle call or scenario launch.
    probe(dataiku.Folder(code.id, ignore_flow=True), '실행코드')
    for stage, ref in cfg['folders'].items():
        probe(dataiku.Folder(ref, ignore_flow=True), stage)
    seed_sample(dataiku.Folder(inp.id, ignore_flow=True))
    existing = {d['name'] for d in project.list_datasets()}
    used_keys = {key for _,_,_,keys in STAGES for key in keys}
    for key in sorted(used_keys):
        t = target['tables'][key]
        name = PREFIX+'_DB_'+key
        columns = [{'name':c['name'],'type':'double' if c['type'].startswith('NUMBER') else
                    'date' if c['type'].startswith('TIMESTAMP') else 'string'}
                   for c in t['columns'].values() if not c['type'].startswith('VECTOR')]
        sql = {'connection':params['ORACLE_CONNECTION'],'schema':t['owner'],'table':t['name'],
               'mode':'table','noDropOnSchemaMismatch':True}
        if name in existing:
            ds = project.get_dataset(name); raw = ds.get_settings().get_raw()
            schema = [{'name':c['name'],'type':c['type']} for c in ds.get_schema()['columns']]
            if raw.get('type')!='Oracle' or raw.get('managed',False) or schema != columns or any(raw.get('params',{}).get(k)!=v for k,v in sql.items()):
                raise ValueError('EXISTING_DATASET_CONFLICT:'+name)
        else:
            ds = project.create_dataset(name, type='Oracle', params=sql)
            settings = ds.get_settings(); settings.get_raw()['managed']=False; settings.save()
            ds.set_schema({'columns':columns})
        stage = next(s for s,_,_,keys in STAGES if key in keys)
        ds.move_to_zone(zone(GROUPS[stage]))
    recipes = {r['name'] for r in project.list_recipes()}
    previous = None
    for stage, step, label, keys in STAGES:
        name = PREFIX+'_'+step
        inputs = [code.id, inp.id]+([cfg['folders'][previous]] if previous else [])
        outputs = [cfg['folders'][stage]]+[PREFIX+'_DB_'+key for key in keys]
        script = 'PARAMS = '+repr(stable)+'\n'+bootstrap+'\nfrom zip_runtime import run\nrun('+repr(stage)+','+repr(cfg)+')\n'
        if name in recipes:
            recipe = project.get_recipe(name); s = recipe.get_settings()
            if s.get_code()!=script or set(s.get_flat_input_refs())!=set(inputs) or set(s.get_flat_output_refs())!=set(outputs):
                raise ValueError('EXISTING_RECIPE_CONFLICT:'+name)
        else:
            builder = project.new_recipe('python', name)
            for ref in inputs: builder.with_input(ref)
            for ref in outputs: builder.with_output(ref, append=True)
            recipe = builder.with_script(script).create()
            s = recipe.get_settings(); s.set_code_env(inherit=True); s.save()
        recipe.move_to_zone(zone(GROUPS[stage]))
        metadata = recipe.get_metadata()
        metadata['label'] = step[:2]+' '+label
        metadata['description'] = '개발계 예시 전용. 결과와 전체 로그는 '+outputs[0]+'에서 확인합니다.'
        recipe.set_metadata(metadata)
        previous = stage
    name = 'GTEST_RUN_ALL · 예시 2조각 전체 시험'
    script = 'from dataiku.scenario import Scenario\ns = Scenario()\n'
    for stage, step, label, _ in STAGES:
        script += 's.build_folder('+repr(cfg['folders'][stage])+',build_mode="NON_RECURSIVE_FORCED_BUILD",step_name='+repr(step+' '+label)+',asynchronous=False,fail_fatal=True)\n'
    found = [s for s in project.list_scenarios() if s['name']==name]
    if len(found)>1: raise ValueError('SCENARIO_NAME_CONFLICT')
    if found:
        scenario = project.get_scenario(found[0]['id'])
        if scenario.get_settings().code != script: raise ValueError('EXISTING_SCENARIO_CONFLICT')
    else:
        scenario = project.create_scenario(name, 'custom_python')
        settings = scenario.get_settings(); settings.code=script; settings.active=False; settings.save()
    cfg['scenario'] = scenario.id
    result.upload_stream('installation.json', io.BytesIO(json.dumps(cfg, ensure_ascii=False).encode()))
    if read_folder(result, 'installation.json') != cfg: raise ValueError('INSTALLATION_READBACK')
    print('TEST_FLOW_READY: 저장 연결 확인 + 예시2조각 업로드 완료. Oracle 적재는 아직 시작하지 않았습니다.')
    print('입력 폴더:', inp.id, '/ 결과 폴더:', cfg['folders']['report'])
    print('Flow에서 Zones 표시 → 모두 접기: 01~06 단계와 90 실행코드')
    print('Scenarios → '+name+' → Run (첫 단계에서 테스트13테이블 생성·검증)')
    return cfg
