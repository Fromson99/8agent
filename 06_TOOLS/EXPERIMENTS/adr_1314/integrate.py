from common import *
import shutil,datetime
before=read(DES/'candidate-before.json');after=read(DES/'candidate-after.json');B=ROOT/before['code_root'];C=ROOT/after['code_root'];n='02_BACKEND/semantic_runtime/oracle_query_matcher.py';assert sha(ROOT/n)==sha(B/n),'Concurrent changes in target module; do not overwrite'
assert read(ART/'contracts/result.json')['passed']==230
assert all(read(ART/'actual'/a/'result.json')['failed']==0 for a in ('sqlite','oracle'))
changes={n:(C/n).read_bytes()};changedhash=sha(C/n)
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if isinstance(v.get('files'),dict) and n in v['files']:
  v['files'][n]=changedhash;changes[str(p.relative_to(ROOT))]=(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
p=ROOT/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():
 if row['manifest'] in changes:row['sha256']=hashlib.sha256(changes[row['manifest']]).hexdigest()
changes[str(p.relative_to(ROOT))]=(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
backup=ART/'working-before';backup.mkdir(exist_ok=False);pre={n:sha(ROOT/n) for n in changes};other={n:sha(ROOT/n) for n in before['selected_files'] if n not in changes};mainsha=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
for n in changes:
 p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
assert all(sha(ROOT/n)==h for n,h in pre.items())
for n,body in changes.items():
 p=ROOT/n;tmp=p.with_name('.'+p.name+'.adr1314');tmp.write_bytes(body);os.replace(tmp,p)
assert all(sha(ROOT/n)==h for n,h in other.items()),'Unrelated working file changed concurrently; preserve'
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==mainsha
# Current work may include another authorized Oracle transport; verify, never replace it.
files={}
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
 for n,h in read(p).get('files',{}).items():assert sha(ROOT/n)==h,(str(p),n);files[n]=h
for n in before['selected_files']:files[n]=sha(ROOT/n)
for n in changes:files[n]=sha(ROOT/n)
put(DES/'candidate-working.json',{'code_root':'.','selected_files':files})
put(ART/'working-integration.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'changes':{n:{'before':pre[n],'after':sha(ROOT/n)} for n in changes},'product_module_count':1,'module_sha256':changedhash,'unrelated517files_preserved':True,'other_work_including_oracle_dp_preserved':True,'main_pointer_sha256':mainsha,'all_current_engine_pins_verified':True,'snapshot_used_for_postintegration_verification':str((DES/'candidate-working.json').relative_to(ROOT))})
print('Working integration:',len(changes),'files; one productmodule; unrelatedOracletransportpreserved; MAINunchanged')
