"""Update only known recipe 02 sources and preserve the real prior code."""
import ast
import hashlib
import json
from pathlib import Path


def expected(code, baseline, named, resume):
    call = ast.parse(code).body[-1]
    if (not isinstance(call, ast.Expr) or not isinstance(call.value, ast.Call)
            or not isinstance(call.value.func, ast.Name) or call.value.func.id != 'run_recipe'
            or len(call.value.args) != 2 or call.value.keywords):
        raise ValueError('RECIPE_ENTRY_CHANGED')
    stage, cfg = map(ast.literal_eval, call.value.args)
    if (stage != 'structure' or not isinstance(cfg,dict)
            or set(cfg) != {'landing','connection','raw','structured','load'}
            or cfg['landing'] != 'ehA8dpVm'
            or any(not isinstance(v,str) or not v for v in cfg.values())):
        raise ValueError('RECIPE_CONFIG_CHANGED')
    ending = '\nrun_recipe(' + repr(stage) + ', ' + repr(cfg) + ')\n'
    anchor = '\ndef run_recipe(stage, cfg):\n'
    invoke = '        import recipes_runtime\n        recipes_runtime.execute(stage, cfg, work)'
    if baseline.count(anchor) != 1 or baseline.count(invoke) != 1:
        raise ValueError('BASELINE_ANCHOR_CHANGED')
    r1 = baseline + ending
    r2 = baseline.replace(anchor,'\n'+named+anchor).replace(invoke,
        '        import recipes_runtime\n        install_input_selection(recipes_runtime)\n'
        '        recipes_runtime.execute(stage, cfg, work)') + ending
    r3 = baseline.replace(anchor,'\n'+named+'\n'+resume+anchor).replace(invoke,
        '        import recipes_runtime\n        install_input_selection(recipes_runtime)\n'
        '        install_resume(recipes_runtime)\n        recipes_runtime.execute(stage, cfg, work)') + ending
    if code not in (r1,r2,r3):
        raise ValueError('EXISTING_RECIPE_CODE_CHANGED')
    compile(r3,'<resume-recipe>','exec')
    return cfg, r3, (r1,r2)


def update(project, baseline, named, resume, directory, action='apply'):
    if action not in ('apply','rollback','inspect'):
        raise ValueError('ACTION')
    recipe = project.get_recipe('LEGAL_02_STRUCTURE_GENOS_R1')
    settings = recipe.get_settings()
    before = settings.get_code()
    cfg, target, old = expected(before,baseline,named,resume)
    inputs = {cfg[k] for k in ('landing','raw','connection')}
    outputs = {cfg['structured']}
    def edges(s):
        return set(s.get_flat_input_refs()) == inputs and set(s.get_flat_output_refs()) == outputs
    if not edges(settings):
        raise ValueError('RECIPE_FLOW_CHANGED')
    if action == 'inspect':
        return cfg
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    backup = directory/'LEGAL_02_STRUCTURE_GENOS_R1.before.txt'
    if backup.exists():
        if backup.read_text(encoding='utf-8') not in old:
            raise ValueError('BACKUP_CONFLICT')
    elif before in old:
        backup.write_text(before,encoding='utf-8')
    if action == 'rollback':
        if not backup.is_file():
            raise ValueError('ORIGINAL_BACKUP_REQUIRED')
        target = backup.read_text(encoding='utf-8')
    current = recipe.get_settings()
    if current.get_code() != before or not edges(current):
        raise ValueError('RECIPE_CONCURRENT_CHANGE')
    def event(status):
        with (directory/'updates.jsonl').open('a',encoding='utf-8') as out:
            out.write(json.dumps({'action':action,'status':status,
                'before':hashlib.sha256(before.encode()).hexdigest(),
                'after':hashlib.sha256(target.encode()).hexdigest()})+'\n')
    if before != target:
        event('SAVE_INTENT')
        current.set_code(target)
        try:
            current.save()
        except Exception:
            event('SAVE_UNCONFIRMED')
            raise
    observed = recipe.get_settings()
    if observed.get_code() != target or not edges(observed):
        raise ValueError('RECIPE_READBACK')
    event('VERIFIED')
    print('RESUME_FIX_APPLIED' if action == 'apply' else 'RESUME_FIX_ROLLED_BACK', flush=True)
    return cfg
