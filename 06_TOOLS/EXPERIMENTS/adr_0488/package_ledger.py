"""Add required ledger aggregate metadata; preserve frozen raw measurements.

No product or evaluator is called. Exact cases/stages/gold/metrics remain unchanged.
"""
import hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0488-qwen-source-tiers-v4-paired/artifacts'
def main():
 source=A/'retrieval-stage-ledger.json';target=A/'retrieval-stage-ledger-validated.json';assert not target.exists()
 raw=json.loads(source.read_text());before=json.dumps(raw['runs'],ensure_ascii=False,sort_keys=True)
 for run in raw['runs']:
  for arm in run['arms']:
   assert 'aggregate' not in arm
   arm['aggregate']={'presented_total':sum(c['stages'][-1]['after_count'] for c in arm['cases']),'gold_after':sum(c['stages'][-1]['gold_after'] for c in arm['cases']),'gold_total':sum(c['gold_total'] for c in arm['cases'])}
 raw['audit']['schema_packaging']={'source_path':str(source.relative_to(R)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'operation':'Add required aggregate field; source/case/stage/identity/gold values and numerical evaluation unchanged','raw_runs_sha256':hashlib.sha256(before.encode()).hexdigest()}
 sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));from adr_structure import _canonical_value_sha256
 raw.pop('artifact_sha256');raw['artifact_sha256']=_canonical_value_sha256(raw)
 target.write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n');print(target)
if __name__=='__main__':main()
