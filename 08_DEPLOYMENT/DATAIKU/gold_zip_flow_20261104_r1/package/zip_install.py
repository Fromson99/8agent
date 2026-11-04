"""Native Dataiku Flow installer. Tables remain external and are never auto-created."""
import json
import io
from zip_config import PREFIX, STAGES, target, validate


def install(params, bootstrap):
    import dataiku
    validate(params)
    project = dataiku.api_client().get_default_project()
    project_key = project.project_key
    base = project.get_managed_folder(params['CODE_FOLDER_ID']).get_settings()
    base_params = base.get_raw_params()
    if base.type not in {'S3','Filesystem'} or not base_params.get('connection'):
        raise ValueError('CODE_FOLDER_S3_OR_FILESYSTEM_CONNECTION_REQUIRED')
    known = project.list_managed_folders()
    flow = project.get_flow()
    zones = {z.name:z for z in flow.list_zones()}
    def zone(title):
        name = 'Gold ZIP | '+title
        if name not in zones: zones[name] = flow.create_zone(name)
        return zones[name]
    def folder(name, key):
        path = '/'+project_key+'/gold_zip_flow_20261104_r1/'+key
        wanted = {'connection':base_params['connection'],'path':path}
        if 'bucket' in base_params: wanted['bucket'] = base_params['bucket']
        found = [f for f in known if f['name']==name]
        if len(found)>1: raise ValueError('FOLDER_NAME_CONFLICT:'+name)
        if found:
            f = project.get_managed_folder(found[0]['id']); settings = f.get_settings()
            if settings.type!=base.type or any(settings.get_raw_params().get(k)!=v for k,v in wanted.items()):
                raise ValueError('EXISTING_FOLDER_CONFLICT:'+name)
        else:
            f = project.create_managed_folder(name,folder_type=base.type,connection_name=wanted['connection'])
            settings = f.get_settings(); settings.get_raw_params().update(wanted); settings.save()
        return f
    inp = project.get_managed_folder(params['INPUT_FOLDER_ID']) if params.get('INPUT_FOLDER_ID') else folder(PREFIX+'_INPUT','input')
    inp.move_to_zone(zone('00 · 업로드'))
    stable = {k:v for k,v in params.items() if k!='RUN_AFTER_INSTALL'}
    cfg = {'version':'gold-zip-flow-20261104-r1','project':project_key,'params':stable,
           'input_folder':inp.id,'folders':{},'target':target(params)}
    for stage,code,label,keys in STAGES:
        f = folder(PREFIX+'_'+code+'_RESULT',stage)
        cfg['folders'][stage] = f.id; f.move_to_zone(zone(code+' · '+label))
    existing = {d['name'] for d in project.list_datasets()}
    for key,t in cfg['target']['tables'].items():
        name = PREFIX+'_DB_'+key
        columns = [{'name':c['name'],'type':'double' if c['type'].startswith('NUMBER') else
                    'date' if c['type'].startswith('TIMESTAMP') else 'string'}
                   for c in t['columns'].values() if not c['type'].startswith('VECTOR')]
        connection = {'connection':params['ORACLE_CONNECTION'],'schema':t['owner'],'table':t['name'],
                      'mode':'table','noDropOnSchemaMismatch':True}
        if name in existing:
            ds = project.get_dataset(name); raw = ds.get_settings().get_raw()
            schema = [{'name':c['name'],'type':c['type']} for c in ds.get_schema()['columns']]
            if raw.get('type')!='Oracle' or raw.get('managed',False) or schema!=columns or any(raw.get('params',{}).get(k)!=v for k,v in connection.items()):
                raise ValueError('EXISTING_DATASET_CONFLICT:'+name)
        else:
            ds = project.create_dataset(name,type='Oracle',params=connection)
            settings = ds.get_settings(); settings.get_raw()['managed']=False; settings.save()
            ds.set_schema({'columns':columns})
        label = next((code+' · '+label for _,code,label,keys in STAGES if key in keys),'08 · 승인 지식·서비스 선택')
        ds.move_to_zone(zone(label))
    recipes = {r['name'] for r in project.list_recipes()}
    previous = None
    for stage,code,label,keys in STAGES:
        name = PREFIX+'_'+code
        inputs = list(dict.fromkeys([params['CODE_FOLDER_ID'],inp.id]+([cfg['folders'][previous]] if previous else [])))
        outputs = [cfg['folders'][stage]]+[PREFIX+'_DB_'+key for key in keys]
        script = 'PARAMS = '+repr(stable)+'\n'+bootstrap+'\nfrom zip_runtime import run\nrun('+repr(stage)+','+repr(cfg)+')\n'
        if name in recipes:
            settings = project.get_recipe(name).get_settings()
            if settings.get_code()!=script or set(settings.get_flat_input_refs())!=set(inputs) or set(settings.get_flat_output_refs())!=set(outputs):
                raise ValueError('EXISTING_RECIPE_CONFLICT:'+name)
        else:
            builder = project.new_recipe('python',name)
            for ref in inputs: builder.with_input(ref)
            for ref in outputs: builder.with_output(ref,append=True)
            settings = builder.with_script(script).create().get_settings()
            settings.set_code_env(inherit=True); settings.save()
        previous = stage
    name = PREFIX+'_RUN_ALL · ZIP부터 Gold 벡터까지'
    code = 'from dataiku.scenario import Scenario\ns = Scenario()\n'
    for stage,step,label,_ in STAGES:
        code += 's.build_folder('+repr(cfg['folders'][stage])+',build_mode="NON_RECURSIVE_FORCED_BUILD",step_name='+repr(step+' · '+label)+',asynchronous=False,fail_fatal=True)\n'
    found = [s for s in project.list_scenarios() if s['name']==name]
    if len(found)>1: raise ValueError('SCENARIO_NAME_CONFLICT')
    if found:
        scenario = project.get_scenario(found[0]['id'])
        if scenario.get_settings().code!=code: raise ValueError('EXISTING_SCENARIO_CONFLICT')
    else:
        scenario = project.create_scenario(name,'custom_python')
        settings = scenario.get_settings(); settings.code=code; settings.active=False; settings.save()
    cfg['scenario'] = scenario.id
    result = dataiku.Folder(cfg['folders']['report'],ignore_flow=True)
    result.upload_stream('installation.json',io.BytesIO(json.dumps(cfg,ensure_ascii=False).encode()))
    print('FLOW_INSTALLED: 8 Python recipes / 13 external Oracle datasets')
    print('데이터 업로드 폴더 ID:',inp.id,'/ 조각34개 + PARTS.sha256 + ORIGINAL.sha256')
    print('실행: Scenarios → '+name+' → Run')
    print('매핑 확인:',json.dumps({k:t['owner']+'.'+t['name'] for k,t in cfg['target']['tables'].items()},ensure_ascii=False))
    if params.get('RUN_AFTER_INSTALL'):
        # The first recipe checks complete parts + actual schema before any insert/model call.
        # Never resubmit an ambiguous scenario launch automatically.
        trigger = scenario.run()
        print('SCENARIO_TRIGGERED_ONCE:',scenario.id)
    return cfg
