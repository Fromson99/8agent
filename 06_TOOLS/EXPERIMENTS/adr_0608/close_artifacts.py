"""Inventory raw evidence and protect actual code/source bindings without regrading."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(n):
    a=next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{n:04d}-*'));m=json.loads((a/'실험/manifest.json').read_text());errors=[];expected_metadata=[]
    frozen=json.loads((a/'artifacts/design/freeze.json').read_text())
    for path,h in frozen.items():
        if sha(ROOT/path)!=h:
            if path==str((a/'실험/manifest.json').relative_to(ROOT)):expected_metadata.append(path)
            else:errors.append({'path':path,'kind':'frozen_code_input_drift'})
    for c in m['design']['code_isolation']['candidates']:
        p=ROOT/c['manifest_path'];x=json.loads(p.read_text())
        if sha(p)!=c['manifest_sha256']:errors.append({'path':c['manifest_path'],'kind':'candidate_manifest_drift'})
        rev=next(v for v in x['revisions'] if v['revision_id']==c['revision_id'])
        if rev['revision_sha256']!=c['revision_sha256']:errors.append({'path':c['manifest_path'],'kind':'revision_drift'})
        for f in rev['files']:
            if sha(ROOT/f['frozen_path'])!=f['snapshot_sha256']:errors.append({'path':f['frozen_path'],'kind':'candidate_file_drift'})
    p=a/'artifacts/preservation-receipt.json';p.write_text(json.dumps({'schema_version':'prototype-preservation-receipt-v1','adr_id':m['adr_id'],'created_at':datetime.now(timezone.utc).isoformat(),'frozen_files_checked':len(frozen),'mismatches':errors,'expected_final_metadata_updates':expected_metadata,'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')=='c860cfdb1a57968df4740c1bf2bf08947dfa15c1edbcb7c14d31f85773af3b32','production_memory_module_absent':not (ROOT/'02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py').exists(),'scoring_unchanged':True},ensure_ascii=False,indent=2)+'\n')
    files=[p for p in a.rglob('*') if p.is_file() and p!=a/'artifacts/manifest.json' and '__pycache__' not in p.parts]
    for c in m['design']['code_isolation']['candidates']:files += [p for p in (ROOT/c['manifest_path']).parent.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += list((ROOT/f'06_TOOLS/EXPERIMENTS/adr_{n:04d}').glob('*.py'))
    (a/'artifacts/manifest.json').write_text(json.dumps({'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen candidate, raw source/model response, functional result, failure receipt or final metadata'} for p in sorted(set(files))]},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'adr':m['adr_id'],'inventory_files':len(set(files)),'binding_errors':errors},ensure_ascii=False))
    if errors:raise SystemExit(1)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('number',type=int);main(p.parse_args().number)
