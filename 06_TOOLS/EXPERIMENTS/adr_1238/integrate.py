from common import *
import shutil,subprocess
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root']
rows={}
for tag in ('candidate-ready','candidate-fixture-corrected','native-unknown'):
 for r in read(ART/('checks-'+tag+'.json'))['rows']:rows[r['test']]=r
failed={k:v for k,v in rows.items() if v['status']=='failed'}
old={r['test']:r for r in read(ART/'checks-baseline-existing-failures.json')['rows'] if r['status']=='failed'}
assert set(failed)==set(old) and len(failed)==4
for k in failed:
 assert failed[k]['error'].splitlines()[-1]==old[k]['error'].splitlines()[-1],k
assert sum(r['status']=='passed' for r in rows.values())==223
assert read(ART/'consumer-candidate-off.json')['passed']
assert read(ART/'gold-binding-candidate.json')['passed']
assert read(ART/'gold-candidate/consumer-verification.json')['status']=='PASS'
assert read(ART/'gold-candidate/ontology-verification.json')['publications']==3
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
assert all(sha(C/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items())
changes=[n for n,h in f['files'].items() if sha(ROOT/n)!=h]
pins=[n for n in changes if n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/')]
products=[n for n in changes if n not in pins];assert len(pins)==31 and len(products)==5
put(ART/'contract-summary.json',{'passed':223,'existing_failed':4,'new_failures':0,'rows':list(rows.values()),'baseline_failure_tests':list(old),'external_model_calls':0,'fixture_corrections':'stdlib inspect preload; correct pytest hook signature; basetemp parent; legacy test contract roots set to frozen code. Product validators unchanged.'})
for n in changes:shutil.copy2(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'all489_exact':True,'changed_files':{n:f['files'][n] for n in changes},'products':products,'pins':pins,'baseline_main':b['active']['release_id'],'gold_port_not_yet_switched':True})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','judgment-gold-preview-20261030-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==36
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Exact serving inventory pin' if row['path'] in pins else 'Preserve incomplete judgment/conflict visibility; stop unknown supervisor before downstream calls/resume; integrate Gold exact-source rebind and response-local claim IDs'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
print('Working489 exact; product5+pin31; unchanged MAIN123 still selected')
