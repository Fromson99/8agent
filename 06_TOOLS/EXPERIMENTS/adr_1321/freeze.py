from common import *
import ast,importlib.util
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac,adr_structure as ads
m=read(ADR/'실험/manifest.json');parents=[];data=[];refs=[]
for n,arm in [('ADR-1319-multiturn-command-assessment-repair','repaired'),('ADR-1320-genos-embed-env-main','integrated')]:
 pm,info=ads._load_parent(ROOT/'04_EXPERIMENTS/ADR'/n/'실험/manifest.json',arm,'merged_from');data.append(pm);parents.append(info['record']);refs.append(info['ref'])
m['lineage'].update(parents=parents,root_ref=data[0]['lineage']['root_ref'],root_refs=list(dict.fromkeys(d['lineage']['root_ref'] for d in data)),source_branch_paths={r:d['lineage']['branch_path'] for r,d in zip(refs,data)},branch_path=['followup-review-build'])
m['design']['arms'][0]['derived_from']=refs
m['integration']={'type':'multi_parent_merge','parent_refs':refs,'result_arm':'integrated','rollback_ref':refs[1],
 'parent_contributions':[{'parent_ref':refs[0],'adopted':'Six memory/assessment repair product files','excluded':'Stale Oracle source hash catalogue and all superseded engine pins','reason':'Preserve proven command correction and fail-closed validation'}, {'parent_ref':refs[1],'adopted':'Exact selectedMAIN139 embedding code/environment and native SQL base','excluded':'No unrelated model/field quality claim','reason':'Preserve concurrently completed and selected development work'}],
 'conflicts':[{'id':'native-and-engine-hashes','between':refs,'resolution':'Regenerate source hashes and engine manifests against combined frozen code; all639SQLplans equal MAIN139','chosen_from':refs,'rationale':'Neither parent pin set can identify both contributions without rebuilding'}], 'no_conflict_reason':None}
put(ADR/'실험/manifest.json',m)
x=read(DES/'candidate-path.json');can=ROOT/x['candidate'];C=can/'snapshot'
spec=importlib.util.spec_from_file_location('prepare_queries',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
original=builder.source_queries;builder.ROOT=C;builder.source_queries=lambda:original(C)
sys.argv=['prepare_queries','--report',str(DES/'native-plans.json')];builder.main()
sys.argv=['prepare_queries','--check'];builder.main()
def constants(path):return {t.id:ast.literal_eval(node.value) for node in ast.parse(path.read_text()).body if isinstance(node,ast.Assign) for t in node.targets if isinstance(t,ast.Name)}
old=constants(ROOT/read(DES/'baseline.json')['release']['code_root']/'02_BACKEND/semantic_runtime/oracle_query_plans.py');new=constants(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py')
assert set(old['PLANS'])==set(new['PLANS'])
assert all({k:v for k,v in row.items() if k!='sources'}=={k:v for k,v in new['PLANS'][key].items() if k!='sources'} for key,row in old['PLANS'].items())
put(DES/'native-plan-equivalence.json',{'plans':len(new['PLANS']),'executable_sql_lists_and_plans_exactly_equal':True,'source_line_metadata_changes':sum(old['PLANS'][k]['sources']!=new['PLANS'][k]['sources'] for k in old['PLANS']), 'initial_check_failure':'Full PLANS equality included source line coordinates; eight source-location shifts preserved, executable SQL and AST unchanged','changed_source_hashes':[n for n,h in new['SOURCES'].items() if old['SOURCES'].get(n)!=h],'source_count':len(new['SOURCES']),'runtime_sqlglot_added':False})
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for n in v.get('files',{}):v['files'][n]=sha(C/n)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(C/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in [*Path(__file__).parent.glob('*.py'),*(C/'02_BACKEND/semantic_runtime/legal_agent').glob('*.py')]:ast.parse(p.read_text())
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf);engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors})
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in x['files']},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-integrated.json',desc)
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
print('Frozen',rev['revision_id'],len(x['files']),'files; MAIN139 parallel changes preserved; preflight',engines,count)
