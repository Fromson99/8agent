"""Cumulative MAIN96 overlay, including the prior bounded-finalization patch."""
import ast,hashlib,json,subprocess,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
NAME='GENOS_COMPARISON_READABLE_20261021_R2'
BASE=HERE.with_name('main96_ad_disabled_20261021_r1')
PRIOR=HERE.with_name('comparison_readable_20261021_r1')
TEN=HERE.with_name('comparison_ten_minute_20261021_r1')
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261021-comparison-readable-r2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (HERE/'SEALED.json').exists(),'Already sealed'
before=read(BASE/'PACKAGE.json')['code']; prior=read(PRIOR/'PACKAGE.json')['code']; ten=read(TEN/'PACKAGE.json')['code']
after={n:sha(ROOT/n) for n in prior}
changed={n for n in after if after[n]!=prior[n]}
allowed={'02_BACKEND/workflow/risk_team_compare_workflow/concept_report.py',
 '02_BACKEND/workflow/risk_team_compare_workflow/finalize.py',
 '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','00_SYSTEM/PIPELINE.json',
 '02_BACKEND/workflow/risk_team_compare_workflow/manifest.json',
 '02_BACKEND/workflow/internal_basis_discovery_workflow/manifest.json'}
assert all(n in allowed or n.startswith('02_BACKEND/ENGINES/') for n in changed),changed-allowed
patch=[n for n in after if before.get(n)!=after[n]]
for n in patch:
 target=HERE/'payload'/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
 if n.endswith('.py'):ast.parse(target.read_bytes(),filename=n,feature_version=(3,11))
for name in ('runner.py','genos_release_gate.py'):(HERE/name).write_bytes((PRIOR/name).read_bytes())
run=(PRIOR/'GENOS_COMPARISON_READABLE_20261021_R1_RUN.txt').read_text()
run=run.replace('GENOS_COMPARISON_READABLE_20261021_R1',NAME).replace('comparison-readable-r1-logs','comparison-readable-r2-logs')
(HERE/(NAME+'_RUN.txt')).write_text(run)
subprocess.run(['bash','-n',str(HERE/(NAME+'_RUN.txt'))],check=True)
editor='GENOS_COMPARISON_READABLE_WORKFLOW_ALL.txt'
(HERE/editor).write_bytes((ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes())
ast.parse((HERE/editor).read_bytes(),filename=editor,feature_version=(3,10))
manifest={'format':'8agent-code/1','files':[{'path':n,'sha256':after[n],'bytes':(ROOT/n).stat().st_size} for n in patch],
 'required_files':[{'path':n,'sha256':h} for n,h in after.items() if n not in patch]}
save(HERE/'CODE_MANIFEST.json',manifest)
with zipfile.ZipFile(HERE/'code.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 z.write(HERE/'CODE_MANIFEST.json','CODE_MANIFEST.json')
 for n in patch:z.write(ROOT/n,n)
(HERE/'COMMIT_PATHS.txt').write_text('\n'.join(patch)+'\n')
files=['runner.py','genos_release_gate.py',NAME+'_RUN.txt','PATCH_NOTE.txt',editor,
 'CODE_MANIFEST.json','COMMIT_PATHS.txt','code.zip']+['payload/'+n for n in patch]
if (HERE/'HANDOFF_VALIDATION.txt').exists():files.append('HANDOFF_VALIDATION.txt')
save(HERE/'PACKAGE.json',{'version':NAME,'base_release':'ad-management-disabled-20261021-r1','code':after,'patch':patch,
 'allowed_before':{n:list(dict.fromkeys([before.get(n),ten.get(n),prior.get(n),h])) for n,h in after.items()},
 'payload':{n:sha(HERE/n) for n in files},'workflow_version':'1.20.6',
 'GENOS_field_verified':False,'data_modified':False,'selected_main_modified':False})
with zipfile.ZipFile(HERE/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n in sorted(files+['PACKAGE.json']):z.write(HERE/n,n)
for p in (HERE/(NAME+'.zip'),HERE/'code.zip'):
 with zipfile.ZipFile(p) as z:
  assert not z.testzip()
  assert not any(Path(n).suffix.lower() in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
save(HERE/'BUILD.json',{'archive':NAME+'.zip','sha256':sha(HERE/(NAME+'.zip')),'bytes':(HERE/(NAME+'.zip')).stat().st_size,
 'patch_files':len(patch),'required_code_files':len(after),'changed_since_readable_r1':sorted(changed),
 'source_root':str(ROOT),'code_manifest_sha256':sha(HERE/'CODE_MANIFEST.json'),
 'workflow_editor_sha256':sha(HERE/editor),'selected_release':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'GENOS_checkout':'~/DEV (physical path recorded at check)','GENOS_commit':None,'GENOS_generation_path':None,
 'GENOS_generation_manifest_sha256':None,'GENOS_serving_revision':None,'GENOS_revision_generation_setting':None})
(HERE/'SHA256SUMS.txt').write_text('\n'.join(sha(HERE/n)+'  '+n for n in [NAME+'.zip',NAME+'_RUN.txt',editor,'PATCH_NOTE.txt'])+'\n')
print(json.dumps({'patch_files':len(patch),'code_files':len(after),'changed_since_prior':len(changed),'zip':NAME+'.zip'}))
