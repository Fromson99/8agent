from pathlib import Path
import hashlib,json,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0927-connected-source-release-binding';Q=R/'04_EXPERIMENTS/ADR/ADR-0926-connected-source-release-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items())
b=read(D/'binding.json');base=read(D/'baseline.json');previous=read(Q/'artifacts/packager-preview.json');staged=dict(base['manifest']['files'])
for row in previous['changes']:
    if row['after'] is None:staged.pop(row['path'],None)
    else:staged[row['path']]=row['after']
assert staged==b['serving_files']
sys.path.insert(0,str(R/'02_BACKEND'))
from semantic_runtime.release_integration import check
receipt=check(R,{'pointer':base['pointer'],'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')},staged,read(D/'integration.json'))
out={'status':'PASS','checks':{'exact_frozen_inputs':True,'actual_packager387_retained':len(staged)==387,'actual_stable_integration_contract':bool(receipt),'candidate_source_files_exact':all(sha(R/b['code_root']/n)==h for n,h in staged.items()),'parent162checks':read(Q/'artifacts/run-001/result.json')['strict_success'],'candidate_consumer':all(read(Q/'artifacts/candidate-consumer.json')['checks'].values()),'working_consumer':all(read(Q/'artifacts/working-consumer.json')['checks'].values()),'pointer_unchanged':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']},'integration_receipt':receipt}
assert all(out['checks'].values());(A/'artifacts/binding-check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print('Actual stable release integration contract PASS')
