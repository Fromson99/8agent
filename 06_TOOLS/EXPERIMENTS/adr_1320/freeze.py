from pathlib import Path
import json,hashlib,sys,shutil,importlib.util
ROOT=Path('/home/jin/8-AGENT');ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1320-genos-embed-env-main'
DES=ADR/'artifacts/design';can=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1320/integrated';C=can/'snapshot'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
spec=importlib.util.spec_from_file_location('prepare_queries',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
original=builder.source_queries;builder.ROOT=C;builder.source_queries=lambda:original(C)
sys.argv=['prepare_oracle_queries','--report',str(DES/'native-plans.json')];builder.main()
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for n in v.get('files',{}):v['files'][n]=sha(C/n)
 put(p,v)
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(C/row['manifest'])
put(p,v)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in read(DES/'candidate-path.json')['files']},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-integrated.json',desc)
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path='06_TOOLS/EXPERIMENTS/adr_1320/check.py',runner_sha256=sha(Path(__file__).with_name('check.py')))])
put(ADR/'실험/manifest.json',m)
print('Frozen',rev['revision_id'],len(desc['selected_files']))
