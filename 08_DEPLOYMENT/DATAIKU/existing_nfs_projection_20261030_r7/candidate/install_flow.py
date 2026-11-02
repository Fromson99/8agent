"""Add four Python recipes to LEGAL_RAG without replacing the project."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROLES = {'connection':'LEGAL_GENOS_CONNECTION_R1', 'raw':'LEGAL_RAW_SOURCE_R1',
         'structured':'LEGAL_STRUCTURED_RESULT_R1', 'load':'LEGAL_LGL_LOAD_RESULT_R1'}
STAGES = [
    ('connection','LEGAL_00_CHECK_GENOS_R1', ('landing',), 'connection'),
    ('unpack','LEGAL_01_UNZIP_RAW_R1', ('landing',), 'raw'),
    ('structure','LEGAL_02_STRUCTURE_GENOS_R1', ('landing','raw','connection'), 'structured'),
    ('load','LEGAL_03_LOAD_SILVER_R1', ('landing','structured'), 'load'),
]


def install(project, bootstrap, landing_id):
    source = project.get_managed_folder(landing_id).get_settings()
    source_params = source.get_raw_params()
    if source.type != 'S3' or source_params.get('connection') != 'OBS_DP_PUBLIC':
        raise ValueError('SOURCE_S3_CONNECTION_MISMATCH')
    # Server generates legal physical folder paths. Keep the source bucket/connection
    # but do not guess the bucket name from a photographed breadcrumb.
    known = project.list_managed_folders()
    cfg = {'landing':landing_id}
    for role, name in ROLES.items():
        found = [row for row in known if row['name'] == name]
        if len(found) > 1: raise ValueError('DUPLICATE_FOLDER_NAME: '+name)
        expected = '/LEGAL_RAG/legal_pipeline_recipes_20261027_r1/' + role
        if found:
            folder = project.get_managed_folder(found[0]['id'])
            settings = folder.get_settings()
            params = settings.get_raw_params()
            if (settings.type != 'S3' or params.get('connection') != source_params['connection']
                    or params.get('bucket') != source_params.get('bucket') or params.get('path') != expected):
                raise ValueError('EXISTING_FOLDER_CONFLICT: '+name)
        else:
            folder = project.create_managed_folder(name, folder_type='S3', connection_name=source_params['connection'])
            settings = folder.get_settings()
            params = settings.get_raw_params()
            params['path'] = expected
            if 'bucket' in source_params: params['bucket'] = source_params['bucket']
            settings.save()
        cfg[role] = folder.id
        print('S3_FOLDER', role, folder.id, expected)
    # External dataset handles give the actual seven write targets a place in Flow.
    # No table DDL, table recreation, DSS dataset writer or schema autodetection.
    dataset_specs = json.loads((ROOT/'oracle_datasets.json').read_text())
    existing_datasets = {row['name'] for row in project.list_datasets()}
    output_datasets = []
    for spec in dataset_specs:
        name, params = spec['name'], spec['params']
        if name in existing_datasets:
            ds = project.get_dataset(name)
            raw = ds.get_settings().get_raw()
            if (raw.get('type') != 'Oracle' or raw.get('managed', False)
                    or any(raw.get('params',{}).get(k) != params[k] for k in ('connection','schema','table','mode'))
                    or ds.get_schema()['columns'] != spec['schema']['columns']):
                raise ValueError('EXISTING_DATASET_CONFLICT: '+name)
        else:
            ds = project.create_dataset(name, type='Oracle', params=params)
            settings = ds.get_settings()
            settings.get_raw()['managed'] = False
            settings.save()
            ds.set_schema(spec['schema'])
        output_datasets.append(name)
    known_recipes = {row['name'] for row in project.list_recipes()}
    for stage, name, roles, output in STAGES:
        inputs = [cfg[r] for r in roles]
        outputs = [cfg[output]] + (output_datasets if stage == 'load' else [])
        script = bootstrap + '\nrun_recipe(' + repr(stage) + ', ' + repr(cfg) + ')\n'
        if name in known_recipes:
            settings = project.get_recipe(name).get_settings()
            if (settings.get_code() != script
                    or set(settings.get_flat_input_refs()) != set(inputs)
                    or set(settings.get_flat_output_refs()) != set(outputs)):
                raise ValueError('EXISTING_RECIPE_CONFLICT: '+name)
        else:
            builder = project.new_recipe('python', name)
            for item in inputs: builder.with_input(item)
            for item in outputs: builder.with_output(item, append=True)
            recipe = builder.with_script(script).create()
            settings = recipe.get_settings()
            settings.set_code_env(inherit=True)
            settings.save()
        print('RECIPE_READY', name)
    print('FLOW_INSTALLED: Flow를 새로고침하고 LEGAL_00_CHECK_GENOS_R1을 실행하세요.')
    return cfg
