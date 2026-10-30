from common import *
import shutil,subprocess
f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root'];plan=read(DES/'integration-plan.json')
products=[n for n in plan['changed'] if '/ENGINES/' not in n and n!='00_SYSTEM/PIPELINE.json']
status=subprocess.check_output(['git','status','--porcelain','-z'],cwd=ROOT).decode().split('\0')
protected={s[3:]:sha(ROOT/s[3:]) for s in status if s and s[:2]!='??' and (ROOT/s[3:]).is_file() and s[3:] not in plan['changed']}
for n in plan['changed']:assert (sha(ROOT/n) if (ROOT/n).is_file() else None)==b['working_files'].get(n),'concurrent edit: '+n
for n in products:
 source=ART/'working-merged'/n if n in plan['overlapping_working_edits'] else C/n
 dest=ROOT/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
# Merge dependency inventories, preserving independent storage pins already present.
for n in plan['changed']:
 if '/ENGINES/' not in n:continue
 p=ROOT/n;v=read(p);before=read(ROOT/b['manifest']['code_root']/n);candidate=read(C/n)
 for name,h in candidate['files'].items():
  if before['files'].get(name)!=h:v['files'][name]=sha(ROOT/name)
 for name in v['files']:v['files'][name]=sha(ROOT/name)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'00_SYSTEM/PIPELINE.json';v=read(p)
for e in v['engines'].values():e['sha256']=sha(ROOT/e['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert all(sha(ROOT/n)==h for n,h in protected.items())
for n in plan['overlapping_working_edits']:assert 'journal_text(payload_json)' in (ROOT/n).read_text()
put(ART/'working-integration.json',{'strategy':'Exact baseline preconditions; two clean three-way merges retain journal storage; dependency inventory union, source files preserved','product_files':{n:sha(ROOT/n) for n in products},'pins':{n:sha(ROOT/n) for n in plan['changed'] if n not in products},'protected':protected,'protected_unchanged':True,'different_from_release':plan['overlapping_working_edits'],'data_modified':False,'new_model_calls':0})
print('Working integrated:',len(products),'products; two storage edits retained; other tracked changes preserved')
