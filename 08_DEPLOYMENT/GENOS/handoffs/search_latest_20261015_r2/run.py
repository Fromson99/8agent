"""TRANSFER operator workflow. Checkout and selected generation are explicit."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types
from apply import HERE,atomic,encode,payload,sha


def selected_generation(root, explicit=None):
    """Use the same fixed deployment binding as service.py, then verify its pin.

    A fixed operator config overrides the codespace's legacy GENOS_DATA_ROOT,
    exactly as deployment_paths.install does at service startup. No CURRENT is
    created and no directory is selected by timestamp or filename.
    """
    package, _ = payload()
    pins = {r['path']: r['sha256'] for r in package['manifest']['required_files']}
    def load(name, relative):
        file = root / relative
        if file.is_symlink() or sha(file.read_bytes()) != pins[relative]:
            raise ValueError('selection dependency differs: ' + relative)
        spec = importlib.util.spec_from_file_location(name, file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    binding = load('deployed_paths', '02_BACKEND/semantic_runtime/deployment_paths.py')
    selector = load('selected_generation', '06_TOOLS/COMMANDS/genos_generation_e2e.py')
    settings = dict(os.environ)
    config = binding.install(root, environment=settings)
    if config is not None:
        generation = selector.selected_generation(explicit, settings=settings)
        binding.verify_generation(config, generation)
        source = binding.CONFIG
    else:
        generation = (selector.selected_generation(explicit) if explicit is not None
                      else selector.operator_generation(root))
        source = 'explicit' if explicit is not None else 'existing operator settings'
    # Subprocess gates must see exactly the generation selected above.
    os.environ['GENOS_GENERATION'] = str(generation)
    if config is not None:
        os.environ['GENOS_RUNTIME_DIR'] = settings['GENOS_RUNTIME_DIR']
        os.environ.pop('GENOS_STATE_DIR', None)
    print('GENERATION_SOURCE=' + source, flush=True)
    return generation


def run(command,root,*,capture=False):
    try:
        return subprocess.run(command,cwd=root,check=True,text=True,capture_output=capture,
            env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(root),
                 'LAWRAG_TOOL_WORKSPACE_ROOT':str(root)})
    except subprocess.CalledProcessError as exc:
        if capture:
            if exc.stdout:print(exc.stdout,flush=True)
            if exc.stderr:print(exc.stderr,file=sys.stderr,flush=True)
        raise


def load_scanner(root):
    _,files=payload();sys.path.insert(0,str(root/'02_BACKEND'))
    for name,path in [('semantic_runtime.search_selection','02_BACKEND/semantic_runtime/search_selection.py'),
                      ('lawrag.pipeline.search_selection','02_BACKEND/lawrag/pipeline/search_selection.py')]:
        m=types.ModuleType(name);m.__file__=str(HERE/path);sys.modules[name]=m
        exec(compile(files[path],m.__file__,'exec'),m.__dict__)
    return m


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['check','apply','install','status','gate','rollback','undo-code'])
    p.add_argument('--root',type=Path,default=Path(os.environ.get('GENOS_DEV_ROOT',str(Path.home()/'DEV'))))
    p.add_argument('--generation',type=Path);p.add_argument('--plan',type=Path,default=HERE/'SELECTION_PLAN.json')
    p.add_argument('--receipt',type=Path);p.add_argument('--backup',type=Path)
    a=p.parse_args();root=a.root.expanduser().resolve(strict=True)
    if a.action=='install':a.action='apply'
    print('CODE_ROOT='+str(root)+' PYTHON='+sys.executable+' VERSION='+sys.version,flush=True)
    installer=[sys.executable,str(HERE/'apply.py'),'--root',str(root)]
    # GENOS serving packages do not carry the local build CLI and its dependency
    # tree. Invoke the same search-selection implementation directly as a module.
    cli=[sys.executable,'-m','lawrag.pipeline.search_selection']
    if a.action=='undo-code':
        if a.backup is None:p.error('--backup is required (CODE_BACKUP path)')
        run([*installer,'undo','--backup',str(a.backup)],root);return
    if a.action=='rollback':
        if a.receipt is None:p.error('--receipt is required (selection receipt.json)')
        run([*cli,'rollback','--receipt',str(a.receipt)],root);return
    g=selected_generation(root,a.generation)
    print('GENERATION='+str(g),flush=True)
    if a.action=='status':run([*cli,'status','--generation',str(g)],root);return
    if a.action=='gate':
        run([*installer,'verify'],root)
        run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),
             '--code-zip',str(HERE/'CODE_APPLIED.zip'),'--deploy-root',str(root),'--generation',str(g)],root)
        status=run([*cli,'status','--generation',str(g)],root,capture=True)
        value=json.loads(status.stdout)
        expected=json.loads((HERE/'SELECTION_APPLIED.json').read_text())
        if value['selection_sha256']!=expected['selection_sha256']:raise ValueError('selection differs from applied receipt')
        commit=run(['git','rev-parse','HEAD'],root,capture=True).stdout.strip()
        atomic(HERE/'VERIFIED_CHECKOUT.json',encode({'code_root':str(root),'commit':commit,
            'generation':str(g),'generation_manifest_sha256':sha((g/'manifest.json').read_bytes()),
            'code_zip_sha256':sha((HERE/'CODE_APPLIED.zip').read_bytes()),'search_selection':value,
            'code_serving_revision':None,'field_workflow_test':'UNVERIFIED'}))
        print('GATE PASS; push/new revision/SSE restart/workflow test remain');return
    run([*installer,'check'],root)
    scanner=load_scanner(root);value=scanner.plan(g);raw=encode(value)
    if a.plan.exists() and a.plan.read_bytes()!=raw:raise ValueError('saved plan changed; choose another --plan filename')
    atomic(a.plan,raw)
    print(json.dumps({'plan':str(a.plan),'counts':value['counts'],'warning_count':len(value['warnings']),
                      'rebuild':False,'model_calls':0},ensure_ascii=False),flush=True)
    if a.action=='check':print('CHECK PASS; selection not applied');return
    run([*installer,'apply'],root)
    state={'code_root':str(root),'generation':str(g),'generation_manifest_sha256':sha((g/'manifest.json').read_bytes()),
           'phase':'CODE_APPLIED_SELECTION_PENDING','code_serving_revision':None,'workflow_test':'NOT_RUN'}
    atomic(HERE/'RUN_STATE.json',encode(state))
    try:
        result=run([*cli,'apply','--plan',str(a.plan)],root,capture=True)
    except Exception:
        state['phase']='CODE_APPLIED_SELECTION_FAILED'
        atomic(HERE/'RUN_STATE.json',encode(state))
        print('Code remains applied; selection failed. Review this log, then rerun apply or use rollback/undo-code.',flush=True)
        raise
    applied=json.loads(result.stdout)
    if applied['state']!='ALREADY_APPLIED' or not (HERE/'SELECTION_APPLIED.json').exists():
        atomic(HERE/'SELECTION_APPLIED.json',encode(applied))
    print(result.stdout,flush=True)
    run([*cli,'status','--generation',str(g)],root)
    state.update(phase='CODE_AND_SELECTION_APPLIED_DEPLOYMENT_PENDING',selection_sha256=applied['selection_sha256'])
    atomic(HERE/'RUN_STATE.json',encode(state))
    print('APPLIED. Commit reviewed files, run gate, push, deploy new revision, restart SSE. Workflow editor unchanged.',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('FAILED: '+str(exc),file=sys.stderr);raise SystemExit(1)
