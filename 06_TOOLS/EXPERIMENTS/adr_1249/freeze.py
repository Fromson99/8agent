from common import *
import ast
T=Path(__file__).parent;b=read(DES/'baseline.json');candidate=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1249/repaired';S=candidate/'snapshot';n='02_BACKEND/semantic_runtime/legal_agent/gateway.py';mapping={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if n not in v.get('files',{}):continue
 old=sha(p);v['files'][n]=sha(S/n);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');mapping[old]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';s=p.read_text()
for old,new in mapping.items():s=s.replace(old,new)
p.write_text(s)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(candidate);assert not ac.validate(candidate),ac.validate(candidate)
c=read(candidate/'candidate.json');v=c['revisions'][-1];C=candidate/'revisions'/v['revision_id']/'snapshot';pin={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
files={str((ROOT/x['frozen_path']).relative_to(C)):x['snapshot_sha256'] for x in v['files']}
for p in T.glob('*.py'):ast.parse(p.read_text())
paths=[ROOT/'service.py',ROOT/'service/__init__.py',ROOT/'service/service.py',ROOT/'02_BACKEND/lawrag/core/request_deadline.py',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',ROOT/'06_TOOLS/maintenance/experiment_json.py']
data=ROOT/b['release']['data_path'];paths+=list(data.rglob('*.sqlite'))+list(data.rglob('*manifest*.json'));paths+=list(DES.glob('*.json'))
put(DES/'freeze.json',{'code_root':str(C.relative_to(ROOT)),'files':files,'candidate_revision':pin,'pointer_sha256':b['pointer_sha256'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in paths},'scripts':{str((T/n).relative_to(ROOT)):sha(T/n) for n in ('live.py','common.py','resource_guard.py','cm_authorization.py')},'oracle_access':False,'main_promoted':False})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='repaired',experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))]);put(ADR/'실험/manifest.json',m)
print('frozen',v['revision_id'],len(files),'files; changed engine manifests',len(mapping))
