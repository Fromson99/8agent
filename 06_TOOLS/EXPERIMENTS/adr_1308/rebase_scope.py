from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
f=read(DES/'freeze.json');old=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1308/optimized'
archive=ART/'prepared-r1-design';archive.mkdir(exist_ok=False)
for p in DES.glob('*.json'):shutil.copy2(p,archive/p.name)
put(DES/'working-before-final.json',{n:sha(ROOT/n) for n in f['files']})
m=read(ADR/'실험/manifest.json')
c=ac.snapshot(ADR,'scope-fixed',list(f['files']),experiment_id=m['experiment_id'],arm_id='optimized',run_ids=['run-001'])
changes=[]
for n in f['files']:
 if sha(old/'snapshot'/n)!=sha(ROOT/n):
  shutil.copy2(old/'snapshot'/n,c/'snapshot'/n);changes.append(n)
put(DES/'candidate-path.json',{'candidate':str(c.relative_to(ROOT)),'snapshot':str((c/'snapshot').relative_to(ROOT))})
put(DES/'scope-followup.json',{'parent':f['candidate_revision'],'changes':changes,'reason':'Document IDs and source IDs can share the same string. Cache and cursor scopes must preserve the kind, not only sorted values. Found before MAIN activation; r1 prepared release retained, never selected.'})
p=Path(__file__).parent/'freeze.py';s=p.read_text().replace("'freeze-'+v['revision_id']+'.json'", "'freeze-'+C.name+'-'+v['revision_id']+'.json'").replace("candidate_id='optimized'","candidate_id=C.name");p.write_text(s)
p=Path(__file__).parent/'common.py';s=p.read_text().replace("OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-gold-query-optimization'", "OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-gold-query-optimization/final'").replace("RELEASE='gold-query-optimized-20261103-r1'", "RELEASE='gold-query-optimized-20261103-r2'");p.write_text(s)
p=Path(__file__).parent/'check.py';s=p.read_text().replace('gold-query-optimized-20261103-r1/release.json','gold-query-optimized-20261103-r2/release.json');p.write_text(s)
p=Path(__file__).parent/'release_prepare.py';s=p.read_text().replace("before=b['working_files']","before=read(DES/'working-before-final.json')").replace("('contracts-final','regression-qualified')","('scope-final-r2','regression-qualified')").replace("ART/'oracle-select-final/result.json'","ART/'oracle-select-verified/result.json'").replace("ART/'working-before'","ART/'working-before-r2'");p.write_text(s)
print('Rebased scope-kind fix with unchanged working provenance:',len(changes),'files')
