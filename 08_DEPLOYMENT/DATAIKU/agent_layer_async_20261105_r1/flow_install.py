"""Install three new DSS Python recipes. Installation never submits a job."""
import re
from pathlib import Path

STEPS=(('submit','01_SUBMIT'),('wait','02_WAIT_AGENT'),('load','03_LOAD'))


def validate(cfg):
    if cfg['ENVIRONMENT'] not in ('DEV','PROD'):
        raise ValueError('ENVIRONMENT_MUST_BE_DEV_OR_PROD')
    for key in ('CODE_FOLDER_ID','INPUT_FOLDER_ID','TARGET_CONNECTION','AGENT_CONNECTION','EMBED_MODEL'):
        if not isinstance(cfg[key],str) or not cfg[key].strip():
            raise ValueError(key+'_REQUIRED')
    if (not cfg['WORK_DIR'] or not Path(cfg['WORK_DIR']).is_absolute() or
            type(cfg['EMBED_DIMENSIONS']) is not int or not 1<=cfg['EMBED_DIMENSIONS']<=4096):
        raise ValueError('SHARED_WORK_DIR_OR_DIMENSIONS')
    for key in ('EXPECTED_DB_USER',*(['GOLD_OWNER'] if cfg['ENVIRONMENT']=='PROD' else [])):
        if not re.fullmatch('[A-Z][A-Z0-9_]{0,29}',cfg[key]):
            raise ValueError(key+'_REQUIRED')


def install(params, bootstrap):
    import dataiku
    validate(params)
    project=dataiku.api_client().get_default_project()
    prefix='LGL_AGENT_R1_'+params['ENVIRONMENT']
    code=project.get_managed_folder(params['CODE_FOLDER_ID'])
    source=project.get_managed_folder(params['INPUT_FOLDER_ID'])
    settings=code.get_settings()
    connection=settings.get_raw_params().get('connection')
    if settings.type not in ('S3','Filesystem') or not connection:
        raise ValueError('CODE_FOLDER_CONNECTION_REQUIRED')
    support=[params['SUPPORT_FOLDER_ID']] if params['SUPPORT_FOLDER_ID'] else []
    if source.id in [code.id,*support]:
        raise ValueError('LOOSE_DOCUMENT_FOLDER_MUST_BE_SEPARATE')
    folders=project.list_managed_folders()
    recipes={r['name'] for r in project.list_recipes()}
    cfg=dict(params,project=project.project_key,folders={})
    flow=project.get_flow()
    zone=next((z for z in flow.list_zones() if z.name==prefix),None) or flow.create_zone(prefix)
    for stage,step in STEPS:
        name=prefix+'_'+step+'_OUT'
        matches=[f for f in folders if f['name']==name]
        if len(matches)>1:
            raise ValueError('AMBIGUOUS_OUTPUT_FOLDER:'+name)
        if matches:
            folder=project.get_managed_folder(matches[0]['id'])
            fs=folder.get_settings()
            if fs.type!=settings.type or fs.get_raw_params().get('connection')!=connection:
                raise ValueError('OUTPUT_FOLDER_CONFLICT:'+name)
        else:
            folder=project.create_managed_folder(name,folder_type=settings.type,connection_name=connection)
        if folder.id in {code.id,source.id,*support,*cfg['folders'].values()}:
            raise ValueError('OUTPUT_OVERLAPS_INPUT')
        folder.move_to_zone(zone)
        cfg['folders'][stage]=folder.id
    # Check the physical DSS paths as different managed-folder IDs can alias one bucket prefix.
    from dev_guard import location,check_disjoint
    locations=[]
    for ref in dict.fromkeys([code.id,source.id,*support,*cfg['folders'].values()]):
        c=project.get_managed_folder(ref).get_settings().get_raw_params().get('connection')
        locations.append((ref,location(dataiku.Folder(ref,ignore_flow=True),c)))
    check_disjoint(locations)
    previous=source.id
    for stage,step in STEPS:
        name=prefix+'_'+step
        inputs=list(dict.fromkeys([code.id,previous]+(support if stage=='submit' else [])))
        output=cfg['folders'][stage]
        script='PARAMS = '+repr({'CODE_FOLDER_ID':code.id})+'\n'+bootstrap+'\nfrom flow_runtime import run\nrun('+repr(stage)+','+repr(cfg)+')\n'
        if name in recipes:
            r=project.get_recipe(name)
            settings=r.get_settings()
            if (settings.get_code()!=script or set(settings.get_flat_input_refs())!=set(inputs)
                    or set(settings.get_flat_output_refs())!={output}):
                raise ValueError('RECIPE_CONFLICT:'+name)
        else:
            b=project.new_recipe('python',name)
            for ref in inputs:
                b.with_input(ref)
            r=b.with_output(output,append=True).with_script(script).create()
            settings=r.get_settings()
            settings.set_code_env(inherit=True)
            settings.save()
        r.move_to_zone(zone)
        previous=output
    name=prefix+'_RUN_ALL'
    script='from dataiku.scenario import Scenario\ns=Scenario()\n'
    for stage,step in STEPS:
        script+='s.build_folder('+repr(cfg['folders'][stage])+', build_mode="NON_RECURSIVE_FORCED_BUILD", step_name='+repr(step)+', asynchronous=False, fail_fatal=True)\n'
    found=[s for s in project.list_scenarios() if s['name']==name]
    if len(found)>1:
        raise ValueError('SCENARIO_AMBIGUOUS')
    if found:
        if project.get_scenario(found[0]['id']).get_settings().code!=script:
            raise ValueError('SCENARIO_CONFLICT')
    else:
        scenario=project.create_scenario(name,'custom_python')
        settings=scenario.get_settings()
        settings.code=script
        settings.active=False
        settings.save()
    print('FLOW_INSTALLED',name,'결과 폴더',cfg['folders']['load'])
    return cfg
