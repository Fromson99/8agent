"""Exact-source Flow update, durable before-image, readback, and rollback."""
import ast
import hashlib
import io
import json
from pathlib import Path

STAGES=[('connection','LEGAL_00_CHECK_GENOS_R1',('landing',),'connection'),
        ('structure','LEGAL_02_STRUCTURE_GENOS_R1',('landing','raw','connection'),'structured'),
        ('load','LEGAL_03_LOAD_SILVER_R1',('landing','structured'),'load')]
BACKUP='_pipeline/dataiku-owned-v1/install/preprocessor-r2-before.json'


def config(code,stage=None):
    call=ast.parse(code).body[-1]
    if (not isinstance(call,ast.Expr) or not isinstance(call.value,ast.Call)
        or not isinstance(call.value.func,ast.Name) or call.value.func.id!='run_recipe'
        or len(call.value.args)!=2 or call.value.keywords):raise ValueError('RECIPE_ENTRY_CHANGED')
    actual,cfg=map(ast.literal_eval,call.value.args)
    if ((stage is not None and actual!=stage) or set(cfg)!={'landing','connection','raw','structured','load'}
        or cfg['landing']!='ehA8dpVm' or any(not isinstance(x,str) or not x for x in cfg.values())):
        raise ValueError('RECIPE_CONFIG_CHANGED')
    return cfg


def variants(stage,cfg,ref,resume):
    return [ref['prior_compute_bootstrap']+'\nrun_recipe('+repr(stage)+', '+repr(cfg)+')\n']


def update(project,root,bootstrap,action):
    import dataiku
    if action not in ('apply','inspect','rollback'):raise ValueError('ACTION')
    ref=json.loads((Path(root)/'REFERENCE.json').read_text())
    resume=(Path(root)/'resume_source.txt').read_text()
    plan=[];cfg=None
    for stage,name,inputs,output in STAGES:
        recipe=project.get_recipe(name);settings=recipe.get_settings();code=settings.get_code()
        c=config(code,stage)
        if cfg is not None and cfg!=c:raise ValueError('FLOW_CONFIG_CONFLICT')
        cfg=c;target=bootstrap+'\nrun_recipe('+repr(stage)+', '+repr(cfg)+')\n'
        if code not in variants(stage,cfg,ref,resume)+[target]:raise ValueError('UNKNOWN_RECIPE_EDIT: '+name)
        expected_in={cfg[k] for k in inputs}
        expected_out={cfg[output]} | (set(ref['datasets']) if stage=='load' else set())
        if set(settings.get_flat_input_refs())!=expected_in or set(settings.get_flat_output_refs())!=expected_out:
            raise ValueError('FLOW_EDGES_CHANGED: '+name)
        plan.append(dict(name=name,code=code,target=target,inputs=expected_in,outputs=expected_out))
    if action=='inspect':return cfg
    landing=dataiku.Folder(cfg['landing'])
    known={p.lstrip('/') for p in landing.list_paths_in_partition()}
    if BACKUP not in known:
        if action=='rollback' or any(p['code']==p['target'] for p in plan):raise ValueError('ORIGINAL_BACKUP_REQUIRED')
        body=json.dumps({p['name']:p['code'] for p in plan},sort_keys=True).encode()
        landing.upload_stream(BACKUP,io.BytesIO(body))
        with landing.get_download_stream(BACKUP) as f:
            if f.read()!=body:raise ValueError('BACKUP_READBACK')
    with landing.get_download_stream(BACKUP) as f:before=json.loads(f.read(1024*1024))
    for p in plan:
        if before[p['name']] not in variants(next(s[0] for s in STAGES if s[1]==p['name']),cfg,ref,resume):
            raise ValueError('BACKUP_SOURCE_CHANGED')
        if action=='rollback':p['target']=before[p['name']]
    # All code/edges/backups validated before the first mutation.
    for p in plan:
        recipe=project.get_recipe(p['name']);settings=recipe.get_settings()
        if settings.get_code()!=p['code'] or set(settings.get_flat_input_refs())!=p['inputs'] or set(settings.get_flat_output_refs())!=p['outputs']:
            raise ValueError('CONCURRENT_RECIPE_CHANGE')
        if p['code']!=p['target']:
            settings.set_code(p['target']);settings.save()
        observed=recipe.get_settings()
        if observed.get_code()!=p['target'] or set(observed.get_flat_input_refs())!=p['inputs'] or set(observed.get_flat_output_refs())!=p['outputs']:
            raise ValueError('RECIPE_READBACK')
        print('RECIPE_VERIFIED',p['name'],hashlib.sha256(p['target'].encode()).hexdigest(),flush=True)
    return cfg
