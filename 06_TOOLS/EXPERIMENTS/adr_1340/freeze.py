from common import *
import ast,importlib.util
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
x=read(DES/'candidate-path.json');can=ROOT/x['candidate'];C=can/'snapshot'
# This module contains no SQL and is absent from the native SQL source list.
assert 'legal_agent/read_candidate_pages.py' not in (C/'02_BACKEND/semantic_runtime/oracle_query_plans.py').read_text()
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
    v=read(p)
    for n in v.get('files',{}):v['files'][n]=sha(C/n)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(C/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in [*Path(__file__).parent.glob('*.py'),C/'02_BACKEND/semantic_runtime/legal_agent/read_candidate_pages.py']:ast.parse(p.read_text())
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors})
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in x['files']},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-bounded.json',desc)
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='bounded',experiment_id=m['experiment_id'],arm_id='bounded',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
put(DES/'test-sources.json',{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('test*.py')})
print('Frozen',rev['revision_id'],len(x['files']),'files; preflight',engines,count)
