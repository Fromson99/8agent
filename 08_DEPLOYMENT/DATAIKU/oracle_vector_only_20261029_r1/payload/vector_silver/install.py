"""Reuse R4, detach the old import chain, and retain its checkpoint folder."""
import ast
import hashlib
import json
import re
from pathlib import Path

from semantic_runtime.initial_vector import endpoint, profile

RECIPE = 'LEGAL_04_VECTOR_SILVER_R4'
RESULT = 'LEGAL_VECTOR_SILVER_RESULT_R4'
RESULT_PATH = '/LEGAL_RAG/vector_silver_20261029_r3/results'
DATASETS = ('LGL_SRCH_PBLS_S', 'LGL_VCTR_SET_S', 'LGL_VCTR_ITEM_S')


def previous_config(code):
    """Accept only the sealed R3 installer output, never arbitrary Python."""
    bootstrap = (Path(__file__).resolve().parents[1] / 'LEGACY_BOOTSTRAP.txt').read_text()
    prefix = bootstrap + '\nfrom vector_silver.runtime import run\nrun('
    suffix = ', action="build")\n'
    if not code.startswith(prefix) or not code.endswith(suffix):
        raise ValueError('FLOW_EXISTING_RECIPE_CONFLICT: expected sealed R3 recipe')
    cfg = ast.literal_eval(code[len(prefix):-len(suffix)])
    if (not isinstance(cfg, dict) or set(cfg) != {'landing', 'load', 'output', 'legacy'}
            or not all(isinstance(cfg[k], str) and cfg[k] for k in ('landing', 'load', 'output'))
            or not (cfg['legacy'] is None or isinstance(cfg['legacy'], str))):
        raise ValueError('FLOW_EXISTING_RECIPE_CONFIG')
    return cfg


