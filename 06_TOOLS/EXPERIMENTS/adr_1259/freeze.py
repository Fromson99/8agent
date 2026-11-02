from common import *
import ast
B=read(D/'baseline.json');candidate=R/'02_BACKEND/lawrag/research/candidates/adr_1259/typed';S=candidate/'snapshot';hashes={}
for directory in ('02_BACKEND/workflow','02_BACKEND/ENGINES'):
 for p in (S/directory).rglob('*.json'):
  v=read(p)
  if not isinstance(v.get('files'),dict):continue
  before=sha(p)
  for n in v['files']:
   target=S/n if directory.endswith('ENGINES') else S/directory/n
   if target.is_file():v['files'][n]=sha(target)
  put(p,v);hashes[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';text=p.read_text()
for old,new in hashes.items():text=text.replace(old,new)
p.write_text(text)
pipeline=read(p)
for entry in pipeline['engines'].values():
 entry['sha256']=sha(S/entry['manifest'])
put(p,pipeline)
for p in (T).glob('*.py'):ast.parse(p.read_text())
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(candidate);assert not ac.validate(candidate),ac.validate(candidate)
v=read(candidate/'candidate.json')['revisions'][-1];C=candidate/'revisions'/v['revision_id']/'snapshot'
pin={'manifest_path':str((candidate/'candidate.json').relative_to(R)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
files={str((R/x['frozen_path']).relative_to(C)):x['snapshot_sha256'] for x in v['files']}
inputs=[D/n for n in ('criteria.json','records.json','originals.json','source-binding.json')]
inputs.extend(R/c['origin']['path'] for c in read(D/'records.json'))
gold=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';binding=read(gold/'binding.json');inputs.extend(gold/n for n in binding['connector_files']);inputs.extend(R/n for n in binding['files'])
inputs.extend(R/n for n in ['02_BACKEND/lawrag/research/__init__.py','02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','06_TOOLS/EXPERIMENTS/adr_1244/test_records.py','06_TOOLS/EXPERIMENTS/adr_1254/safety.py','06_TOOLS/maintenance/agent_record_oracle_r2.py','06_TOOLS/maintenance/publish_gold_ontology_samples.py'])
scripts=[T/n for n in ('common.py','live.py','native.py')]
put(D/'freeze.json',{'code_root':str(C.relative_to(R)),'candidate_revision':pin,'files':files,'inputs':{str(p.relative_to(R)):sha(p) for p in inputs},'scripts':{str(p.relative_to(R)):sha(p) for p in scripts},'working_snapshot':B['working_files'],'not_main_qualified':True})
m=read(A/'실험/manifest.json');m['design']['criteria_frozen_before_run']=True;m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='typed',experiment_id=m['experiment_id'],arm_id='typed',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(R)),runner_sha256=sha(T/'live.py'))]);m['dataset'].update(name='Actual archived public model statements with current Oracle source',version='adr1259-frozen-v1',frozen_source=str((D/'records.json').relative_to(R)),sha256=sha(D/'records.json'),legal_version_checked=True,reference_version_checked=True);m['runs'][0].update(selection_rule='Two exact archived norm text subtrees, original Oracle 369 units fixed before new model calls',artifact_path=str((O/'result.json').relative_to(R)))
put(A/'실험/manifest.json',m);print('FROZEN',len(files),v['revision_id'])
