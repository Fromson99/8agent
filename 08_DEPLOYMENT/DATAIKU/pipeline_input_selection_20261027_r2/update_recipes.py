"""Replace only known R1 recipe code; preserve all inputs, outputs, jobs and data."""
import ast
import hashlib
import json
from pathlib import Path


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def expected_sources(code, stage, baseline, adapter):
    tree = ast.parse(code)
    call = tree.body[-1]
    if (not isinstance(call, ast.Expr) or not isinstance(call.value, ast.Call)
            or not isinstance(call.value.func, ast.Name) or call.value.func.id != 'run_recipe'
            or len(call.value.args) != 2 or call.value.keywords):
        raise ValueError('RECIPE_ENTRY_CHANGED')
    actual_stage, cfg = [ast.literal_eval(v) for v in call.value.args]
    if (actual_stage != stage or not isinstance(cfg, dict)
            or set(cfg) != {'landing','connection','raw','structured','load'}
            or cfg['landing'] != 'ehA8dpVm'
            or any(not isinstance(v,str) or not v for v in cfg.values())):
        raise ValueError('RECIPE_CONFIG_CHANGED')
    ending = '\nrun_recipe(' + repr(stage) + ', ' + repr(cfg) + ')\n'
    old = baseline + ending
    anchor = '\ndef run_recipe(stage, cfg):\n'
    invocation = '        import recipes_runtime\n        recipes_runtime.execute(stage, cfg, work)'
    if baseline.count(anchor) != 1 or baseline.count(invocation) != 1:
        raise ValueError('BASELINE_ANCHOR_CHANGED')
    patched = baseline.replace(anchor, '\n' + adapter + anchor)
    patched = patched.replace(invocation, '        import recipes_runtime\n'
                              '        install_input_selection(recipes_runtime)\n'
                              '        recipes_runtime.execute(stage, cfg, work)')
    new = patched + ending
    if code not in (old, new):
        raise ValueError('EXISTING_RECIPE_CODE_CHANGED')
    compile(new, '<named-input-recipe>', 'exec')
    return old, new, cfg


def update(project, baseline, adapter, datasets, backup_dir, action='apply'):
    if action not in ('apply','rollback'):
        raise ValueError('ACTION')
    definitions = [
        ('LEGAL_01_UNZIP_RAW_R1','unpack',('landing',),'raw'),
        ('LEGAL_02_STRUCTURE_GENOS_R1','structure',('landing','raw','connection'),'structured'),
        ('LEGAL_03_LOAD_SILVER_R1','load',('landing','structured'),'load'),
    ]
    plans = []
    shared_cfg = None
    # Inspect every code/edge before saving any change. An unknown custom edit is
    # preserved. Re-execution accepts an already applied subset after a lost reply.
    for name,stage,roles,out in definitions:
        recipe = project.get_recipe(name)
        settings = recipe.get_settings()
        before = settings.get_code()
        old,new,cfg = expected_sources(before,stage,baseline,adapter)
        if shared_cfg is not None and cfg != shared_cfg:
            raise ValueError('CROSS_RECIPE_CONFIG_CHANGED')
        shared_cfg = cfg
        inputs = set(cfg[role] for role in roles)
        outputs = {cfg[out]} | (set(datasets) if stage == 'load' else set())
        if set(settings.get_flat_input_refs()) != inputs or set(settings.get_flat_output_refs()) != outputs:
            raise ValueError('RECIPE_FLOW_CHANGED: '+name)
        plans.append({'name':name,'recipe':recipe,'before':before,'old':old,'new':new,
                      'target':new if action=='apply' else old,'inputs':inputs,'outputs':outputs})
    directory = Path(backup_dir)
    directory.mkdir(parents=True,exist_ok=True)
    for plan in plans:
        p = directory/(plan['name']+'.before.txt')
        if p.exists():
            if p.read_text(encoding='utf-8') != plan['old']:
                raise ValueError('LOCAL_BACKUP_CONFLICT: '+plan['name'])
        else:
            p.write_text(plan['old'],encoding='utf-8')
    log = directory/'updates.jsonl'
    def record(value):
        with log.open('a',encoding='utf-8') as f:
            f.write(json.dumps(value,sort_keys=True)+'\n')
    for plan in plans:
        name,recipe,target = plan['name'],plan['recipe'],plan['target']
        settings = recipe.get_settings()
        if settings.get_code() != plan['before']:
            raise ValueError('RECIPE_CONCURRENT_CHANGE: '+name)
        if (set(settings.get_flat_input_refs()) != plan['inputs']
                or set(settings.get_flat_output_refs()) != plan['outputs']):
            raise ValueError('RECIPE_CONCURRENT_FLOW_CHANGE: '+name)
        if plan['before'] != target:
            record({'name':name,'action':action,'status':'SAVE_INTENT',
                    'before':sha(plan['before']),'after':sha(target)})
            settings.set_code(target)
            try:
                settings.save()
            except Exception:
                record({'name':name,'action':action,'status':'SAVE_UNCONFIRMED'})
                raise
        observed = recipe.get_settings()
        if (observed.get_code() != target or set(observed.get_flat_input_refs()) != plan['inputs']
                or set(observed.get_flat_output_refs()) != plan['outputs']):
            raise ValueError('RECIPE_READBACK: '+name)
        record({'name':name,'action':action,'status':'VERIFIED','sha256':sha(target)})
        print('RECIPE_INPUT_SELECTION_READY',name,flush=True)
    result={'status':'INPUT_SELECTION_APPLIED' if action=='apply' else 'INPUT_SELECTION_ROLLED_BACK',
            'recipes':3,'s3_mutations':0,'genos_calls':0,'oracle_calls':0,
            'backup_dir':str(directory.resolve())}
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result
