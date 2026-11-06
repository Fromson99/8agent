from common import *
import shutil
b=read(DES/'baseline.json');ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert ptr['generation']==144 and all(ptr[k]==b['pointer'][k] for k in ('release_id','manifest_path','release_manifest_sha256'))
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items())
other=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1378-*/artifacts'))
f=read(other/'design/candidate-repaired.json');integ=read(other/'working-integration.json')
name='00_SYSTEM/PIPELINE.json';path=ROOT/name
assert integ['whole528_matches_candidate'] and [n for n,h in f['selected_files'].items() if sha(ROOT/n)!=h]==[name]
old=ROOT/'08_DEPLOYMENT/RELEASES/ontology-accumulation-20261105-r1/rollback/PIPELINE.json'
assert sha(path)==sha(old) and sha(ROOT/f['code_root']/name)==integ['changes'][name]
tmp=path.with_name('.PIPELINE.1377-recover');shutil.copyfile(ROOT/f['code_root']/name,tmp)
assert sha(path)==sha(old);os.replace(tmp,path)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
put(DES/'post-rollback.json',{**b,'pointer':ptr,'working_files':f['selected_files']})
put(ART/'main/rollback-receipt.json',{'restored_release':ptr,'restored_Gold_binding':True,'concurrent_working_revision':f['pin'],'working_recovery':{name:integ['changes'][name]},'verified_working_files':528,'reason':'Restricted HEALTH test hung. Official rollback advances generation and restores prior pipeline bytes; restored concurrent working pin from its own verified snapshot.'})
