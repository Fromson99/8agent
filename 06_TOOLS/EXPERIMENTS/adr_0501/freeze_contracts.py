"""Freeze contract fixtures and candidate import only; no model evaluation authorization."""
import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0501-gemma-question-obligation-wiring';C=R/'02_BACKEND/lawrag/research/candidates/adr_0501/obligations'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
    cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1]
    paths=[C/'candidate.json',A/'artifacts/gemma-policy.json',A/'artifacts/preregistered-contract-design.json']
    paths+=sorted(Path(__file__).parent.glob('*.py'))
    paths+=sorted((R/'05_TESTS/CONTRACTS').glob('*.py'))
    paths+=[R/'06_TOOLS/EXPERIMENTS/adr_0498/test_workflow.py']
    # Pin inherited common runtime too; original source data is never selected implicitly.
    runtime=R/'04_EXPERIMENTS/ADR/ADR-0498-gemma4-fp8-compatible-schema-cm51-fsc10/artifacts/sealed-runtime'
    paths+=sorted(p for p in runtime.rglob('*') if p.is_file())
    design={'schema_version':'offline-contract-design-v1','revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'files':{str(p.relative_to(R)):sha(p) for p in paths},'live_calls':False}
    write(A/'artifacts/frozen-contracts.json',design)
    m=json.loads((A/'실험/manifest.json').read_text())
    m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'obligations','experiment_id':m['experiment_id'],'arm_id':'obligations','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(Path(__file__).with_name('run_contracts.py').relative_to(R)),'runner_sha256':sha(Path(__file__).with_name('run_contracts.py'))}])
    m['dataset'].update(frozen_source=str(Path(__file__).with_name('test_obligations.py').relative_to(R)),sha256=sha(Path(__file__).with_name('test_obligations.py')))
    write(A/'실험/manifest.json',m)
    print(rev['revision_id'],len(paths),'files pinned')
if __name__=='__main__':main()
