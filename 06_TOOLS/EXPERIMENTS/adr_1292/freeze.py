from common import *
import ast
C=ROOT/read(DES/'candidate-path.json')['candidate'];S=C/'snapshot'
# Rebind exact engine dependencies in the isolated snapshot only.
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p);changed=False
 if '02_BACKEND/semantic_runtime/ontology_work/configuration.py' in d.get('files',{}):
  extra='02_BACKEND/semantic_runtime/ontology_work/mapped_authoring.py';d['files'][extra]=sha(S/extra);changed=True
 if '02_BACKEND/semantic_runtime/legal_agent/compact_model_input.py' in d.get('files',{}):
  for leaf in ('assessment_links.py','scenario_application.py','scenario_computation.py'):
   extra='02_BACKEND/semantic_runtime/legal_agent/'+leaf
   d['files'][extra]=sha(S/extra)
  changed=True
 for n,h in d.get('files',{}).items():
  if (S/n).is_file() and sha(S/n)!=h:d['files'][n]=sha(S/n);changed=True
 if changed:p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
p=S/'00_SYSTEM/PIPELINE.json';d=read(p)
def patch(x):
 if isinstance(x,dict):
  for k,v in x.items():
   if isinstance(v,str) and (S/v).is_file() and k in ('manifest','manifest_path'):
    for hk in ('manifest_sha256','sha256'):
     if hk in x and isinstance(x[hk],str) and len(x[hk])==64:x[hk]=sha(S/v)
   elif isinstance(v,(dict,list)):patch(v)
 elif isinstance(x,list):
  for v in x:patch(v)
patch(d)
# The pipeline stores manifest pins under engine_manifests as a path/hash map.
def pins(x):
 if isinstance(x,dict):
  for k,v in list(x.items()):
   if isinstance(v,str) and len(v)==64 and k.startswith('02_BACKEND/ENGINES/') and (S/k).is_file():x[k]=sha(S/k)
   elif isinstance(v,(dict,list)):pins(v)
 elif isinstance(x,list):
  for v in x:pins(v)
pins(d);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
for p in S.rglob('*.py'):ast.parse(p.read_text())
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
v=read(C/'candidate.json')['revisions'][-1];S=C/'revisions'/v['revision_id']/'snapshot'
pin={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
files={str((ROOT/r['frozen_path']).relative_to(S)):r['snapshot_sha256'] for r in v['files']}
put(DES/('freeze-'+v['revision_id']+'.json'),{'code_root':str(S.relative_to(ROOT)),'files':files,'candidate_revision':pin,'pointer_sha256':read(DES/'baseline.json')['active_sha256'],'tests':{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('test_*.py'))}})
(DES/'freeze.json').write_text((DES/('freeze-'+v['revision_id']+'.json')).read_text())
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='verified',experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
print('Frozen',v['revision_id'],len(files))
