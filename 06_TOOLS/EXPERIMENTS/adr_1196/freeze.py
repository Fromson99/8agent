from common import *
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ROOT/read(DES/'candidate.json')['root'];S=C/'snapshot'
for entry in read(S/'00_SYSTEM/PIPELINE.json')['engines'].values():
 p=S/entry['manifest']
 v=read(p)
 for n in v.get('files',{}):v['files'][n]=sha(S/n)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(S/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');revision=c['revisions'][-1];code=C/'revisions'/revision['revision_id']/'snapshot'
files={str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in revision['files']}
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}
path=DES/('freeze-'+revision['revision_id']+'.json');put(path,{'code_root':str(code.relative_to(ROOT)),'files':files,'candidate_revision':binding})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='preserved',experiment_id=m['experiment_id'],arm_id='preserved',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
print(path, len(files),'files')
