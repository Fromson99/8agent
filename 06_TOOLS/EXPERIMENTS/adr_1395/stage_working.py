from common import *
import shutil,ast,importlib.util
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
f=read(DES/'candidate-repaired.json');source=ROOT/f['code_root']
before={n:sha(ROOT/n) for n in f['selected_files']}
products=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('investigation_supervisor.py','completion_execution.py','ontology_assessment.py','output_contract.py','bounded_source_session.py','repository.py')]
original=read(DES/'working-before.json')
assert all(before[n]==original[n] for n in products),'Concurrent supervisor edits. Stop before writes.'
test=read(ART/'native-r4/result.json');assert test['exit_code']==0 and test['passed']==6
m=read(ADR/'실험/manifest.json')
can=ac.snapshot(ADR,'working-integration',list(before),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
C=can/'snapshot'
for n in products:shutil.copyfile(source/n,C/n)
spec=importlib.util.spec_from_file_location('prepare_queries',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
original_queries=builder.source_queries;builder.ROOT=C;builder.source_queries=lambda:original_queries(C)
sys.argv=['prepare_queries','--report',str(DES/'integration-native-plans.json')];builder.main()
sys.argv=['prepare_queries','--check'];builder.main()
def plans(path):
 for node in ast.parse(path.read_text()).body:
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PLANS' for t in node.targets):return ast.literal_eval(node.value)
old=plans(ROOT/'02_BACKEND/semantic_runtime/oracle_query_plans.py');new=plans(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py')
assert old.keys()==new.keys() and all({k:v for k,v in n.items() if k!='sources'}=={k:v for k,v in new[i].items() if k!='sources'} for i,n in old.items())
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for n in v.get('files',{}):v['files'][n]=sha(C/n)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(C/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
from genos_codespace_engine_preflight import check
engines,count,errors=check(C);assert not errors,errors
ac.freeze(can);assert not ac.validate(can)
rev=read(can/'candidate.json')['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
pin={'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
after={n:sha(C/n) for n in before}
put(DES/'candidate-working.json',{'code_root':str(C.relative_to(ROOT)),'selected_files':after,'pin':pin})
put(DES/'integration-plan.json',{'before':before,'after':after,'products':products,'changes':{n:h for n,h in after.items() if before[n]!=h},
 'preserved_concurrent':{n:before[n] for n in before if original[n]!=before[n] and n not in products and not n.startswith('02_BACKEND/ENGINES/') and n not in ('00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py')},'native_executables':len(new),'engines':engines,'engine_files':count})
runner=Path(__file__).with_name('check.py')
m['design']['code_isolation']['candidates'].append(dict(pin,candidate_id='working-integration',experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner)))
put(ADR/'실험/manifest.json',m)
print('Integration prepared; changes',len(read(DES/'integration-plan.json')['changes']),'preserved concurrent product files',len(read(DES/'integration-plan.json')['preserved_concurrent']))
