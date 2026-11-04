from common import *
import ast,importlib.util
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac,adr_structure as ads
x=read(DES/'candidate-path.json');can=ROOT/x['candidate'];C=can/'snapshot'
spec=importlib.util.spec_from_file_location('prepare_queries',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
original=builder.source_queries;builder.ROOT=C;builder.source_queries=lambda:original(C)
sys.argv=['prepare_queries','--report',str(DES/'native-plans.json')];builder.main()
sys.argv=['prepare_queries','--check'];builder.main()
def constants(path):return {t.id:ast.literal_eval(node.value) for node in ast.parse(path.read_text()).body if isinstance(node,ast.Assign) for t in node.targets if isinstance(t,ast.Name)}
old=constants(ROOT/'02_BACKEND/semantic_runtime/oracle_query_plans.py');new=constants(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py')
assert set(old['PLANS'])==set(new['PLANS'])
assert all({k:v for k,v in row.items() if k!='sources'}=={k:v for k,v in new['PLANS'][key].items() if k!='sources'} for key,row in old['PLANS'].items())
put(DES/'native-plan-equivalence.json',{'plans':len(new['PLANS']),'executable_sql_lists_and_plans_exactly_equal':True,'source_line_metadata_changes':sum(old['PLANS'][k]['sources']!=new['PLANS'][k]['sources'] for k in old['PLANS']), 'source_metadata_note':'Source locations and hashes may change; executable SQL/list/AST must remain identical','changed_source_hashes':[n for n,h in new['SOURCES'].items() if old['SOURCES'].get(n)!=h],'source_count':len(new['SOURCES']),'runtime_sqlglot_added':False})
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
put(DES/'candidate-repaired.json',desc)
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='repaired',experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
print('Frozen',rev['revision_id'],len(x['files']),'files; MAIN142 parallel changes preserved; preflight',engines,count)
