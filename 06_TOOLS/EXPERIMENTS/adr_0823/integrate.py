"""Integrate qualified file deltas only; do not activate a release."""
from pathlib import Path
import json,hashlib,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0823-comparison-partial-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');b=read(D/'baseline.json');C=R/f['code_root'];result=read(A/'artifacts/run-001/result.json');w=read(D/'working-before.json')
assert result['strict_success'] and all(result['checks'].values())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(C/n)==h for n,h in f['serving_files'].items())
changed={n:h for n,h in f['serving_files'].items() if h!=b['manifest']['files'].get(n)
         and not n.startswith('02_BACKEND/ENGINES/') and n!='00_SYSTEM/PIPELINE.json'}
pending={};observed={}
def stage(n,content):
    assert n not in pending,n
    observed[n]=sha(R/n) if (R/n).exists() else None
    pending[n]=content
def planned_sha(n):
    return hashlib.sha256(pending[n]).hexdigest() if n in pending else sha(R/n)
for n,h in changed.items():
    actual=sha(R/n) if (R/n).exists() else None
    assert actual in (w.get(n),h),n
    # Unrelated edits are never overwritten, including changes predating this task.
    assert actual in (b['manifest']['files'].get(n),h),n
    stage(n,(C/n).read_bytes())
engines={}
for p in (R/'02_BACKEND/ENGINES').rglob('*.json'):
    n=str(p.relative_to(R));v=read(p);before=encoded(v);files=v.get('files',{})
    candidate=read(C/n) if (C/n).exists() else {'files':{}}
    baseline=read(R/b['manifest']['code_root']/n) if (R/b['manifest']['code_root']/n).exists() else {'files':{}}
    for name in set(files)&set(changed):
        assert files[name] in (observed[name],changed[name]),(n,name,'engine pin conflict')
        files[name]=changed[name]
    for name in candidate.get('files',{}).keys()-baseline.get('files',{}).keys():
        target=planned_sha(name)
        assert candidate['files'][name]==target,(n,name,'candidate pin mismatch')
        assert name not in files or files[name]==target,(n,name,'added engine pin conflict')
        files[name]=target
    if encoded(v)!=before:
        stage(n,encoded(v));engines[n]=planned_sha(n)
pipeline_name='00_SYSTEM/PIPELINE.json'
p=R/pipeline_name;v=read(p);candidate=read(C/pipeline_name)
baseline=read(R/b['manifest']['code_root']/pipeline_name)
for e in v['engines'].values():
    if e['manifest'] in engines:
        assert e['sha256'] in (observed[e['manifest']],engines[e['manifest']]),('pipeline engine pin conflict',e['manifest'])
        e['sha256']=engines[e['manifest']]
def workflows(config):
    rows=config['workflows']['registered'];indexed={e['id']:e for e in rows}
    assert len(indexed)==len(rows),'duplicate workflow IDs'
    return indexed
current_workflows=workflows(v);baseline_workflows=workflows(baseline)
for workflow_id,chosen in workflows(candidate).items():
    if chosen['manifest'] not in changed:
        continue
    assert workflow_id in current_workflows and workflow_id in baseline_workflows,('workflow registration conflict',workflow_id)
    e=current_workflows[workflow_id];previous=baseline_workflows[workflow_id]
    assert e['manifest']==previous['manifest']==chosen['manifest'],('workflow manifest conflict',workflow_id)
    assert e['version'] in (previous['version'],chosen['version']),('workflow version conflict',workflow_id)
    target=planned_sha(chosen['manifest'])
    assert chosen['sha256']==target,('candidate workflow pin mismatch',workflow_id)
    assert e['sha256'] in (previous['sha256'],target),('workflow pin conflict',workflow_id)
    e['version']=chosen['version'];e['sha256']=target
stage(pipeline_name,encoded(v))
# All payloads and merge conflicts are checked before the first working write.
generation=R/read(D/'data-binding.json')['path']
preserved=[n for n,h in f['serving_files'].items() if planned_sha(n)!=h]
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for n,before in observed.items():
    assert (sha(R/n) if (R/n).exists() else None)==before,('working file changed during preflight',n)
backup=A/'artifacts/working-before';backup.mkdir(exist_ok=True);changes=[]
def save(n,content):
    p=R/n;out=backup/n
    assert (sha(p) if p.exists() else None)==observed[n],('working file changed after preflight',n)
    if p.exists() and not out.exists():out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
    p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content)
    changes.append({'path':n,'before':observed[n],'after':sha(p)})
    put(A/'artifacts/working-integration-progress.json',{'changes':changes})
for n,content in pending.items():save(n,content)
put(A/'artifacts/working-integration.json',{'status':'PASS','changes':changes,
    'preserved_other_working_differences':preserved,'verified_candidate':f['code_root'],
    'active_pointer_changed':False,'genos_deployed':False})
print('Reviewed implementation deltas integrated; unrelated working differences preserved; active pointer unchanged')
