from pathlib import Path
import json,hashlib,sys
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1057-grouped-query-literal-preservation';ART=ADR/'artifacts'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1057/literal-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(p.relative_to(ROOT))
tested=read(ART/'release-check-v2-summary.json')
assert tested['status']==0 and tested['failed']==0 and not tested['production_import_leaks'] and not tested['candidate_changed_during_tests']
assert tested['files']=={str(p.relative_to(CAND/'snapshot')):sha(p) for p in (CAND/'snapshot').rglob('*') if p.is_file()}
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
# Each freeze appends a new immutable revision; old validation failures remain.
c.freeze(CAND);assert not c.validate(CAND)
v=read(CAND/'candidate.json');rev=v['revisions'][-1]
m=read(ADR/'실험/manifest.json')
m['design']['code_isolation']['candidates']=[{'candidate_id':v['candidate_id'],'arm_id':'grouped-query','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':rel(CAND/'candidate.json'),'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':rel(Path(__file__).parent/'validate_candidate.py'),'runner_sha256':sha(Path(__file__).parent/'validate_candidate.py')}]
save(ADR/'실험/manifest.json',m)
save(ART/'tested-freeze-v2.json',{'candidate':rel(CAND),'revision':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'files':len(tested['files']),'test_summary':rel(ART/'release-check-v2-summary.json'),'sha256':sha(ART/'release-check-v2-summary.json'),'exact_tested_files':True,'external_model_calls':0})
print('FROZEN',len(tested['files']),'files;',tested['passed'],'tests passed')
