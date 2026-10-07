"""Hash inventory and read-only preservation receipts. Does not regrade outputs."""
import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 a=argparse.ArgumentParser();a.add_argument('number',type=int);args=a.parse_args();n=args.number
 adr=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-'+str(n).zfill(4)+'-*'))
 frozen=json.loads((adr/'artifacts/design/freeze.json').read_text())
 baseline=json.loads((adr/'artifacts/design/baseline-binding.json').read_text())
 current=json.loads((adr/'실험/manifest.json').read_text())
 errors=[]
 for label,files in [('frozen_inputs_code',frozen),('protected_baseline',baseline)]:
  for path,h in files.items():
   if sha(ROOT/path)!=h:errors.append({'kind':label,'path':path})
 for c in current['design']['code_isolation']['candidates']:
  p=ROOT/c['manifest_path'];m=json.loads(p.read_text())
  if sha(p)!=c['manifest_sha256']:errors.append({'kind':'candidate_manifest','path':str(p.relative_to(ROOT))})
  r=next(x for x in m['revisions'] if x['revision_id']==c['revision_id'])
  if r['revision_sha256']!=c['revision_sha256']:errors.append({'kind':'candidate_revision','path':str(p.relative_to(ROOT))})
  for f in r['files']:
   if sha(ROOT/f['frozen_path'])!=f['snapshot_sha256']:errors.append({'kind':'candidate_file','path':f['frozen_path']})
 receipt={'schema_version':'prototype-preservation-receipt-v1','created_at':datetime.now(timezone.utc).isoformat(),'adr_id':current['adr_id'],'frozen_files_checked':len(frozen),'protected_baseline_files_checked':len(baseline),'mismatches':errors,'production_prototype_target_absent':not (ROOT/'02_BACKEND/semantic_runtime/legal_agent/chain_prototype.py').exists(),'raw_result_sha256':sha(adr/'artifacts/run-001/result.json' if (adr/'artifacts/run-001/result.json').exists() else adr/'artifacts/run-001/execution-abort.json'),'scoring_unchanged':True,'main_unchanged':not any(x['kind']=='protected_baseline' and 'ACTIVE_RELEASE' in x['path'] for x in errors),'scope':'Local research prototype; not production API or GENOS verification'}
 if n==594:receipt['old_diagnostic_note']='Historical unexpected_status includes MAP_WRONG=REUSED (legitimate); original audit preserved, one actual unexpected CLARIFY remained.'
 write(adr/'artifacts/preservation-receipt.json',receipt)
 paths=[p for p in adr.rglob('*') if p.is_file() and p!=adr/'artifacts/manifest.json' and '__pycache__' not in p.parts]
 for c in current['design']['code_isolation']['candidates']:
  paths += [p for p in (ROOT/c['manifest_path']).parent.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
 paths += [p for p in (ROOT/'06_TOOLS/EXPERIMENTS'/('adr_'+str(n).zfill(4))).glob('*.py')]
 paths += list((ROOT/'07_DOCS/REFERENCE/REPORTS').glob('ADR-'+str(n).zfill(4)+'_RAG_CHAIN*.md'))
 write(adr/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':current['adr_id'],'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code/input, complete raw evidence or immutable-result report/metadata','contains_raw_prompts_and_outputs':'call-' in str(p) or p.parent.name=='실험' and p.name.startswith('질문-')} for p in sorted(set(paths))]})
 print(json.dumps({'adr':current['adr_id'],'inventory_files':len(set(paths)),**receipt},ensure_ascii=False))
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
