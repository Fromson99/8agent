from pathlib import Path
import hashlib, io, json, os, shutil, subprocess, sys, tempfile, zipfile
ROOT=Path.cwd(); OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main123_full_20261030_r1'; NAME='GENOS_MAIN123_FULL_20261030_R1'
record=json.loads((OUT/'HANDOFF.json').read_text()); results=[]
def ok(name, condition):
    results.append({'name':name,'passed':bool(condition)})
    assert condition,name
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def scan_zip(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist();ok('archive unique safe paths', len(names)==len(set(names)) and all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names))
        ok('no forbidden JS attachment extensions',all(Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs') for n in names))
        for n in names:
            if n.lower().endswith('.zip'):scan_zip(z.read(n))
scan_zip((OUT/(NAME+'.zip')).read_bytes())
for row in record['attachments']:ok('attachment hash '+row['filename'],sha(Path(row['path']))==row['sha256'])
with tempfile.TemporaryDirectory(prefix='main123-mail-check-') as tmp:
    tmp=Path(tmp);transfer=tmp/'TRANSFER';transfer.mkdir();pkg=transfer/NAME
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as z:z.extractall(pkg)
    dev=tmp/'DEV';dev.mkdir()
    active=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text());release=json.loads((ROOT/active['manifest_path']).read_text());source=ROOT/release['code_root']
    for name in release['files']:
        p=dev/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,p)
    for n in ['requirements-serving.txt','requirements.txt','06_TOOLS/COMMANDS/genos_generation_e2e.py']:
        p=dev/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
    (dev/'01_DATA').mkdir();(dev/'01_DATA/keep.txt').write_text('unchanged local data');(dev/'.env').write_text('TEST_ONLY=unchanged')
    newfile='02_BACKEND/semantic_runtime/ontology/recorded_fields.py'
    if not (dev/newfile).exists():
        matches=list(dev.rglob('recorded_fields.py'));assert len(matches)==1;newfile=matches[0].relative_to(dev).as_posix()
    (dev/newfile).unlink()
    oldfile=dev/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'; oldfile.write_bytes(b'# prior committed version\n'+oldfile.read_bytes())
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')};env.update(GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null')
    def git(*args):return subprocess.run(['git','-C',str(dev),*args],env=env,capture_output=True,check=True)
    git('init','-q');git('add','.');git('-c','user.name=Package verification','-c','user.email=package-check@example.invalid','commit','-qm','isolated test baseline')
    before={p.relative_to(dev).as_posix():sha(p) for p in dev.rglob('*') if p.is_file() and '.git' not in p.parts}
    logs=[]
    def run(cmd, success=True):
        r=subprocess.run(['bash',str(pkg/(NAME+'_RUN.txt')),cmd,'--root',str(dev)],cwd=transfer,env=env,capture_output=True,text=True,timeout=120)
        logs.append({'command':cmd,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        ok(cmd+(' pass' if success else ' refusal'),(r.returncode==0)==success)
        return r
    js=dev/'02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js';raw=js.read_bytes();js.write_bytes(raw+b'\n');run('check',False);js.write_bytes(raw)
    original=oldfile.read_bytes();oldfile.write_bytes(original+b'# uncommitted local edit\n');run('check',False);oldfile.write_bytes(original)
    run('check');run('apply');run('apply');run('gate')
    ok('all 489 selected files exact after apply',all(sha(dev/p)==h for p,h in release['files'].items()))
    ok('new module installed',(dev/newfile).is_file())
    ok('data and env preserved',sha(dev/'01_DATA/keep.txt')==before['01_DATA/keep.txt'] and sha(dev/'.env')==before['.env'])
    git('add','.');git('-c','user.name=Package verification','-c','user.email=package-check@example.invalid','commit','-qm','isolated MAIN123 verification')
    run('gate-code')
    # A later user's edit must prevent partial rollback.
    raw=oldfile.read_bytes();oldfile.write_bytes(raw+b'# later edit\n');run('rollback',False);oldfile.write_bytes(raw)
    run('rollback')
    after={p.relative_to(dev).as_posix():sha(p) for p in dev.rglob('*') if p.is_file() and '.git' not in p.parts}
    ok('rollback restores exact pre-install file set and bytes',before==after)
    run('apply',False)
    ok('persistent logs and exit files',len(list((transfer/'main123-full-r1-logs').glob('*.log')))==len(logs) and len(list((transfer/'main123-full-r1-logs').glob('*.exit')))==len(logs))
    (OUT/'VALIDATION_COMMAND_LOGS.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2)+'\n')
(OUT/'VALIDATION.json').write_text(json.dumps({'passed':len(results),'failed':0,'checks':results,'model_calls':0,'field_genos_verified':False},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':len(results),'failed':0,'isolated_apply_reapply_rollback':True,'selected_files_exact':489,'field_genos_verified':False}))
