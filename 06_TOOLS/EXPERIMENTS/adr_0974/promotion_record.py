"""Explicit user authorization, exact qualification and reversible local cutover."""
from common import *
A=ROOT/'09_ARTIFACTS/AUDITS/20261021-structured-selection-main';A.mkdir(exist_ok=True)
def bound(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
m=read(ADR/'실험/manifest.json');r=read(ART/'result.json');s=read(ART/'stage.json')
assert m['reservation']['status']=='completed' and r['strict_success'] and all(r['checks'].values())
assert all(sha(ROOT/n)==h for n,h in s['files']['candidate'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['base_pointer']
save(A/'previous-pointer.json',s['base_pointer'])
auth={'quality_gate_override':False,'user_authorization':'실제 LLM으로 다양한 범위·복수·제외 표현도 테스트해보고 문제없으면 메인에 반영하고 GENOS 반입용 ZIP도 만들어줘',
 'scope':'Qualified local MAIN activation and GENOS handoff ZIP; no field deployment or Git commit/push',
 'qualification':{'source':bound(ADR/'실험/manifest.json'),'readme':bound(ADR/'README.md'),'arm':'candidate','result':bound(ART/'result.json'),'rebase':bound(ART/'release-rebase.json')}}
report={'structural_checks_passed':True,'integration':read(ART/'integration.json'),'checks':r['checks'],
 'evidence':[bound(ART/n) for n in ('result.json','analysis.json','contracts-final.json','consumer-candidate.json','consumer-working.json','working-integration.json')],
 'quality_certified':False,'genos_verified':False}
save(A/'authorization.json',auth);save(A/'validation.json',report)
print('Exact qualified promotion authorization prepared; no override')
