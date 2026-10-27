"""Freeze one user-authorized restart, asserting unchanged product and conditions."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
from common import ROOT, ADR, ART, read, save, sha, exact_write
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1047-ontology-mvp-state-format/artifacts/design-freeze.json'
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1048/state-format-r10/revisions/rev-001/snapshot'
def rel(p): return str(p.relative_to(ROOT))
def main():
    assert not (ART/'design-freeze.json').exists()
    assert not (ART/'matrix').exists() and not (ART/'evaluation').exists()
    old=read(PRIOR); new=deepcopy(old)
    for p,h in old['runner_hashes'].items(): assert sha(ROOT/p)==h,p
    for key in ['validation','validation_receipt','optimization_authorization','data_manifest']:
        p=ROOT/(old['data_path']+'/manifest.json' if key=='data_manifest' else old[key+'_path'])
        assert sha(p)==old[key+'_sha256'],key
    validation=read(ROOT/old['validation_path'])
    assert validation['status']==0 and validation['passed']==619
    assert not validation['candidate_changed_during_tests'] and not validation['production_import_leaks']
    assert validation['files']==old['files']
    assert all(sha(CODE/n)==h for n,h in old['files'].items())
    identity=read(ART/'runner-identity.json')
    assert identity['all_reverse_normalized_byte_identical'] and identity['only_namespace_changes']
    for row in identity['files']:
        assert sha(ROOT/row['path'])==row['sha256']
        assert sha(ROOT/row['source_path'])==row['source_sha256']
    assert '20 passed' in (ART/'runner-contracts.log').read_text()
    auth=read(ART/'restart-authorization.json')
    assert auth['approved_for_run'] and auth['new_planned_cells']==111 and auth['transport_retries']==0
    assert auth['add_missing_laws'] is False and auth['max_output_tokens'] is None
    for row in auth['inherited_input_identity']:
        assert sha(ROOT/row['path'])==sha(ROOT/row['source_path'])==row['sha256']
    for row in auth['prior_stop_records']: assert sha(ROOT/row['path'])==row['sha256']
    sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
    import adr_candidate
    candidates=[]
    for arm,name in [('A1','state-format-a1-r10'),('A2','state-format-r10')]:
        directory=CODE.parents[3]/name
        assert not adr_candidate.validate(directory)
        candidate=read(directory/'candidate.json'); revision=candidate['revisions'][-1]
        assert {r['target_path']:r['snapshot_sha256'] for r in candidate['files']}==old['files']
        candidates.append({'candidate_id':name,'arm_id':arm,'experiment_id':'ADR-1048-experiment-v1','run_ids':['run-001'],'manifest_path':rel(directory/'candidate.json'),'manifest_sha256':sha(directory/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],'runner_path':rel(Path(__file__).with_name('run_matrix.py')),'runner_sha256':sha(Path(__file__).with_name('run_matrix.py'))})
    source=ROOT/old['data_path']/'store.sqlite'; before=source.stat(); measured=sha(source); after=source.stat()
    fields=lambda s:(s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    assert fields(before)==fields(after) and measured==old['store_sha256']
    integrity=read(ROOT/old['source_integrity_path'])
    assert (integrity['size'],integrity['mtime_ns'],integrity['ctime_ns'])==fields(after)
    assert sha(ROOT/old['main_pointer_path'])==old['main_pointer_sha256']
    policy=read(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    assert policy['http_retries']==0 and policy['max_output_tokens'] is None and not policy['fallback_allowed']
    assert sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')==old['policy_sha256']
    manifest_path=ADR/'실험/manifest.json'; manifest=read(manifest_path)
    manifest['design']=deepcopy(old['design'])
    manifest['design']['code_isolation']['candidates']=candidates
    manifest['design']['live_execution_gate']='User approved one fresh identical r10 111-cell attempt after preserved ADR1047 shared-provider 429; no automatic transport retry or changed conditions.'
    manifest['design']['criteria_frozen_before_run']=True
    manifest['dataset']['frozen_source']=rel(ART/'dataset-freeze-r1.json')
    manifest['dataset']['sha256']=sha(ART/'dataset-freeze-r1.json')
    manifest['reservation']['events'].append({'action':'execution_design_frozen','at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'owner':'Codex','session_id':manifest['reservation']['session_id'],'note':'Same 684 product files and all experimental conditions as ADR1047. One user-authorized fresh attempt; stop on another operational failure.'})
    old_updated=manifest['reservation']['updated_at']; manifest['reservation']['updated_at']=manifest['reservation']['events'][-1]['at']
    readme=ADR/'README.md'; readme.write_text(readme.read_text().replace('updated_at: '+old_updated,'updated_at: '+manifest['reservation']['updated_at']))
    save(manifest_path,manifest)
    new.update(frozen_at=datetime.now(timezone.utc).isoformat(),experiment_id=manifest['experiment_id'],design=manifest['design'],manifest_sha256_at_freeze=sha(manifest_path),code_root=rel(CODE),client_path=rel(CODE/'02_BACKEND/lawrag/research/experiment_client.py'),validation_inheritance=True,validation_note='619 product/API checks inherited on byte-identical 684 files; 20 runner tests rerun after namespace-only changes. No claim of new product tests.')
    for key in ['product_cases','evaluator_cases','corpus','authorization','evaluation_contract','dataset_preparation','snapshot','corpus_article_root_count']:
        new[key+'_path']=rel(ART/Path(old[key+'_path']).name)
        hk=key+'_file_sha256' if key=='snapshot' else key+'_sha256'
        assert sha(ROOT/new[key+'_path'])==old[hk]
    for row in identity['files']:
        new['runner_hashes'][row['path']]=row['sha256']
    for p in [Path(__file__),Path(__file__).with_name('prepare_restart.py')]: new['runner_hashes'][rel(p)]=sha(p)
    new['evaluation_scripts']={p.replace('/adr_1047/','/adr_1048/'):sha(ROOT/p.replace('/adr_1047/','/adr_1048/')) for p in old['evaluation_scripts']}
    new['prior_design_freeze_path']=rel(PRIOR); new['prior_design_freeze_sha256']=sha(PRIOR)
    new['restart_authorization_path']=rel(ART/'restart-authorization.json'); new['restart_authorization_sha256']=sha(ART/'restart-authorization.json')
    proofpaths=[ART/n for n in ['restart-authorization.json','runner-identity.json','candidate-code-identity.json','runner-contracts.log']]+[PRIOR]
    new['restart_integrity_receipts']={rel(p):sha(p) for p in proofpaths}
    new['runner_hashes'].update(new['restart_integrity_receipts'])
    for key in ['files','execution_order','equal_operational_overrides','reporting_rules','snapshot_digest','snapshot_file_sha256','policy_sha256','client_sha256','judge_client_sha256','data_manifest_sha256','store_sha256','product_cases_sha256','evaluator_cases_sha256','corpus_sha256','authorization_sha256','evaluation_contract_sha256','response_reception','input_output_representation','semantic_contract_files','unchanged_core_semantic_definitions']:
        assert new[key]==old[key],key
    exact_write(ART/'design-freeze.json',new)
    print('Frozen byte-identical r10; 111 fresh sequential cells; no automatic transport retries; model calls 0.')
if __name__=='__main__': main()
