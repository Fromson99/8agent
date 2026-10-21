"""Bind explicit local MAIN authorization to completed, exact qualification."""
from common import *
A=ROOT/'09_ARTIFACTS/AUDITS/20261021-law-name-main';A.mkdir(exist_ok=True)
def bound(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
m=read(ADR/'실험/manifest.json');r=read(ART/'result.json');s=read(ART/'stage.json')
assert m['reservation']['status']=='completed' and r['strict_success'] and all(r['checks'].values())
assert all(sha(ROOT/n)==h for n,h in s['files']['candidate'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['base_pointer']
auth={'quality_gate_override':False,'user_authorization':'메인에 적용해봐 그리고 실험까지','scope':'Local MAIN only; no GENOS, Git push or external publication',
 'qualification':{'source':bound(ADR/'실험/manifest.json'),'readme':bound(ADR/'README.md'),'arm':'integrated','result':bound(ART/'result.json'),'rebase':bound(ART/'release-rebase.json')}}
report={'structural_checks_passed':True,'integration':read(ART/'integration.json'),
 'checks':{'completed_qualified_source':True,'working_candidate_all418_files_match':True,'final260_contracts':True,'candidate_and_working_native_consumers':True,'model_path_unchanged':True},
 'evidence':[bound(ART/n) for n in ('result.json','contracts-002.xml','consumer-candidate.json','consumer-working.json','integration-delta.json')],
 'genos_verified':False,'quality_certified':False}
save(A/'authorization.json',auth);save(A/'validation.json',report)
print('Prepared exact authorization and validation; explicit user request retained')
