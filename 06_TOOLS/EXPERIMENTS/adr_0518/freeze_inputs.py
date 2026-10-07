from pathlib import Path
import json,hashlib,datetime
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop';P=R/'04_EXPERIMENTS/ADR/ADR-0517-bounded-provenance-protocol';C=R/'02_BACKEND/lawrag/research/candidates/adr_0518/selection'
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');c=read(C/'candidate.json');rev=c['revisions'][-1]
print('revision',rev.keys())
item={'candidate_id':'selection','experiment_id':m['experiment_id'],'arm_id':'selection','run_ids':['run-002'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0518/run_selection.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0518/run_selection.py')}
m['design']['code_isolation']['candidates']=[item]
write(A/'실험/manifest.json',m)
old=read(P/'artifacts/frozen-design.json')
files={p:h for p,h in old['file_hashes'].items() if 'ADR-0517-bounded-provenance-protocol' not in p and 'adr_0517' not in p}
extra=[A/'PLAN.md',A/'product-cases.json',A/'artifacts/gemma-policy.json',A/'artifacts/export-rebinding.json',A/'artifacts/reference-witnesses.json',P/'실험/manifest.json',P/'artifacts/summary.json',C/'candidate.json',R/item['runner_path']]
extra+=list((P/'artifacts/run-001').glob('*/result.json'))
for p in extra:files[str(p.relative_to(R))]=sha(p)
f={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'design':m['design'],'runs':m['runs'],'file_hashes':files,'grader_only_hashes':{str((A/'gold-cases.json').relative_to(R)):sha(A/'gold-cases.json')},'parent_pipeline_binding':old['parent_pipeline_binding'],'physical_calls_max':122,'worker_count':3,'scope':'No count target; review existing final choices; public original sources+literal relation appendix; no final answer calls'}
write(A/'artifacts/frozen-design.json',f)
print('Frozen',len(files),'files')
