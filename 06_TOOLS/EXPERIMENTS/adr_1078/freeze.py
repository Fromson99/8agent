"""Freeze new state contracts and journal-bound native replay, without product changes."""
from common import *
from datetime import datetime, timezone
import subprocess

assert not (DESIGN/'freeze.json').exists()
assert (ROOT/'06_TOOLS/EXPERIMENTS/adr_1078/state_contract.py').is_file()
assert (DESIGN/'secondary-replay.json').is_file()
assert (DESIGN/'compose-preflight.json').is_file()
manifest = read(ADR/'실험/manifest.json')
assert len(manifest['runs']) == 1 and manifest['runs'][0]['status'] == 'planned'
manifest['runs'].append({'id':'run-002','purpose':'audit','parent_run_id':'run-001',
    'arm_ids':['optimized'],'status':'planned',
    'selection_rule':'Known ADR1075 exact38savedresponses,35navigationframes and finalanswer; journal-bound serverIDs. View timing only against prior ADR1076completed35viewsegment; original failure and time limits remain explicit.',
    'artifact_path':str((ADR/'artifacts/run-002/result.json').relative_to(ROOT)),'sha256':'PENDING'})
manifest['design']['secondary_replay'] = bound(DESIGN/'secondary-replay.json')
put(ADR/'실험/manifest.json',manifest,replace=True)
cm = read(CANDIDATE/'candidate.json')
assert not cm['revisions'] and cm['run_ids'] == ['run-001']
cm['run_ids'] = ['run-001','run-002']
cm['updated_at'] = datetime.now(timezone.utc).isoformat()
put(CANDIDATE/'candidate.json',cm,replace=True)
base = read(DESIGN/'baseline.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == base['pointer_sha256']
old_freeze_path = ROOT/'04_EXPERIMENTS/ADR/ADR-1076-navigation-view-preparation-reuse/artifacts/design/freeze.json'
old = read(old_freeze_path)
stage = CANDIDATE/'snapshot'
files = {name:sha(stage/name) for name in base['manifest']['files']}
assert files == old['serving_files']
pin_paths = {'00_SYSTEM/PIPELINE.json'} | {ref['manifest'] for ref in read(stage/'00_SYSTEM/PIPELINE.json')['engines'].values()}
changes = [name for name,old_hash in base['manifest']['files'].items() if files[name] != old_hash]
assert len(changes) == 33 and set(changes) <= set(TARGETS)|pin_paths
assert len(set(changes)&set(TARGETS)) == 2
put(DESIGN/'candidate-preparation.json',{'source_targets':TARGETS,'pin_paths':sorted(pin_paths),
    'changed':changes,'serving_files':files,'all_product_bytes_identical_to_prior_candidate':True,
    'prior_candidate_freeze':bound(old_freeze_path),
    'scope':'No new product edits; same two-module preparation, newly frozen state contract and native identity guard.'})
subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py',
    'freeze',str(CANDIDATE)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
cm = read(CANDIDATE/'candidate.json')
revision = cm['revisions'][-1]
code = CANDIDATE/'revisions'/revision['revision_id']/'snapshot'
assert all(sha(code/name) == value for name,value in files.items())
binding = {'manifest_path':str((CANDIDATE/'candidate.json').relative_to(ROOT)),
    'manifest_sha256':sha(CANDIDATE/'candidate.json'),'revision_id':revision['revision_id'],
    'revision_sha256':revision['revision_sha256']}
reviewed = [{'path':name,'before':base['manifest']['files'][name],'after':files[name],
    'reason':'Same invocation-local preparation or its exact dependency pin as the preserved prior candidate; no new product change.'}
    for name in sorted(changes)]
rebase = {'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],
    'candidate':binding,'staged_files':files,'excluded_candidate_paths':{},'reviewed_changes':reviewed,
    'base_code_root':base['manifest']['code_root'],'stage':str(code.relative_to(ROOT)),
    'reason':'Exact MAIN104 plus preserved two-module invocation-local preparation, qualified by new composed-state boundary contracts and known native replay.'}
put(DESIGN/'release-rebase.json',rebase)
put(DESIGN/'integration.json',{'schema_version':'local-release-integration-v1',
    'base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],
    'changes':reviewed,'candidate':binding,'rebase_receipt':bound(DESIGN/'release-rebase.json')})
manifest = read(ADR/'실험/manifest.json')
manifest['design']['release_rebase'] = bound(DESIGN/'release-rebase.json')
manifest['design']['code_isolation']['candidates'] = [{**binding,'candidate_id':CANDIDATE.name,
    'arm_id':'optimized','experiment_id':manifest['experiment_id'],'run_ids':['run-001','run-002'],
    'runner_path':'06_TOOLS/EXPERIMENTS/adr_1078/audit.py',
    'runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1078/audit.py')}]
put(ADR/'실험/manifest.json',manifest,replace=True)
frozen = {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1078').glob('*.py')}
matrix_source = ROOT/'06_TOOLS/EXPERIMENTS/adr_1078/state-matrix.json'
assert read(matrix_source) == read(DESIGN/'state-matrix.json')
frozen[str(matrix_source.relative_to(ROOT))] = sha(matrix_source)
frozen.update({str(p.relative_to(ROOT)):sha(p) for p in DESIGN.glob('*.json')})
frozen.update({str((code/name).relative_to(ROOT)):value for name,value in files.items()})
frozen.update({str((ROOT/base['manifest']['code_root']/name).relative_to(ROOT)):value
    for name,value in base['manifest']['files'].items()})
frozen[str((CANDIDATE/'candidate.json').relative_to(ROOT))] = sha(CANDIDATE/'candidate.json')
for key in ('failed_source','prior_primary','prior_secondary_failure','prior_product_freeze'):
    item = read(DESIGN/'prior-observed-evidence.json')[key]
    assert sha(ROOT/item['path']) == item['sha256']
    frozen[item['path']] = item['sha256']
put(DESIGN/'freeze.json',{'schema_version':'adr1078-composed-state-freeze-v1',
    'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(ROOT)),
    'files':frozen,'serving_files':files,'candidate':binding})
print('Frozen new state contracts + exact420priorproductbytes;33changes from MAIN104; no execution yet')
