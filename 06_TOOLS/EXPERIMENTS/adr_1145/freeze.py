from common import *
import sys,ast
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
D=Path(__file__).parent
for p in D.glob('*.py'):ast.parse(p.read_text())
ac.freeze(CAND);assert not ac.validate(CAND),ac.validate(CAND)
c=read(CAND/'candidate.json');rev=c['revisions'][-1];code=CAND/'revisions'/rev['revision_id']/'snapshot'
files={str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in rev['files']}
base=read(ART/'baseline.json');changed=[n for n,h in files.items() if base['files'][n]!=h]
assert len(changed)==32,changed
assert all(n=='02_BACKEND/semantic_runtime/legal_agent/ontology_scenarios.py' or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in changed)
binding={'candidate_id':CAND.name,'experiment_id':'ADR-1145-experiment-v1','arm_id':'concise','run_ids':['run-001'],'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((D/'run.py').relative_to(ROOT)),'runner_sha256':sha(D/'run.py')}
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding]);put(ADR/'실험/manifest.json',m)
inputs=[ART/n for n in ['criteria.json','cases.json','rubric.json','schedule.json','baseline.json','build-input.json','package.json','build-result.json','recipe.json','prompt-change.json']]+[ROOT/base['source_view'],ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json']
scripts=list(D.glob('*.py'))+list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1139').glob('test_*.py'))
put(ART/'freeze.json',{'arms':{'baseline':{'code_root':base['code_root'],'files':base['files']},'concise':{'code_root':str(code.relative_to(ROOT)),'files':files}},'binding':binding,'changed':changed,'pointer_sha256':base['pointer_sha256'],'source_view':base['source_view'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in scripts},'manifest_sha256_at_freeze':sha(ADR/'실험/manifest.json'),'new_model_calls':0})
print('FROZEN',len(files),'files;changed',len(changed),'prompt365chars;22cells')
