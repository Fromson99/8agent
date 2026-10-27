"""Freeze the user-requested three-case probe before any external call."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from common import ROOT,ADR,ART,read,save,sha,exact_write

CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1059/dense-input-r1'
CODE=CAND/'revisions'/read(CAND/'candidate.json')['revisions'][-1]['revision_id']/'snapshot'
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1057-grouped-query-literal-preservation/artifacts/design-freeze.json'
def rel(p):return str(p.relative_to(ROOT))

def main():
    assert not (ART/'design-freeze.json').exists() and not (ART/'matrix').exists()
    old=read(PRIOR);f=deepcopy(old);plan=read(ART/'live-probe-plan.json')
    replay=read(ART/'saved-input-replay.json')
    assert replay['all_within_budget'] and len(replay['rows'])==4
    files={str(p.relative_to(CODE)):sha(p) for p in CODE.rglob('*') if p.is_file()}
    for name in ('release-check','frozen-api'):
        t=read(ART/(name+'-summary.json'))
        assert t['status']==0 and not t['failed'] and t['files']==files and not t['production_import_leaks'] and not t['candidate_changed_during_tests']
    # Stream-verify one shared source file. No body/index copy or corpus loading.
    source=ROOT/old['data_path']/'store.sqlite';before=source.stat()
    assert sha(source)==old['store_sha256']
    after=source.stat();assert (before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
    receipt=read(ROOT/old['source_integrity_path'])
    assert (receipt['size'],receipt['mtime_ns'],receipt['ctime_ns'])==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
    for path,h in read(ART/'preservation.json')['files'].items():assert sha(ROOT/path)==h
    for key in ('product_cases','evaluator_cases','corpus','authorization','evaluation_contract'):
        assert sha(ROOT/old[key+'_path'])==old[key+'_sha256']
    m=read(ADR/'실험/manifest.json')
    f.update(frozen_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),experiment_id=m['experiment_id'],design=m['design'],manifest_sha256_at_freeze=sha(ADR/'실험/manifest.json'),code_root=rel(CODE),files=files,policy_sha256=sha(CODE/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),validation_inheritance=False,validation_note='Lossless navigation input contracts and exact frozen API checks; previous failures retained.',execution_order=[{'ordinal':i,'case_id':cid,'arm':'A0'} for i,cid in enumerate(plan['cases'],1)])
    for key in ('client','judge_client'):
        f[key+'_path']=rel(CODE/'02_BACKEND/lawrag/research/experiment_client.py');f[key+'_sha256']=sha(ROOT/f[key+'_path'])
    f['optimization_authorization_path']=rel(ART/'live-probe-plan.json');f['optimization_authorization_sha256']=sha(ART/'live-probe-plan.json')
    f['validation_path']=rel(ART/'release-check-summary.json');f['validation_sha256']=sha(ART/'release-check-summary.json')
    f['validation_receipt_path']=rel(ART/'tested-freeze.json');f['validation_receipt_sha256']=sha(ART/'tested-freeze.json')
    f['semantic_contract_files']={p:files[p] for p in old['semantic_contract_files']}
    f['provider_failover']=read(CODE/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['provider_failover']
    f['input_output_representation'].update(query_language='grouped-fulltext-v1',law_choices='presentation-local-law-number-v1')
    f['input_output_representation'].update(navigation_values='navigation-values-v1',
        bound_research_scope='server-retained-exact-ACL-list',large_read_threshold_chars=24000,
        final_request_limit_chars=100000,required_output_schema='unchanged')
    f['saved_input_replay_path']=rel(ART/'saved-input-replay.json');f['saved_input_replay_sha256']=sha(ART/'saved-input-replay.json')
    f['prior_design_freeze_path']=rel(PRIOR);f['prior_design_freeze_sha256']=sha(PRIOR)
    f['runner_hashes']={rel(p):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    f['runner_hashes'][rel(ROOT/'06_TOOLS/EXPERIMENTS/adr_1037/trace.py')]=sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1037/trace.py')
    for key in ('provider_authorization','optimization_authorization'):
        f['runner_hashes'][f[key+'_path']]=f[key+'_sha256']
    f['evaluation_scripts']={rel(Path(__file__).parent/n):sha(Path(__file__).parent/n) for n in ('collect_metrics.py','common.py','wire_audit.py')}
    p=ROOT/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py';f['evaluation_scripts'][rel(p)]=sha(p)
    exact_write(ART/'design-freeze.json',f)
    print('Three cases frozen, A0, sequential; source/index shared read-only; no live calls yet')

if __name__=='__main__':main()
