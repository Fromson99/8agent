from common import *
f=read(DES/'freeze-rev-001.json');old=read(DES/'source-freeze.json');b=read(DES/'baseline.json');work=read(SOURCE/'working-integration.json');rollback=read(ART/'rollback-compatibility.json')
checks={'all466_identical':f['files']==old['files'] and len(f['files'])==466,
 'all_frozen_files_intact':all(sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items()),
 'inherited_evidence_intact':all(sha(ROOT/n)==v['sha256'] for n,v in read(DES/'inherited-evidence.json').items()),
 'all_working_product_and_pins_intact':all(sha(ROOT/n)==h for k in ('product_files','pins') for n,h in work[k].items()),
 'candidate116_passed':read(SOURCE/'check-qualified.json')['all_passed'] and read(SOURCE/'check-qualified.json')['unique_conditions']==116,
 'working116_passed':read(SOURCE/'check-working.json')['passed']==116 and read(SOURCE/'check-working.json')['failed']==0,
 'same211_regression':read(SOURCE/'regression-comparison.json')['unique_conditions']==211 and not read(SOURCE/'regression-comparison.json')['status_differences'],
 'previous_reader12_passed':rollback['passed'] and rollback['cases']==12,
 'main116_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']}
put(ART/'receipt-checks.json',{'passed':all(checks.values()),'checks':checks,'new_model_calls':0});assert all(checks.values()),checks
print('Nine receipt checks pass; inherited116/116 and211 unchanged; reader12 passes')
