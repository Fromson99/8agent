"""Freeze unchanged product,237unexecuted contracts and1345observed support."""
from common import *
from datetime import datetime, timezone
import subprocess

assert not (DESIGN/'freeze.json').exists()
for name in ('secondary-replay.json','compose-preflight.json','alias-preflight.json','fixture-preflight.json'):
    assert (DESIGN/name).is_file()
manifest = read(ADR/'실험/manifest.json')
assert manifest['lineage']['parents'][0]['experiment_id'] == 'ADR-1075-experiment-v1'
assert len(manifest['runs']) == 1 and manifest['runs'][0]['status'] == 'planned'
manifest['runs'].append({'id':'run-002','purpose':'audit','parent_run_id':'run-001',
    'arm_ids':['optimized'],'status':'planned',
    'selection_rule':'Known ADR1075 exact38savedresponses,35navigationframes and finalanswer; journal-bound generatedIDs and proven role-only aliases. View timing only against prior1076completed35viewsegment, whose later failure remains preserved.',
    'artifact_path':str((ADR/'artifacts/run-002/result.json').relative_to(ROOT)),'sha256':'PENDING'})
manifest['design']['secondary_replay'] = bound(DESIGN/'secondary-replay.json')
put(ADR/'실험/manifest.json',manifest,replace=True)
cm = read(CANDIDATE/'candidate.json')
assert not cm['revisions'] and cm['run_ids'] == ['run-001']
cm['run_ids'] = ['run-001','run-002']
cm['updated_at'] = datetime.now(timezone.utc).isoformat()
put(CANDIDATE/'candidate.json',cm,replace=True)
base = read(DESIGN/'baseline.json')
observed = read(DESIGN/'observed-comparator.json')
prep = read(DESIGN/'candidate-preparation.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == base['pointer_sha256']
stage = CANDIDATE/'snapshot'
files = {name:sha(stage/name) for name in base['manifest']['files']}
assert files == prep['serving_files']
prior = read(DESIGN/'prior-observed-evidence.json')
assert files == read(ROOT/prior['prior_product_freeze']['path'])['serving_files']
assert read(DESIGN/'fixture-preflight.json')['status'] == 'PASS' and all(value is True for value in read(DESIGN/'fixture-preflight.json')['checks'].values())
changes = {name for name,value in base['manifest']['files'].items() if files[name] != value}
assert changes == set(TARGETS)|set(prep['pin_paths']) and len(changes) == 34
observed_changes = {name for name,value in observed['serving_files'].items() if files[name] != value}
assert observed_changes == {SQL_TARGET}|set(prep['pin_paths']) and len(observed_changes) == 32
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
    'reason':'One-view preparation or one reference membership predicate; otherwise an exact dependency pin. All menus and validation consumers retained.'}
    for name in sorted(changes)]
rebase = {'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],
    'candidate':binding,'staged_files':files,'excluded_candidate_paths':{},'reviewed_changes':reviewed,
    'base_code_root':base['manifest']['code_root'],'stage':str(code.relative_to(ROOT)),
    'reason':'Exact MAIN104 plus three narrow source changes. Prior cache contracts disclosed as observed, 237unexecuted SQL conditions,1345observed SQL support and complete known replay required; no legal quality claim.'}
put(DESIGN/'release-rebase.json',rebase)
put(DESIGN/'integration.json',{'schema_version':'local-release-integration-v1',
    'base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],
    'changes':reviewed,'candidate':binding,'rebase_receipt':bound(DESIGN/'release-rebase.json')})
manifest = read(ADR/'실험/manifest.json')
manifest['design']['release_rebase'] = bound(DESIGN/'release-rebase.json')
manifest['design']['code_isolation']['candidates'] = [{**binding,'candidate_id':CANDIDATE.name,
    'arm_id':'optimized','experiment_id':manifest['experiment_id'],'run_ids':['run-001','run-002'],
    'runner_path':'06_TOOLS/EXPERIMENTS/adr_1081/audit.py',
    'runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1081/audit.py')}]
put(ADR/'실험/manifest.json',manifest,replace=True)
frozen = {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1081').glob('*.py')}
matrix_source = ROOT/'06_TOOLS/EXPERIMENTS/adr_1081/sql-matrix.json'
assert read(matrix_source) == read(DESIGN/'sql-matrix.json')
frozen[str(matrix_source.relative_to(ROOT))] = sha(matrix_source)
frozen.update({str(p.relative_to(ROOT)):sha(p) for p in DESIGN.glob('*.json')})
fixture_raw = ROOT/read(DESIGN/'fixture-preflight.json')['raw_path']
frozen[str(fixture_raw.relative_to(ROOT))] = sha(fixture_raw)
frozen.update({str((code/name).relative_to(ROOT)):value for name,value in files.items()})
for source in (base['manifest'],observed):
    for name,value in source.get('files',source.get('serving_files')).items():
        frozen[str((ROOT/source['code_root']/name).relative_to(ROOT))] = value
frozen[str((CANDIDATE/'candidate.json').relative_to(ROOT))] = sha(CANDIDATE/'candidate.json')
for key in ('source','readme','freeze','primary_result','secondary_result'):
    item = observed[key]
    assert sha(ROOT/item['path']) == item['sha256']
    frozen[item['path']] = item['sha256']
frozen.update(read(ROOT/prior['prior_product_freeze']['path'])['files'])
for key in ('failed_source','prior_primary','prior_raw','prior_product_freeze'):
    item = prior[key]
    assert sha(ROOT/item['path']) == item['sha256']
    frozen[item['path']] = item['sha256']
put(DESIGN/'freeze.json',{'schema_version':'adr1081-valid-fixture-freeze-v1',
    'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(ROOT)),
    'files':frozen,'serving_files':files,'candidate':binding})
print('Frozen237new/1345observedSQLpairs;420productbytes unchanged;34cumulativeMAIN104changes; observedcache and nativeevidence explicit; execution0')
