from common import *
A=ROOT/'09_ARTIFACTS/AUDITS/20261022-unified-scope-main';A.mkdir(exist_ok=True)
def bound(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
m=read(ADR/'실험/manifest.json');r=read(ART/'result.json');s=read(ART/'stage.json')
assert m['reservation']['status']=='completed' and r['strict_success'] and all(r['checks'].values())
assert all(sha(ROOT/n)==h for n,h in s['files']['candidate'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['base_pointer']
save(A/'previous-pointer.json',s['base_pointer'])
auth={'quality_gate_override':False,'user_authorization':'이걸 한번에 해야될 것 같은데 그리고 나머지 문제 위에서 나왔던 현재 main에 있는문제들 전부다 고쳐',
 'scope':'Integrated repair and verified local MAIN activation; no GENOS deployment or Git push.',
 'qualification':{'source':bound(ADR/'실험/manifest.json'),'readme':bound(ADR/'README.md'),'arm':'candidate','result':bound(ART/'result.json'),'rebase':bound(ART/'release-rebase.json')}}
report={'structural_checks_passed':True,'integration':read(ART/'integration.json'),'checks':r['checks'],
 'evidence':[bound(ART/n) for n in ('result.json','analysis.json','contracts-final.json','consumer-candidate.json','consumer-working.json','working-integration.json')],
 'quality_certified':False,'genos_verified':False}
save(A/'authorization.json',auth);save(A/'validation.json',report)
print('User-authorized exact promotion record ready; no waiver')
