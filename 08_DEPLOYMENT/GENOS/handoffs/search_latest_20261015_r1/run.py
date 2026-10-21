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
    p.add_argument('action',choices=['check','apply','status','gate','rollback','undo-code'])
    p.add_argument('--root',type=Path,default=Path(os.environ.get('GENOS_DEV_ROOT',str(Path.home()/'DEV'))))
    p.add_argument('--generation',type=Path);p.add_argument('--plan',type=Path,default=HERE/'SELECTION_PLAN.json')
    p.add_argument('--receipt',type=Path);p.add_argument('--backup',type=Path)
    a=p.parse_args();root=a.root.expanduser().resolve(strict=True)
    print('CODE_ROOT='+str(root)+' PYTHON='+sys.executable+' VERSION='+sys.version,flush=True)
    installer=[sys.executable,str(HERE/'apply.py'),'--root',str(root)]
    cli=[sys.executable,str(root/'06_TOOLS/pipeline.py'),'search-selection']
    if a.action=='undo-code':
        if a.backup is None:p.error('--backup is required (CODE_BACKUP path)')
        run([*installer,'undo','--backup',str(a.backup)],root);return
    if a.action=='rollback':
        if a.receipt is None:p.error('--receipt is required (selection receipt.json)')
        run([*cli,'rollback','--receipt',str(a.receipt)],root);return
    spec=importlib.util.spec_from_file_location('selected_generation',root/'06_TOOLS/COMMANDS/genos_generation_e2e.py')
    selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
    g=selector.selected_generation(a.generation) if a.generation else selector.operator_generation(root)
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
    result=run([*cli,'apply','--plan',str(a.plan)],root,capture=True)
    applied=json.loads(result.stdout)
    if applied['state']!='ALREADY_APPLIED' or not (HERE/'SELECTION_APPLIED.json').exists():
        atomic(HERE/'SELECTION_APPLIED.json',encode(applied))
    print(result.stdout,flush=True)
    run([*cli,'status','--generation',str(g)],root)
    print('APPLIED. Commit reviewed files, run gate, push, deploy new revision, restart SSE. Workflow editor unchanged.',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('FAILED: '+str(exc),file=sys.stderr);raise SystemExit(1)
