from pathlib import Path
import sys,shutil
from common import ROOT,ADR,ART,read,save,sha
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
base=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1053/step-state-r1';t=read(ART/'contracts-api-final-summary.json')
assert t['status']==0 and t['passed']==139 and not t['production_import_leaks'] and not t['candidate_changed_during_tests']
assert t['files']=={str(p.relative_to(base/'snapshot')):sha(p) for p in (base/'snapshot').rglob('*') if p.is_file()}
c.freeze(base);assert not c.validate(base)
frozen=base/'revisions/rev-001/snapshot';rows=read(base/'candidate.json')['files']
second=c.snapshot(ADR,'step-state-a1-r1',[r['target_path'] for r in rows if r['upstream_state']=='present'],experiment_id='ADR-1053-experiment-v1',arm_id='A1',run_ids=['run-001'])
for r in rows:
 n=r['target_path'];dest=second/'snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(frozen/n,dest)
 if r['upstream_state']=='absent':c.register_file(second,n,upstream_state='absent')
c.refresh(second);c.freeze(second);assert not c.validate(second)
assert t['files']=={r['target_path']:r['snapshot_sha256'] for r in read(second/'candidate.json')['files']}
save(ART/'tested-freeze.json',{'candidate':str(base.relative_to(ROOT)),'frozen_root':str(frozen.relative_to(ROOT)),'files':len(rows),'test_summary_sha256':sha(ART/'contracts-api-final-summary.json'),'exact_tested_files':True,'external_model_calls':0,'real_source_database_opened':False})
save(ART/'identical-arm-code.json',{'a1':str(second.relative_to(ROOT)),'a2':str(base.relative_to(ROOT)),'files':len(rows),'same_execution_root':str(frozen.relative_to(ROOT)),'model_calls':0,'production_loadable':False})
print('Frozen',len(rows),'files; identicalA1/A2;139tests')
