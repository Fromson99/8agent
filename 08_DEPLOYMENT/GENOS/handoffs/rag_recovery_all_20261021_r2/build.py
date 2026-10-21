"""Freeze recovery R1 plus the exact verified gap reconsideration; preserve prior packages."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_RAG_RECOVERY_ALL_20261021_R2'
PRIOR = HERE.with_name('rag_recovery_all_20261021_r1')
BASE = HERE.with_name('main96_ad_disabled_20261021_r1')
AUDIT = ROOT/'09_ARTIFACTS/AUDITS/20261021-gap-finish-reconsider'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')

assert not (HERE/'SEALED.json').exists(), 'Already sealed'
prior = read(PRIOR/'PACKAGE.json'); base = read(BASE/'PACKAGE.json')
import gzip
verification = read(AUDIT/'FINAL_VERIFICATION.json')
names = ['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('request_repair.py','decision_projection.py','law_navigation.py')]
verified = {'runtime_sha256':{n:verification['after'][n] for n in names}}
assert sha(PRIOR/'GENOS_RAG_RECOVERY_ALL_20261021_R1.zip') == read(PRIOR/'SEALED.json')['archive_sha256']
for n in names:
    before = gzip.decompress((AUDIT/'before'/str(n+'.gz')).read_bytes())
    assert hashlib.sha256(before).hexdigest() == prior['code'][n], n
after = dict(prior['code'])
for n in prior['patch']:
    source = PRIOR/'payload'/n
    assert sha(source) == prior['code'][n], n
    target = HERE/'payload'/n; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
for n, expected in verified['runtime_sha256'].items():
    raw = gzip.decompress((AUDIT/'after'/str(n+'.gz')).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == expected, n
    target = HERE/'payload'/n; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw); after[n] = expected
for n in sorted(prior['code'], key=lambda name: (not name.startswith('02_BACKEND/workflow/'), name)):
    if not (n.startswith('02_BACKEND/ENGINES/') or n.startswith('02_BACKEND/workflow/') and n.endswith('/manifest.json')): continue
    path = HERE/'payload'/n
    value = read(path)
    for name, expected in list(verified['runtime_sha256'].items()):
        key = name.removeprefix('02_BACKEND/workflow/') if n.startswith('02_BACKEND/workflow/') else name
        if key in value['files']: value['files'][key] = expected
    save(path, value); after[n] = sha(path)
    if n.startswith('02_BACKEND/workflow/'): verified['runtime_sha256'][n] = after[n]
path = HERE/'payload/00_SYSTEM/PIPELINE.json'; pipeline = read(path)
def update_pin(value):
    if isinstance(value, dict):
        if value.get('manifest') in after and 'sha256' in value: value['sha256'] = after[value['manifest']]
        for child in value.values(): update_pin(child)
    elif isinstance(value, list):
        for child in value: update_pin(child)
update_pin(pipeline)
save(path, pipeline); after['00_SYSTEM/PIPELINE.json'] = sha(path)
patch = sorted(n for n,h in after.items() if base['code'].get(n) != h)
for n in patch:
    assert sha(HERE/'payload'/n) == after[n], n
    if n.endswith('.py'): ast.parse((HERE/'payload'/n).read_bytes(), feature_version=(3,11))
for n in ('runner.py','genos_release_gate.py'):
    (HERE/n).write_bytes((PRIOR/n).read_bytes())
run = (PRIOR/'GENOS_RAG_RECOVERY_ALL_20261021_R1_RUN.txt').read_text()
run = run.replace('GENOS_RAG_RECOVERY_ALL_20261021_R1', NAME)
run = run.replace('rag-recovery-all-r1-logs','rag-recovery-all-r2-logs')
run = run.replace('COMPARISON_READABLE_EXIT','RAG_RECOVERY_ALL_EXIT')
(HERE/(NAME+'_RUN.txt')).write_text(run)
subprocess.run(['bash','-n',str(HERE/(NAME+'_RUN.txt'))], check=True)
editor = 'GENOS_COMPARISON_READABLE_WORKFLOW_ALL.txt'
(HERE/editor).write_bytes((PRIOR/editor).read_bytes())
ast.parse((HERE/editor).read_bytes(), feature_version=(3,10))
manifest = {'format':'8agent-code/1', 'files':[
    {'path':n,'sha256':after[n],'bytes':(HERE/'payload'/n).stat().st_size} for n in patch],
    'required_files':[{'path':n,'sha256':h} for n,h in after.items() if n not in patch]}
save(HERE/'CODE_MANIFEST.json', manifest)
with zipfile.ZipFile(HERE/'code.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    z.write(HERE/'CODE_MANIFEST.json','CODE_MANIFEST.json')
    for n in patch: z.write(HERE/'payload'/n,n)
(HERE/'COMMIT_PATHS.txt').write_text('\n'.join(patch)+'\n')
files = ['runner.py','genos_release_gate.py',NAME+'_RUN.txt','PATCH_NOTE.txt',editor,
    'CODE_MANIFEST.json','COMMIT_PATHS.txt','code.zip','HANDOFF_VALIDATION.txt']+['payload/'+n for n in patch]
save(HERE/'PACKAGE.json', {'version':NAME,'base_release':base['base_release'],
    'code':after,'patch':patch,
    'allowed_before':{n:list(dict.fromkeys(prior['allowed_before'].get(n,[])+[prior['code'][n],h])) for n,h in after.items()},
    'payload':{n:sha(HERE/n) for n in files},'workflow_version':'1.20.6',
    'GENOS_field_verified':False,'data_modified':False,'selected_main_modified':False})
with zipfile.ZipFile(HERE/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for n in sorted(files+['PACKAGE.json']): z.write(HERE/n,n)
for p in (HERE/(NAME+'.zip'),HERE/'code.zip'):
    with zipfile.ZipFile(p) as z:
        assert not z.testzip()
        assert not any(Path(n).suffix.lower() in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
save(HERE/'BUILD.json', {'archive':NAME+'.zip','sha256':sha(HERE/(NAME+'.zip')),
    'bytes':(HERE/(NAME+'.zip')).stat().st_size,'patch_files':len(patch),'required_code_files':len(after),
    'changed_since_recovery_r1':sorted(n for n in after if after[n]!=prior['code'][n]),
    'source_root':str(HERE/'payload'),'prior_code_root':str(PRIOR),'verified_runtime_source_root':str(AUDIT/'after'),
    'code_manifest_sha256':sha(HERE/'CODE_MANIFEST.json'),'workflow_editor_sha256':sha(HERE/editor),
    'selected_release':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'GENOS_checkout':'~/DEV (physical path recorded by check)','GENOS_commit':None,
    'GENOS_generation_path':None,'GENOS_generation_manifest_sha256':None,
    'GENOS_serving_revision':None,'GENOS_revision_generation_setting':None})
(HERE/'SHA256SUMS.txt').write_text('\n'.join(sha(HERE/n)+'  '+n for n in
    [NAME+'.zip',NAME+'_RUN.txt',editor,'PATCH_NOTE.txt'])+'\n')
print(json.dumps({'archive':NAME+'.zip','bytes':(HERE/(NAME+'.zip')).stat().st_size,
    'code_files':len(after),'patch_files':len(patch)}))
