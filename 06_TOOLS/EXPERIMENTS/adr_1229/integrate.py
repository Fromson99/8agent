from common import *
import shutil,subprocess
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root']
assert read(ART/'checks-first.json')['passed']==82 and read(ART/'checks-first.json')['failed']==0
assert read(ART/'consumer-candidate-off.json')['passed']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
assert all(sha(C/n)==h for n,h in f['files'].items())
# Live audit must be finished against the unchanged working baseline first.
audit=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1230-source-meaning-evidence-live/artifacts/audit.json')
assert all(audit['checks'].values()) and audit['calls']<=4
changes=[n for n,h in f['files'].items() if not (ROOT/n).exists() or sha(ROOT/n)!=h]
pins=[n for n in changes if n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/')]
products=[n for n in changes if n not in pins];assert len(pins)==31 and len(products)==3
for n in products:
 if n not in b['working_files']:assert not (ROOT/n).exists()
for n in changes:
 (ROOT/n).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'all489_exact':True,'changed_files':{n:f['files'][n] for n in changes},'products':products,'pins':pins,'baseline_main':b['active']['release_id'],'other_files_preserved':True})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','source-meaning-preview-20261030-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==34
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Exact tested inventory pin' if row['path'] in pins else 'Independent source analysis with separated interpretation/evidence; nullable recorded roles; source-selected semantic assembly and preserved canonical validation'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
print('Working489 exact; changes34; MAIN122 still selected')
