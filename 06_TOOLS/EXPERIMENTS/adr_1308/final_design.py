from pathlib import Path
import json,hashlib,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-1308-gold-query-optimization/artifacts';D=A/'design-final';D.mkdir(exist_ok=False)
old=A/'design';C=R/'02_BACKEND/lawrag/research/candidates/adr_1308/scope-fixed'
for name in ('criteria.json','baseline.json','gold-before.json','working-before-final.json'):
 shutil.copy2(old/name,D/name)
(D/'candidate-path.json').write_text(json.dumps({'candidate':str(C.relative_to(R)),'snapshot':str((C/'snapshot').relative_to(R))})+'\n')
(D/'scope-followup.json').write_text(json.dumps({'parent':json.loads((old/'freeze.json').read_text())['candidate_revision'],'reason':'Preserve document vs source scope kind in cached results and cursor bindings. Initial prepared r1 never activated. Fresh candidate after working integration; failed freeze paths retained.'},indent=2)+'\n')
p=T/'freeze.py';s=p.read_text().replace("ARTIFACTS_NOT_USED",'').replace("DES=ADR/'artifacts/design'","DES=ADR/'artifacts/design-final'").replace("'freeze-'+v['revision_id']+'.json'", "'freeze-'+C.name+'-'+v['revision_id']+'.json'").replace("candidate_id='optimized'","candidate_id=C.name");p.write_text(s)
p=T/'common.py';s=p.read_text().replace("DES=ART/'design'","DES=ART/'design-final'").replace("OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-gold-query-optimization'", "OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-gold-query-optimization/final'").replace("RELEASE='gold-query-optimized-20261103-r1'", "RELEASE='gold-query-optimized-20261103-r2'");p.write_text(s)
for name in ('check.py','oracle_select.py'):
 p=T/name;s=p.read_text().replace('artifacts/design/freeze.json','artifacts/design-final/freeze.json').replace('gold-query-optimized-20261103-r1/release.json','gold-query-optimized-20261103-r2/release.json');p.write_text(s)
p=T/'release_prepare.py';s=p.read_text().replace("before=b['working_files']","before=read(DES/'working-before-final.json')").replace("('contracts-final','regression-qualified')","('scope-final-r2','regression-qualified')").replace("ART/'oracle-select-final/result.json'","ART/'oracle-select-verified/result.json'").replace("ART/'working-before'","ART/'working-before-r2'");p.write_text(s)
print('Separate final design and candidate initialized; initial records preserved')
