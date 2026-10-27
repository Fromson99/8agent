"""Post-completion exact qualification records; no MAIN prepare or activation."""
from common import *
import shutil
import sys

freeze = read(DESIGN/'freeze.json')
base = read(DESIGN/'baseline.json')
code = ROOT/freeze['code_root']
primary = read(ADR/'artifacts/run-001/result.json')
secondary = read(ADR/'artifacts/run-002/result.json')
working = ROOT/'09_ARTIFACTS/AUDITS/20261027-navigation-view-working-integration'
working_result = read(working/'validation.json')
for result in (primary, secondary, working_result):
    assert result['strict_success'] and all(v is True for v in result['checks'].values())
assert (ADR/'artifacts/final-validation.txt').read_text().startswith('OK:')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == base['pointer_sha256']
assert all(sha(ROOT/p) == h for p,h in freeze['files'].items())
working_receipt = read(working/'integration.json')
assert all(sha(ROOT/p) == h for p,h in working_receipt['working_source_hashes'].items())
assert all(sha(code/p) == h for p,h in working_receipt['candidate_source_hashes'].items())
assert working_receipt['candidate'] == freeze['candidate']
backup = ADR/'artifacts/working-pipeline-before-promotion.json'
assert not backup.exists()
shutil.copyfile(ROOT/'00_SYSTEM/PIPELINE.json', backup)
qualification = {'source':bound(ADR/'실험/manifest.json'), 'readme':bound(ADR/'README.md'),
    'arm':'optimized', 'result':bound(ADR/'artifacts/run-001/result.json'),
    'rebase':bound(DESIGN/'release-rebase.json')}
authorization = {'authorized_by':'user',
    'authorization_text':'오케이 이걸 메인에 반영하고 이부분 전체를 잘 반영해 빠짐없이 그리고 실험도 해봐 반영하고 이후에 온톨로지 실험을 다시해 그리고 메인은 삼성에일로 쫘줘',
    'scope':'Exact MAIN104 derivative: two-module invocation-local acquired-original preparation and31requiredpins only. Primary qualification is the prospective finite mechanical census; known-response native replay is secondary in-sample performance evidence. No inherited waiver or legal-quality claim.',
    'quality_gate_override':False, 'qualification':qualification,
    'rollback_pipeline':bound(backup)}
validation = {'structural_checks_passed':True, 'integration':read(DESIGN/'integration.json'),
    'source_final_validation':bound(ADR/'artifacts/final-validation.txt'),
    'primary_finite_census':bound(ADR/'artifacts/run-001/result.json'),
    'raw_finite_pairs':bound(ADR/'artifacts/run-001/finite-pairs.jsonl.gz'),
    'secondary_known_trace':bound(ADR/'artifacts/run-002/result.json'),
    'working_hunk_integration':bound(working/'integration.json'),
    'working_regressions':bound(working/'validation.json'),
    'exact_candidate_source_hashes':working_receipt['candidate_source_hashes'],
    'different_working_source_hashes':working_receipt['working_source_hashes'],
    'limitations':primary['limitations']+[secondary['scope'],
        'Working source retains separate selected-directory/annex changes and is not byte-identical to candidate.',
        'Native replay injects arm frozen code/data into original logical MAIN104 binding; actual MAIN105 activation/consumer requires a separate check.']}
sys.dont_write_bytecode = True
sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.release_qualification import verify
from semantic_runtime.release_integration import check
assert verify(ROOT,authorization,validation) == qualification
integration = check(ROOT,{'pointer':base['pointer'],'pointer_sha256':base['pointer_sha256']},
    freeze['serving_files'],validation['integration'])
put(ADR/'artifacts/main-authorization.json',authorization)
put(ADR/'artifacts/main-validation.json',validation)
put(ADR/'artifacts/promotion-records.json',{'status':'READY_FOR_STANDARD_PREPARE',
    'qualification':qualification, 'integration':integration,
    'release_id':'navigation-validation-20261027-r1', 'source_code_root':freeze['code_root'],
    'data_generation':base['manifest']['data_path'],
    'authorization':bound(ADR/'artifacts/main-authorization.json'),
    'validation':bound(ADR/'artifacts/main-validation.json'),
    'source_manifest_immutable':True, 'main_activated':False, 'new_model_calls':0})
print('Qualified finite-census source and exact MAIN104 rebase verified; standard prepare ready; MAIN unchanged')
