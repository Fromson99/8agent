from common import *
import ast,shutil
T=Path(__file__).parent;candidate=(ROOT/read(DES/'candidate-path.json')['snapshot']).parent
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(candidate);assert not ac.validate(candidate),ac.validate(candidate)
v=read(candidate/'candidate.json')['revisions'][-1];C=candidate/'revisions'/v['revision_id']/'snapshot'
pin={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
files={str((ROOT[x['frozen_path']] if False else ROOT/x['frozen_path']).relative_to(C)):x['snapshot_sha256'] for x in v['files']}
transport=ART/'transport';transport.mkdir(exist_ok=False)
modules={'lawrag':'02_BACKEND/lawrag/__init__.py','lawrag.core':'02_BACKEND/lawrag/core/__init__.py','lawrag.research':'02_BACKEND/lawrag/research/__init__.py','lawrag.core.request_deadline':'02_BACKEND/lawrag/core/request_deadline.py','lawrag.research.experiment_client':'02_BACKEND/lawrag/research/experiment_client.py','lawrag.research.openrouter_legal_adapter':'02_BACKEND/lawrag/research/openrouter_legal_adapter.py'}
for relative in modules.values():
 source=C/relative
 if not source.exists():source=ROOT/relative
 dest=transport/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
put(transport/'transport-pins.json',{'modules':modules,'files':{n:sha(transport/n) for n in modules.values()}})
for p in T.glob('*.py'):ast.parse(p.read_text())
b=read(DES/'baseline.json');data=ROOT/b['release']['data_path']
paths=[ROOT/'service.py',ROOT/'service/__init__.py',ROOT/'service/service.py',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',ROOT/'06_TOOLS/maintenance/experiment_json.py']
paths+=list(data.rglob('*.sqlite'))+list(data.rglob('*manifest*.json'))+list(DES.glob('*.json'))+list(transport.rglob('*.py'))+[transport/'transport-pins.json']
put(DES/'freeze.json',{'code_root':str(C.relative_to(ROOT)),'files':files,'candidate_revision':pin,'pointer_sha256':b['pointer_sha256'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in paths},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')},'oracle_access':False,'main_promoted':False})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='repaired',experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))]);put(ADR/'실험/manifest.json',m)
print('frozen',v['revision_id'],len(files))
