from common import *
import sys
C=ROOT/read(DES/'candidate.json')['root'];S=C/'snapshot';T=Path(__file__).parent
parent=read(DES/'parent.json')
assert all(sha(S/n)==h for n,h in parent['product_files'].items())
assert '25 passed' in (ART/'technical.log').read_text()
for p in T.glob('*.py'):compile(p.read_text(),str(p),'exec')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';files={str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']}
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,production_paths_modified_before_decision=False,runtime_import_allowed=False,production_registry_registered=False,main_wiring_unchanged=True,candidates=[dict(binding,candidate_id='switched',experiment_id=m['experiment_id'],arm_id='switched',run_ids=['run-001'],runner_path=str((T/'probe.py').relative_to(ROOT)),runner_sha256=sha(T/'probe.py'))]);put(ADR/'실험/manifest.json',m)
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':files,'candidate_revision':binding,'pointer_sha256':parent['pointer_sha256'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json') if p.name!='freeze.json'},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')},'technical_log_sha256':sha(ART/'technical.log'),'technical_passed':25,'inherited_product_checks':77})
print(v['revision_id'],len(files),'files;460 identical parent;25 routing tests')
