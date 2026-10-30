"""Delete only this experiment's two superseded bulk transport copies."""
from pathlib import Path
import json,hashlib,os,shutil,time
R=Path('/home/jin/8-AGENT');RUN=R/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector/artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def free():return {'wsl':shutil.disk_usage(R).free,'c':shutil.disk_usage('/mnt/c').free}
def save(v):
    with (RUN/'owned-staging-cleanup.json').open('w') as f:json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
assert read(RUN/'result.json')['status']=='COMPLETE_SCOPED_NATIVE_GOLD_EXPERIMENT'
assert read(RUN/'operator-cli-checks.json')['status']=='PASS'
assert not (RUN/'owned-staging-cleanup.json').exists(), 'immutable cleanup receipt already exists'
current_sha=read(RUN/'prepare-result.json')['sha256'];items=[]
for directory in ['attempt-29','attempt-21-global-terms']:
    parent=RUN/directory;path=parent/'scoped-query.sqlite';expected=read(parent/'prepare-result.json')['sha256']
    assert path.is_file() and not path.is_symlink() and path.resolve().parent==parent.resolve()
    st=path.stat();assert st.st_nlink==1 and expected!=current_sha and sha(path)==expected
    items.append({'path':str(path.relative_to(R)),'sha256':expected,'bytes':st.st_size,'allocated_bytes':st.st_blocks*512,'inode':st.st_ino,'deleted':False})
receipt={'status':'PREPARED','scope':'Only two owned superseded staging copies; current GOLD, current staging and original databases retained','before_free':free(),'items':items};save(receipt)
for item in items:
    path=R/item['path'];assert path.stat().st_ino==item['inode'];path.unlink();item['deleted']=True;save(receipt)
receipt.update(status='COMPLETE',after_free=free(),completed_at=time.time(),allocated_bytes_removed=sum(x['allocated_bytes'] for x in items));save(receipt)
print('OWNED STAGES REMOVED',len(items),receipt['allocated_bytes_removed'])
