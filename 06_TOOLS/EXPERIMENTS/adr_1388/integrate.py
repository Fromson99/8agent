"""Apply the tested authoring files and update their entries in current engine pins."""
from common import *
import importlib.util
import shutil

candidate = read(DES/'candidate-repaired.json')
products = read(DES/'candidate-path.json')['product_files']
before = read(ART/'integration-current-base.json')
snapshot = ROOT/candidate['code_root']
parent = read(DES/'candidate-parent.json')['selected_files']
assert all(sha(snapshot/n)==h for n,h in candidate['selected_files'].items())
assert all(before[n]==parent[n] for n in products)
# Stage against current file bytes, never copy unrelated parent manifests.
updates = {n:(snapshot/n).read_bytes() for n in products}
def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def fingerprint(content):
    return hashlib.sha256(content).hexdigest()

pipeline_name='00_SYSTEM/PIPELINE.json'
pipeline=read(ROOT/pipeline_name)
for item in pipeline['engines'].values():
    name=item['manifest']
    manifest=read(ROOT/name)
    assert item['sha256']==sha(ROOT/name)
    relevant=set(products)&manifest.get('files',{}).keys()
    if not relevant:
        continue
    for n in relevant:
        assert manifest['files'][n]==before[n]
        manifest['files'][n]=fingerprint(updates[n])
    updates[name]=encoded(manifest)
    item['sha256']=fingerprint(updates[name])
updates[pipeline_name]=encoded(pipeline)

def assert_unchanged():
    assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent change: hold integration'

assert_unchanged()
backup=ART/'working-before'
for n in updates:
    p=backup/n
    p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/n,p)
assert_unchanged()
applied=[]
try:
    for n,content in updates.items():
        p=ROOT/n
        assert sha(p)==before[n],n
        tmp=p.with_name('.'+p.name+'.adr1388')
        with tmp.open('xb') as stream:
            stream.write(content)
        os.replace(tmp,p)
        applied.append(n)
    spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    engines,count,errors=mod.check(ROOT)
    assert not errors,errors
    assert all(sha(ROOT/n)==(fingerprint(updates[n]) if n in updates else h) for n,h in before.items())
except BaseException:
    for n in reversed(applied):
        p=ROOT/n
        if sha(p)==fingerprint(updates[n]):
            tmp=p.with_name('.'+p.name+'.adr1388-restore')
            shutil.copyfile(backup/n,tmp)
            os.replace(tmp,p)
    raise
current={n:sha(ROOT/n) for n in before}
put(ART/'working-integration.json',{'product_files':products,'total_changed':len(updates),
    'previous_hashes':{n:before[n] for n in updates},'changed_hashes':{n:current[n] for n in updates},
    'full_working_hashes':current,'parent_vs_working_unrelated_differences_preserved':sum(before[n]!=h for n,h in parent.items() if n not in updates),
    'tested_products_identical':all(current[n]==candidate['selected_files'][n] for n in products),
    'preflight':{'engines':engines,'files':count,'errors':errors}})
print('Working integration verified',len(updates),engines,count)
