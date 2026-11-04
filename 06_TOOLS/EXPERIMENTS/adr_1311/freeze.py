from common import *
import ast,datetime
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
T=Path(__file__).parent;m=read(ADR/'실험/manifest.json');pins=[]
for arm in ['before','optimized']:
 d=read(DES/(arm+'-path.json'));can=ROOT/d['candidate'];S=can/'snapshot'/d['code_relative']
 if arm=='optimized':
  for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
   v=read(p);changed=False
   for n,h in v.get('files',{}).items():
    if (S/n).is_file() and sha(S/n)!=h:v['files'][n]=sha(S/n);changed=True
   if changed:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
  p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
  def rebind(x):
   if isinstance(x,dict):
    for k,val in list(x.items()):
     if isinstance(val,str) and len(val)==64 and k.startswith('02_BACKEND/ENGINES/') and (S/k).is_file():x[k]=sha(S/k)
     elif isinstance(val,str) and k in ('manifest','manifest_path') and (S/val).is_file():
      for hk in ('manifest_sha256','sha256'):
       if hk in x and isinstance(x[hk],str) and len(x[hk])==64:x[hk]=sha(S/val)
     elif isinstance(val,(dict,list)):rebind(val)
   elif isinstance(x,list):
    for val in x:rebind(val)
  rebind(v);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 for p in S.rglob('*.py'):ast.parse(p.read_text())
 ac.freeze(can);assert not ac.validate(can),ac.validate(can)
 cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'/d['code_relative']
 desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in d['files']},'original_selected_files':read(DES/'baseline-after.json')['release']['files'],'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
 put(DES/('candidate-'+arm+'.json'),desc)
 pins.append(dict(desc['pin'],candidate_id=arm,experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'],runner_path=str((T/'replay.py').relative_to(ROOT)),runner_sha256=sha(T/'replay.py')))
paths=[p for p in DES.glob('*.json') if p.name!='freeze.json']+list((ART/'transport').rglob('*.py'))+[ART/'transport/transport-pins.json']+[p for p in T.glob('*.py') if p.name not in ('finalize.py','integrate.py')]
source=ROOT/read(DES/'source-cell.json')['path'];paths += [source/'request.json',source/'response.json.gz',source/'calls.json']+list((source/'raw').glob('call-*/*.json.gz'))
put(DES/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'new_model_calls':0})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=pins);put(ADR/'실험/manifest.json',m)
print('Frozen before/optimized517 files each.')