def install(project, bootstrap, *, landing_id='ehA8dpVm', query_release_id='',
            model='', revision='', dimensions=0):
    # Validate all existing objects before the first change.
    variables = project.get_variables()
    standard = variables.setdefault('standard', {})
    connection = variables.get('local', {}).get('LEGAL_ORACLE_CONNECTION',
                                               standard.get('LEGAL_ORACLE_CONNECTION', 'AIDP'))
    if query_release_id:
        if not re.fullmatch('[0-9a-f]{64}', query_release_id):
            raise ValueError('VECTOR_QUERY_RELEASE_REQUIRED')
        local_pin = variables.get('local', {}).get('LEGAL_VECTOR_QUERY_RELEASE')
        if local_pin and local_pin != query_release_id:
            raise ValueError('FLOW_LOCAL_RELEASE_OVERRIDE: update the local project variable first')
        standard['LEGAL_VECTOR_QUERY_RELEASE'] = query_release_id
    if model or revision or dimensions:
        import dataiku
        config = profile({'schema_version': 'legal-vector-profile-v1', 'model': model,
                          'revision': revision, 'dimensions': dimensions,
                          'endpoint_sha256': hashlib.sha256(endpoint(dataiku.get_custom_variables()).encode()).hexdigest(),
                          'chunk_chars': 800, 'overlap_chars': 100, 'normalization': 'l2', 'metric': 'COSINE'})
        prior = standard.get('LEGAL_VECTOR_PROFILE')
        if isinstance(prior, str):
            prior = json.loads(prior)
        if prior not in (None, config):
            raise ValueError('FLOW_PROFILE_CONFLICT: retain existing model and work history')
        standard['LEGAL_VECTOR_PROFILE'] = config
    recipes = {r['name']: project.get_recipe(r['name']).get_settings() for r in project.list_recipes()}
    known = {r['name'] for r in project.list_datasets()}
    for name in DATASETS:
        if name not in known:
            raise ValueError('FLOW_DATASET_REQUIRED: import existing SIDDS.' + name + ' with this dataset name')
        raw = project.get_dataset(name).get_settings().get_raw()
        expected = {'connection': connection, 'schema': 'SIDDS', 'table': name, 'mode': 'table'}
        if (raw.get('type') != 'Oracle' or raw.get('managed', False)
                or any(raw.get('params', {}).get(k) != v for k, v in expected.items())):
            raise ValueError('FLOW_DATASET_BINDING: ' + name)
        for other, settings in recipes.items():
            refs = settings.get_flat_output_refs()
            if other != RECIPE and (name in refs or project.project_key + '.' + name in refs):
                raise ValueError('FLOW_DATASET_HAS_PRODUCER: ' + name + ' / ' + other)
    folders = project.list_managed_folders()
    source = project.get_managed_folder(landing_id).get_settings()
    params = source.get_raw_params()
    if source.type != 'S3':
        raise ValueError('FLOW_LANDING_NOT_S3')
    matches = [f['id'] for f in folders if f['name'] == RESULT]
    if len(matches) > 1 or (RECIPE in recipes and not matches):
        raise ValueError('FLOW_RESULT_AMBIGUOUS_OR_MISSING')
    output = matches[0] if matches else None
    if output:
        current = project.get_managed_folder(output).get_settings()
        if current.type != 'S3' or any(current.get_raw_params().get(k) != v for k, v in
                {'connection': params['connection'], 'bucket': params.get('bucket'), 'path': RESULT_PATH}.items()):
            raise ValueError('FLOW_EXISTING_FOLDER_CONFLICT')
    legacy = None
    old = recipes.get(RECIPE)
    cfg = {'landing': landing_id, 'output': output, 'legacy': None, 'source_mode': 'oracle'}
    inputs = [landing_id, DATASETS[0]]
    outputs = [output, *DATASETS[1:]]
    def script(value):
        return bootstrap + '\nfrom vector_silver.runtime import run\nrun(' + repr(value) + ', action="build")\n'
    upgrade = False
    if old:
        # A previous direct-Oracle install may retain an older vector checkpoint folder.
        prefix = bootstrap + '\nfrom vector_silver.runtime import run\nrun('
        code = old.get_code()
        if code.startswith(prefix) and code.endswith(', action="build")\n'):
            saved = ast.literal_eval(code[len(prefix):-len(', action="build")\n')])
            if not isinstance(saved, dict):
                raise ValueError('FLOW_EXISTING_RECIPE_CONFLICT')
            cfg['legacy'] = saved.get('legacy')
            if saved != cfg or code != script(cfg):
                raise ValueError('FLOW_EXISTING_RECIPE_CONFLICT')
        else:
            previous = previous_config(code)
            if previous['landing'] != landing_id or previous['output'] != output:
                raise ValueError('FLOW_EXISTING_RECIPE_BINDING')
            expected = {landing_id, previous['load']} | ({previous['legacy']} if previous['legacy'] else set())
            if set(old.get_flat_input_refs()) != expected or set(old.get_flat_output_refs()) != {output}:
                raise ValueError('FLOW_EXISTING_RECIPE_IO')
            cfg['legacy'] = previous['legacy']
            upgrade = True
        if not upgrade and (set(old.get_flat_input_refs()) != set(inputs)
                            or set(old.get_flat_output_refs()) != set(outputs)):
            raise ValueError('FLOW_EXISTING_RECIPE_IO')
    elif not output:
        # Preserve earlier vector attempts, if any, without connecting their producers.
        for name in ('LEGAL_VECTOR_SILVER_RESULT_R3', 'LEGAL_VECTOR_SILVER_RESULT_R2', 'LEGAL_VECTOR_RESULT_R1'):
            found = [f['id'] for f in folders if f['name'] == name]
            if len(found) > 1:
                raise ValueError('FLOW_LEGACY_FOLDER_AMBIGUOUS')
            if found:
                cfg['legacy'] = found[0]
                break
    if cfg['legacy'] and cfg['legacy'] not in {f['id'] for f in folders}:
        raise ValueError('FLOW_LEGACY_FOLDER_MISSING: checkpoint history is required')
    if not output:
        folder = project.create_managed_folder(RESULT, folder_type='S3', connection_name=params['connection'])
        settings = folder.get_settings()
        settings.get_raw_params().update(path=RESULT_PATH)
        if 'bucket' in params:
            settings.get_raw_params()['bucket'] = params['bucket']
        settings.save()
        output = folder.id
        cfg['output'] = output
        outputs[0] = output
    if upgrade:
        import dataiku
        backup = {'recipe': old.get_recipe_raw_definition(), 'code': old.get_code()}
        body = json.dumps(backup, ensure_ascii=False, sort_keys=True).encode()
        path = '/flow-backup/' + hashlib.sha256(body).hexdigest() + '.json'
        dataiku.Folder(output).upload_stream(path, body)
        old.get_recipe_raw_definition()['inputs'] = {'main': {'items': [{'ref': ref, 'deps': []} for ref in inputs]}}
        old.get_recipe_raw_definition()['outputs'] = {'main': {'items': [{'ref': ref, 'appendMode': True} for ref in outputs]}}
        old.set_code(script(cfg))
        old.save()
        print('FLOW_PREVIOUS_RECIPE_BACKUP', path)
    elif not old:
        builder = project.new_recipe('python', RECIPE)
        for ref in inputs:
            builder.with_input(ref)
        for ref in outputs:
            builder.with_output(ref, append=True)
        settings = builder.with_script(script(cfg)).create().get_settings()
        settings.set_code_env(inherit=True)
        settings.save()
    if variables != project.get_variables():
        project.set_variables(variables)
    print('FLOW_READY', RECIPE, ': Oracle publication -> vector SET/ITEM + result. No SQL/model execution.')
    return cfg
