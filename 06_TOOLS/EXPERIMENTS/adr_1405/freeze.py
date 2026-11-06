from common import *
import ast,importlib.util
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
x=read(DES/'mutable-candidate.json');can=ROOT/x['path'];C=can/'snapshot';b=read(DES/'baseline.json')
spec=importlib.util.spec_from_file_location('prepare_queries',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
original=builder.source_queries;builder.ROOT=C;builder.source_queries=lambda:original(C)
sys.argv=['prepare_queries','--report',str(DES/'native-plans.json')];builder.main()
sys.argv=['prepare_queries','--check'];builder.main()
def constants(p):return {t.id:ast.literal_eval(n.value) for n in ast.parse(p.read_text()).body if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name)}
old=constants(ROOT/b['release']['code_root']/'02_BACKEND/semantic_runtime/oracle_query_plans.py')
new=constants(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py')
assert old['PLANS'].keys()==new['PLANS'].keys()
assert all({k:v for k,v in n.items() if k!='sources'}=={k:v for k,v in new['PLANS'][i].items() if k!='sources'} for i,n in old['PLANS'].items())
put(DES/'native-equivalence.json',{'plans':len(new['PLANS']),'old_executables_identical':True})
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for n in v.get('files',{}):v['files'][n]=sha(C/n)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(C/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
from genos_codespace_engine_preflight import check
engines,count,errors=check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors})
for p in [*Path(__file__).parent.glob('*.py'),*(C/'02_BACKEND/semantic_runtime/legal_agent').glob('*.py')]:ast.parse(p.read_text())
ac.freeze(can);assert not ac.validate(can)
rev=read(can/'candidate.json')['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
pin={'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'candidate-repaired.json',{'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in x['files']},'pin':pin})
m=read(ADR/'실험/manifest.json');runner=Path(__file__).with_name('check.py')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id=can.name,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
print('Frozen',len(x['files']),'files; native executable count',len(new['PLANS']))
