from common import *
import datetime
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
files=read(DES/'working-files.json');old=ROOT/read(DES/'sqlite-path.json')['candidate']/'snapshot';assert all(sha(old/n)==h for n,h in files.items())
put(ART/'preparation-failure.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'freeze_error':'present upstream changed before candidate freeze: 00_SYSTEM/PIPELINE.json','test_error':'candidate descriptor absent; no tests executed','drift_paths':[n for n,h in files.items() if sha(ROOT/n)!=h],'recovery':'Preserve both original captures and current working tree. New candidates copy the exact prior capture as immutable upstream, with identical517files. No product changes.'})
m=read(ADR/'실험/manifest.json');prefix=str(old.relative_to(ROOT))
for arm in ('sqlite','oracle'):
 can=ac.snapshot(ADR,arm+'-stable',[prefix+'/'+n for n in files],experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001']);put(DES/(arm+'-path.json'),{'candidate':str(can.relative_to(ROOT)),'code_relative':prefix})
p=Path(__file__).parent/'freeze.py';s=p.read_text().replace("C=can/'revisions'/rev['revision_id']/'snapshot';files=", "C=can/'revisions'/rev['revision_id']/'snapshot'/read(DES/(arm+'-path.json'))['code_relative'];files=").replace('candidate_id=arm,','candidate_id=arm+\'-stable\',');p.write_text(s)
p=Path(__file__).parent/'query.py';s=p.read_text().replace("assert store.manifest['store_sha256']==read(DES/'baseline.json')['release']['data_sha256'] if 'data_sha256' in read(DES/'baseline.json')['release'] else True", "assert store.manifest['store_sha256']==read(ROOT/read(DES/'baseline.json')['release']['data_path']/'manifest.json')['store_sha256']")
p.write_text(s)
print('Preserved drift, new stable candidates ready')
