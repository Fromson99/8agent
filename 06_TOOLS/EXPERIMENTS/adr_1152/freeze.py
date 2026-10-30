from common import *
import sys,ast,shutil
T=Path(__file__).parent;S=CAND/'snapshot'
for p in T.glob('*.py'):ast.parse(p.read_text())
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(CAND);assert not ac.validate(CAND),ac.validate(CAND)
c=read(CAND/'candidate.json');v=c['revisions'][-1];code=CAND/'revisions'/v['revision_id']/'snapshot';files={str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in v['files']}
base=read(DES/'baseline.json');serving={n:files[n] for n in base['manifest']['files']};changed=[n for n,h in serving.items() if h!=base['manifest']['files'][n]]
assert len(serving)==440 and len(changed)==32
assert all(n.endswith('ontology_scenarios.py') or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in changed)
binding={'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
stage=ART/'staged-code'
for n,h in serving.items():p=stage/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code/n,p)
(stage/'01_DATA').symlink_to(ROOT/'01_DATA',target_is_directory=True)
put(DES/'staging.json',{'code_root':str(stage.relative_to(ROOT)),'files':serving,'changed':sorted(changed),'data_shipped':False,'test_data_symlink_only':True})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id=CAND.name,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path=str((T/'check.py').relative_to(ROOT)),runner_sha256=sha(T/'check.py'))]);put(ADR/'실험/manifest.json',m)
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':files,'binding':binding,'candidate':binding,'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')},'inputs':{str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json') if p.name!='freeze.json'},'pointer_sha256':base['pointer_sha256'],'manifest_sha256_at_freeze':sha(ADR/'실험/manifest.json')})
print('FROZEN',len(files),'serving440,changed32,newtechnical10+existing216')
