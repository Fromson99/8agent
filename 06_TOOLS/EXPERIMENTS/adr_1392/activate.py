"""Activate only the tested staged release and verify fresh MAIN and Gold entry points."""
from common import *
import shutil,subprocess
OUT=ART/'main'
release_id='bound-chat-review-20261105-r1'
path=ROOT/'08_DEPLOYMENT/RELEASES'/release_id/'release.json'
b=read(DES/'baseline.json')
release=read(path);stage=read(OUT/'stage.json')
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json'
active_path=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
assert read(active_path)==b['pointer'] and sha(gold)==b['gold_files'][str(gold.relative_to(ROOT))]
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items())
assert release['files']==stage['files'] and all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
tested=read(ART/'prepared-review/result.json')
assert tested['code_root']==str(ROOT/release['code_root']) and tested['passed']==67 and tested['failed']==0 and tested['code_unchanged']
assert sum('test_displayed_command_reuses_failed_goal' in row['test'] for row in tested['rows'])==2
assert read(DES/'candidate-prepared.json')['selected_files']==release['files']
binding={**b['gold_binding'],'engine_root':release['code_root'],'engine_files':release['files'],'engine_release_id':release_id,'engine_manifest_sha256':sha(path),
         'engine_candidate_revision':read(DES/'candidate-integrated.json')['pin'],'inference_status':'USER_DIRECTED_MAIN146_BOUND_REVIEW_FIELD_NOT_CERTIFIED',
         'main_authorization':{'release_id':release_id,'authorization_sha256':release['authorization_sha256'],'validation_sha256':release['validation_sha256']}}
put(OUT/'gold-binding-prepared.json',binding)
backup=OUT/'gold-binding-before-exact.json'
with backup.open('xb') as f:f.write(gold.read_bytes())
def replace_from(src,dst):
    tmp=dst.with_name('.'+dst.name+'.main146-switch')
    with tmp.open('xb') as f:f.write(src.read_bytes())
    os.replace(tmp,dst)
def run(log,*args):
    with (OUT/log).open('x') as f:
        subprocess.run([str(ROOT/'.venv/bin/python'),*map(str,args)],cwd=ROOT,timeout=240,stdout=f,stderr=subprocess.STDOUT,check=True)
try:
    run('apply.log','06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',path,'--confirm-main')
    assert read(active_path)['release_id']==release_id and sha(gold)==sha(backup)
    replace_from(OUT/'gold-binding-prepared.json',gold)
    run('main-entry.log',Path(__file__).with_name('main_entry.py'))
    run('gold-entry.log',Path(__file__).with_name('gold_entry.py'))
    active=read(active_path)
    assert read(OUT/'main-entry.json')['passed'] and read(OUT/'gold-entry.json')['passed']
    assert active['generation']==146 and active['release_manifest_sha256']==sha(path)
    assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items() if n!=str(gold.relative_to(ROOT)))
    put(OUT/'activation.json',{'active':active,'files':len(stage['files']),'changed':stage['changed'],
        'main_checks':len(read(OUT/'main-entry.json')['checks']),'gold_checks':len(read(OUT/'gold-entry.json')['checks']),
        'old_pointer':b['pointer'],'old_gold_binding':str(backup.relative_to(ROOT)),'original_data':release['data_path'],'field_deployed':False})
except BaseException as exc:
    if read(active_path).get('release_id')==release_id:
        run('rollback.log','06_TOOLS/run_tool.py','rag_main_promotion.py','rollback','--confirm-main')
        if sha(gold)==sha(OUT/'gold-binding-prepared.json'):replace_from(backup,gold)
        assert read(active_path)['release_manifest_sha256']==b['pointer']['release_manifest_sha256'] and sha(gold)==sha(backup)
        put(OUT/'rollback-receipt.json',{'error':str(exc),'restored_main':b['pointer'],'restored_gold_sha256':sha(gold)})
    raise
print('Selected MAIN146, fresh root entry and local Gold connector verified')
