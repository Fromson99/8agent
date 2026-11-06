from common import *
import importlib.util,shutil,ast
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
old=read(DES/'candidate-matrix.json');can=(ROOT/old['pin']['manifest_path']).parent;C=can/'snapshot'
put(DES/'initial-preflight-failure.json',{'model_calls':0,'error':'ORACLE QUERY CATALOGUE STALE provider_routing.py; original rev001 preserved','initial_candidate':old})
spec=importlib.util.spec_from_file_location('prepare_queries',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
original=builder.source_queries;builder.ROOT=C;builder.source_queries=lambda:original(C)
sys.argv=['prepare_queries','--report',str(DES/'native-plans.json')];builder.main();sys.argv=['prepare_queries','--check'];builder.main()
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for n in v.get('files',{}):v['files'][n]=sha(C/n)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(C/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in old['selected_files']},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-matrix.json',desc)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf);engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1346-charter-review-retention-live/artifacts/transport',ART/'transport')
m=read(ADR/'실험/manifest.json');runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='matrix',experiment_id=m['experiment_id'],arm_id='matrix',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))]);put(ADR/'실험/manifest.json',m)
print('Prepared',rev['revision_id'],'engine',engines,count)
