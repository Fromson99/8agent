from common import *
import datetime,ast
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
T=Path(__file__).parent;m=read(ADR/'실험/manifest.json');pins=[]
for arm in ('before','after'):
 x=read(DES/(arm+'-path.json'));can=ROOT/x['candidate'];ac.freeze(can);assert not ac.validate(can),ac.validate(can);cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'/x['code_relative'];files={n:sha(C/n) for n in x['files']}
 # Full internal pin consistency; never silently accept a mixed working capture.
 for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
  v=read(p)
  for n,h in v.get('files',{}).items():assert sha(C/n)==h,(str(p),n)
 desc={'code_root':str(C.relative_to(ROOT)),'selected_files':files,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}};put(DES/('candidate-'+arm+'.json'),desc);pins.append(dict(desc['pin'],candidate_id=arm,experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'],runner_path=str((T/'query.py').relative_to(ROOT)),runner_sha256=sha(T/'query.py')))
for p in T.glob('*.py'):ast.parse(p.read_text())
paths=list((ART/'gold-connector').glob('*'))+[p for p in DES.glob('*.json') if p.name!='freeze.json']+list(T.glob('*.py'));b=read(ART/'gold-connector/binding.json');paths += [ROOT/n for n in b['files']]
put(DES/'freeze.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.is_file()},'model_calls':0})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=pins);put(ADR/'실험/manifest.json',m);print('Before/after frozen and ALL internalenginepinsverified')
