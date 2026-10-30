from common import *
import sys
C=ROOT/read(DES/'candidate.json')['root'];S=C/'snapshot';T=Path(__file__).parent
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
known={x['target_path'] for x in read(C/'candidate.json')['files']}
for p in S.rglob('*'):
 if p.is_file() and '__pycache__' not in p.parts and str(p.relative_to(S)) not in known:ac.register_file(C,str(p.relative_to(S)),upstream_state='absent')
new='02_BACKEND/semantic_runtime/legal_agent/scope_completion.py'
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p)
 if 'files' in d:
  for name in d['files']:d['files'][name]=sha(S/name)
  if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in d['files']:d['files'][new]=sha(S/new);d['files']['02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py']=sha(S/'02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py');d['files']['02_BACKEND/semantic_runtime/legal_agent/provider_routing.py']=sha(S/'02_BACKEND/semantic_runtime/legal_agent/provider_routing.py');d['files']['02_BACKEND/semantic_runtime/legal_agent/assessment_consistency.py']=sha(S/'02_BACKEND/semantic_runtime/legal_agent/assessment_consistency.py')
  put(p,d)
p=S/'00_SYSTEM/PIPELINE.json';d=read(p)
for e in d['engines'].values():e['sha256']=sha(S/e['manifest'])
put(p,d)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');v=c['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';files={str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']}
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='scoped',experiment_id=m['experiment_id'],arm_id='scoped',run_ids=['run-001'],runner_path=str((T/'check.py').relative_to(ROOT)),runner_sha256=sha(T/'check.py'))]);put(ADR/'실험/manifest.json',m)
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':files,'candidate_revision':binding,'pointer_sha256':read(DES/'baseline.json')['pointer_sha256'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json') if p.name!='freeze.json'},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')},'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')});print(v['revision_id'],len(files),'files')
