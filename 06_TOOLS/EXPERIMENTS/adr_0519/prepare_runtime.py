from pathlib import Path
import json,hashlib,datetime
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0519-root-selection-protected-relations';P=R/'04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop';C=R/'02_BACKEND/lawrag/research/candidates/adr_0519/selection'
s=(R/'06_TOOLS/EXPERIMENTS/adr_0518/run_selection.py').read_text().replace('ADR-0518-five-source-replacement-loop','ADR-0519-root-selection-protected-relations').replace('adr_0518','adr_0519').replace('max_calls=2','max_calls=1').replace("run = A/'artifacts/run-002'","run = A/'artifacts/run-001'")
s=s.replace("read(A/'artifacts/reference-witnesses.json')", "read(R/'04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop/artifacts/reference-witnesses.json')")
s=s.replace("        previous=read(R/'04_EXPERIMENTS/ADR/ADR-0517-bounded-provenance-protocol/artifacts/run-001'/cid/'result.json')\n        raw['initial_selected_ids']=previous['final_ids']\n",'')
s=s.replace("            write(result_path,answer)","            original=read(parent)\n            safe=selection.preserve_result(original,selection.originals(original),selection.origin_partition(original),[],error=answer['error'])\n            answer.update(safe)\n            write(result_path,answer)",1)
p=R/'06_TOOLS/EXPERIMENTS/adr_0519/run_selection.py';p.write_text(s)
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1]
item={'candidate_id':'selection','experiment_id':m['experiment_id'],'arm_id':'selection','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(p.relative_to(R)),'runner_sha256':sha(p)}
m['design']['code_isolation']['candidates']=[item];write(A/'실험/manifest.json',m)
parent=read(P/'artifacts/frozen-design.json')
files={p:h for p,h in parent['file_hashes'].items() if 'ADR-0518' not in p and 'adr_0518' not in p and 'ADR-0517' not in p and 'adr_0517' not in p}
extra=[A/'PLAN.md',A/'product-cases.json',A/'artifacts/gemma-policy.json',A/'artifacts/export-rebinding.json',P/'artifacts/reference-witnesses.json',P/'실험/manifest.json',P/'artifacts/summary.json',C/'candidate.json',p]
extra+=list((P/'artifacts/run-002').glob('*/result.json'))
for p in extra:files[str(p.relative_to(R))]=sha(p)
f={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'design':m['design'],'runs':m['runs'],'file_hashes':files,'grader_only_hashes':{str((A/'gold-cases.json').relative_to(R)):sha(A/'gold-cases.json')},'parent_pipeline_binding':parent['parent_pipeline_binding'],'physical_calls_max':61,'worker_count':3,'scope':'Direct root selection only; protection of every acquired linked original; no fresh corpus-wide retrieval or answer generation'}
write(A/'artifacts/frozen-design.json',f)
print('Frozen inputs',len(files),'revision',rev['revision_id'])
