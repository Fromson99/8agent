"""Install native Flow nodes only. Never starts SQL, embedding or an existing recipe."""
import json
from flow_spec import STAGES, PREFIX, INSIGHT, contract, recipe_name, validate_spec

def dataset_specs():
    specs={}
    for key,t in contract()['tables'].items():
        columns=[]
        for c in t['columns'].values():
            kind=c['type']
            # Dataiku preview shows vector metadata; raw native VECTOR stays in Oracle.
            if kind.startswith('VECTOR'):continue
            dtype='double' if kind.startswith(('NUMBER','FLOAT','BINARY_FLOAT','BINARY_DOUBLE')) else 'date' if kind.startswith(('TIMESTAMP','DATE')) else 'string'
            columns.append({'name':c['name'],'type':dtype})
        specs[key]={'name':PREFIX+'_DB_'+key, 'type':'Oracle',
                    'params':{'connection':'AIDP','schema':t['owner'],'table':t['name'],
                              'mode':'table','noDropOnSchemaMismatch':True}, 'schema':{'columns':columns}}
    return specs

def install(project, bootstrap, landing_id):
    validate_spec()
    if project.project_key!='LEGAL_RAG':raise ValueError('LEGAL_RAG_PROJECT_REQUIRED')
    landing=project.get_managed_folder(landing_id).get_settings()
    params=landing.get_raw_params()
    if landing.type!='S3' or not params.get('connection'):raise ValueError('LANDING_S3_REQUIRED')
    known_folders=project.list_managed_folders()
    cfg={'landing':landing_id,'folders':{},'legacy_cache':[],'version':'gold-flow-20261102-r1'}
    # This existing folder contains original NFS chunk cache, if the older Flow exists.
    cache=[f['id'] for f in known_folders if f['name']=='LEGAL_STRUCTURED_RESULT_R1']
    if len(cache)>1:raise ValueError('LEGACY_CACHE_AMBIGUOUS')
    cfg['legacy_cache']=cache
    flow=project.get_flow()
    zones={z.name:z for z in flow.list_zones()}
    for stage,code,label,zone_name,keys in STAGES:
        name=PREFIX+'_'+code+'_RESULT'
        found=[f for f in known_folders if f['name']==name]
        path='/LEGAL_RAG/gold_flow_20261102_r1/'+stage
        if len(found)>1:raise ValueError('FOLDER_NAME_CONFLICT:'+name)
        if found:
            folder=project.get_managed_folder(found[0]['id']);s=folder.get_settings();p=s.get_raw_params()
            if s.type!='S3' or any(p.get(k)!=v for k,v in {'connection':params['connection'],'bucket':params.get('bucket'),'path':path}.items()):
                raise ValueError('EXISTING_FOLDER_CONFLICT:'+name)
        else:
            folder=project.create_managed_folder(name,folder_type='S3',connection_name=params['connection'])
            s=folder.get_settings();s.get_raw_params().update(path=path)
            if 'bucket' in params:s.get_raw_params()['bucket']=params['bucket']
            s.save()
        cfg['folders'][stage]=folder.id
        title='Gold _1 | '+zone_name
        if title not in zones:
            zones[title]=flow.create_zone(title)
            colors=['#2196a6','#497de0','#3b9d73','#7c6bd5','#c4932e','#bb6d99','#526783']
            zs=zones[title].get_settings();zs.color=colors[int(zone_name[:2])-1];zs.save()
        folder.move_to_zone(zones[title])
    specs=dataset_specs();existing={d['name'] for d in project.list_datasets()}
    for stage,code,label,zone_name,keys in STAGES:
        for key in keys:
            spec=specs[key];name=spec['name']
            if name in existing:
                ds=project.get_dataset(name);raw=ds.get_settings().get_raw()
                columns=[{'name':c['name'],'type':c['type']} for c in ds.get_schema()['columns']]
                if raw.get('type')!='Oracle' or raw.get('managed',False) or any(raw.get('params',{}).get(k)!=v for k,v in spec['params'].items()) or columns!=spec['schema']['columns']:
                    raise ValueError('EXISTING_DATASET_CONFLICT:'+name)
            else:
                ds=project.create_dataset(name,type='Oracle',params=spec['params'])
                settings=ds.get_settings();settings.get_raw()['managed']=False;settings.save();ds.set_schema(spec['schema'])
            ds.move_to_zone(zones['Gold _1 | '+zone_name])
    recipes={r['name'] for r in project.list_recipes()}
    previous=None
    for stage,code,label,zone_name,keys in STAGES:
        name=recipe_name(stage)
        inputs=[landing_id]+([cfg['folders'][previous]] if previous else cfg['legacy_cache'])
        outputs=[cfg['folders'][stage]]+[specs[k]['name'] for k in keys]
        script=bootstrap+'\nfrom flow_runtime import run\nrun('+repr(stage)+', '+repr(cfg)+')\n'
        if name in recipes:
            s=project.get_recipe(name).get_settings()
            if s.get_code()!=script or set(s.get_flat_input_refs())!=set(inputs) or set(s.get_flat_output_refs())!=set(outputs):
                raise ValueError('EXISTING_RECIPE_CONFLICT:'+name)
        else:
            b=project.new_recipe('python',name)
            for ref in inputs:b.with_input(ref)
            for ref in outputs:b.with_output(ref,append=True)
            s=b.with_script(script).create().get_settings();s.set_code_env(inherit=True);s.save()
        previous=stage
    # Custom-Python scenario uses documented per-stage build APIs. Each build appears
    # separately in scenario history; failed stages stop subsequent builds.
    scenario_name='G19F1_RUN_ALL · NFS부터 벡터까지'
    script='from dataiku.scenario import Scenario\ns = Scenario()\n'
    for stage,code,label,*_ in STAGES:
        script+='s.build_folder('+repr(cfg['folders'][stage])+', build_mode="NON_RECURSIVE_FORCED_BUILD", step_name='+repr(code+' · '+label)+', asynchronous=False, fail_fatal=True)\n'
    matches=[s for s in project.list_scenarios() if s['name']==scenario_name]
    if len(matches)>1:raise ValueError('SCENARIO_NAME_CONFLICT')
    if matches:
        scenario=project.get_scenario(matches[0]['id']);s=scenario.get_settings()
        if s.code!=script:raise ValueError('EXISTING_SCENARIO_CONFLICT')
    else:
        scenario=project.create_scenario(scenario_name,'custom_python')
        s=scenario.get_settings();s.code=script;s.active=False;s.save()
    cfg['scenario']=scenario.id
    import dataiku
    from flow_runtime import publish_insight,dump
    # Installation creates a waiting view only. It never reports the field job as done.
    import io
    result=dataiku.Folder(cfg['folders']['report'])
    result.upload_stream('installation.json',io.BytesIO(dump(cfg)))
    # Reinstallation must not replace a useful running/completed status with blanks.
    if not any(i['id']==INSIGHT for i in project.list_insights()):publish_insight({})
    print('FLOW_INSTALLED:',len(STAGES),'recipes / 17 external Oracle datasets / scenario',scenario.id)
    print('실행: Scenarios → '+scenario_name+' → Run. 기존 노트북 적재 종료 후 실행하세요.')
    print('현황판: Dashboards → Insights → Gold _1 · 데이터 적재 현황. 필요하면 Add to dashboard.')
    return cfg
