from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
x=read(DES/'candidate-path.json');old=ROOT/x['candidate']/'snapshot'
before=read(DES/'working-before.json')
drift={n:{'original':h,'current':sha(ROOT/n)} for n,h in before.items() if sha(ROOT/n)!=h}
product=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in
 ('investigation_supervisor.py','completion_execution.py','ontology_assessment.py','output_contract.py','bounded_source_session.py','repository.py')]
assert not any(n in drift for n in product)
assert all(n.startswith('02_BACKEND/ENGINES/') or n in ('00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py','02_BACKEND/semantic_runtime/legal_agent/case_repository.py','02_BACKEND/semantic_runtime/legal_agent/shortcut_cases.py') for n in drift),drift
put(DES/'concurrent-1396.json',{'detected':drift,'first_write_to_checkout':False,'candidate_source':x['candidate'],'new_scope':'Keep candidate producer/consumer from completed1393 and six new products. Preserve current1396 unrelated checkout bytes at later scoped integration.'})
m=read(ADR/'실험/manifest.json')
new=ac.snapshot(ADR,'repaired-r2',x['files'],experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n in x['files']:shutil.copyfile(old/n,new/'snapshot'/n)
put(DES/'candidate-path.json',{**x,'candidate':str(new.relative_to(ROOT))})
put(DES/'working-integration-base.json',{n:sha(ROOT/n) for n in x['files']})
