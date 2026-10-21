"""One entrypoint for the current mailed GENOS serving updates and selection."""
import argparse,gzip,importlib.util,json,os,subprocess,sys,types
from pathlib import Path
import apply_patch as installer
from spec_loader import load

HERE=Path(__file__).resolve().parent
SPEC=load()

def run(command,root,capture=False):
    result=subprocess.run(command,cwd=root,text=True,capture_output=capture,
        env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(root),
             'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'PYTHONDONTWRITEBYTECODE':'1','GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'})
    if result.returncode:
        if capture:print(result.stdout+result.stderr,flush=True)
        raise RuntimeError('command failed with exit '+str(result.returncode))
    return result

def generation(root,explicit=None):
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,root/path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    # Root inventory and whole-input signature were checked before this call.
    paths=load('fixed_deployment_paths','02_BACKEND/semantic_runtime/deployment_paths.py')
    selector=load('operator_generation','06_TOOLS/COMMANDS/genos_generation_e2e.py')
    settings=dict(os.environ);config=paths.install(root,environment=settings)
    if config is not None:
        selected=selector.selected_generation(explicit,settings=settings)
        paths.verify_generation(config,selected)
        source=paths.CONFIG
        os.environ['GENOS_RUNTIME_DIR']=settings['GENOS_RUNTIME_DIR'];os.environ.pop('GENOS_STATE_DIR',None)
    else:
        selected=selector.selected_generation(explicit) if explicit else selector.operator_generation(root)
        source='existing operator environment/pointer'
    os.environ['GENOS_GENERATION']=str(selected)
    print('GENERATION_SOURCE='+source+' GENERATION='+str(selected),flush=True)
    return selected

def scanner(root,payload):
    sys.path.insert(0,str(root/'02_BACKEND'))
    for name in ('semantic_runtime.search_selection','lawrag.pipeline.search_selection'):
        relative='02_BACKEND/'+name.replace('.','/')+'.py'
        module=types.ModuleType(name);module.__file__=str(root/relative);sys.modules[name]=module
        exec(compile(payload[relative],module.__file__,'exec'),module.__dict__)
    return module

def latest_backup(root):
    digest=installer.sha((root/'CODE_MANIFEST.json').read_bytes());found=[]
    for path in (root/'TRANSFER/cumulative-mail-r1').glob('backup-*/receipt.json'):
        v=json.loads(path.read_bytes())
        if v.get('root')==str(root) and v.get('revision')==installer.VERSION and v.get('state')=='VERIFIED' and v.get('code_manifest_sha256')==digest:
            found.append(path.parent)
    if len(found)!=1:raise ValueError('exact verified backup missing or ambiguous; keep previous receipts')
    return found[0]

def write_state(value):installer.atomic(HERE/'STATUS.json',installer.encoded(value))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',default='install',choices=['check','install','apply','status','verify','gate','undo'])
    parser.add_argument('--root',type=Path,default=Path(os.environ.get('GENOS_DEV_ROOT',os.environ.get('GENOS_DEV',str(Path.home()/'DEV')))))
    parser.add_argument('--generation',type=Path)
    a=parser.parse_args();root=a.root.expanduser().resolve(strict=True)
    print('CODE_ROOT='+str(root)+' PYTHON='+sys.executable+' VERSION='+sys.version,flush=True)
    os.environ.update(GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
    top=run(['git','rev-parse','--show-toplevel'],root,True).stdout.strip()
    if Path(top).resolve()!=root:raise ValueError('existing Git checkout root required')
    cli=[sys.executable,'-m','lawrag.pipeline.search_selection']
    if a.action=='undo':
        state=json.loads((HERE/'STATUS.json').read_bytes())
        if state['code_root']!=str(root):raise ValueError('foreign run state')
        with installer.locked(root):
            installer.undo(root,Path(state['backup']),check_only=True)
            if state.get('selection_receipt'):
                run([*cli,'rollback','--receipt',state['selection_receipt']],root)
            installer.undo(root,Path(state['backup']))
        state.update(phase='RESTORED_REDEPLOY_PREVIOUS_REVISION');write_state(state)
        print('RESTORED; original code and selection; deploy previous verified revision separately');return
    with installer.locked(root):
        before=json.loads((root/'CODE_MANIFEST.json').read_bytes())
        already=before.get('cumulative_mail',{}).get('revision')==installer.VERSION
        if already:
            installer.verify(root,SPEC);candidate=installer.inventory(root,before)
            print('CODE_ALREADY_APPLIED; verified exact final inventory',flush=True)
        else:
            _,payload,changes,_,_=installer.prepared(root,SPEC);candidate={**payload,**changes}
            print('CODE_PLAN product/inventory paths='+str(len(changes)),flush=True)
        g=generation(root,a.generation)
        if a.action in ('status','verify','gate') and not already:
            raise ValueError('cumulative code not installed; use install')
        if a.action in ('status','verify'):
            run([*cli,'status','--generation',str(g)],root);return
        if a.action=='gate':
            backup=latest_backup(root);receipt=json.loads((backup/'receipt.json').read_bytes())
            archive=backup/'APPLIED_CODE.zip'
            if installer.sha(archive.read_bytes())!=receipt['code_zip_sha256']:raise ValueError('gate archive changed')
            run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),'--code-zip',str(archive),
                '--deploy-root',str(root),'--generation',str(g)],root)
            status=json.loads(run([*cli,'status','--generation',str(g)],root,True).stdout)
            state=json.loads((HERE/'STATUS.json').read_bytes())
            if status['selection_sha256']!=state.get('selection_sha256'):raise ValueError('selection changed since install')
            state.update(phase='GATE_PASSED_PUSH_REVISION_WORKFLOW_PENDING',commit=run(['git','rev-parse','HEAD'],root,True).stdout.strip())
            write_state(state);print('GATE PASS; push, new revision, SSE restart and workflow test pending');return
        value=scanner(root,candidate).plan(g);plan=HERE/'SELECTION_PLAN.json';raw=installer.encoded(value)
        if plan.exists() and plan.read_bytes()!=raw:raise ValueError('generation metadata/plan changed; previous plan preserved')
        installer.atomic(plan,raw)
        print(json.dumps({'search_plan':value['counts'],'warnings':len(value['warnings']),'rebuild':False,'model_calls':0},ensure_ascii=False),flush=True)
        if a.action=='check':print('CHECK PASS; no code/data selection changed');return
        artifacts=root/'TRANSFER/cumulative-mail-r1';artifacts.mkdir(parents=True,exist_ok=True)
        installer.apply(root,SPEC,artifacts)
        backup=latest_backup(root)
        state={'code_root':str(root),'generation':str(g),'generation_manifest_sha256':installer.sha((g/'manifest.json').read_bytes()),
            'backup':str(backup),'code_zip_sha256':installer.sha((backup/'APPLIED_CODE.zip').read_bytes()),
            'python':sys.executable,'python_version':sys.version,'phase':'CODE_APPLIED_SELECTION_PENDING',
            'code_serving_revision':None,'workflow_editor':'MANUAL_UPDATE_OR_COMPARE_REQUIRED','workflow_test':'NOT_RUN'}
        previous=json.loads((HERE/'STATUS.json').read_bytes()) if (HERE/'STATUS.json').exists() else {}
        if previous.get('code_root')==str(root) and previous.get('generation')==str(g):
            for key in ('selection_receipt','selection_sha256'):
                if key in previous:state[key]=previous[key]
        write_state(state)
        try:
            applied=json.loads(run([*cli,'apply','--plan',str(plan)],root,True).stdout)
            if applied.get('receipt'):state['selection_receipt']=applied['receipt']
            state['selection_sha256']=applied['selection_sha256']
            run([*cli,'status','--generation',str(g)],root)
        except Exception:
            state['phase']='CODE_APPLIED_SELECTION_FAILED';write_state(state);raise
        state['phase']='CODE_AND_SELECTION_APPLIED_DEPLOYMENT_PENDING';write_state(state)
        print('ALL_CODE_APPLIED; deployment and workflow editor/test remain',flush=True)
        print('STATUS='+str(HERE/'STATUS.json')+' BACKUP='+str(backup),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('CUMULATIVE_FAILED: '+str(exc),file=sys.stderr,flush=True);raise SystemExit(1)
