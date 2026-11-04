from common import *
import shutil,datetime
result=read(ART/'comparison.json');assert result['speed_hypothesis_pass'] and result['new_regressions']==0
before=read(DES/'candidate-before.json');after=read(DES/'candidate-optimized.json');B=ROOT/before['code_root'];C=ROOT/after['code_root']
products=[n for n,h in after['selected_files'].items() if n.endswith('.py') and h!=before['selected_files'][n]]
assert len(products)==4
for n in products:assert sha(ROOT/n)==before['selected_files'][n],n
rollback=ART/'working-before';changed={}
for n in products:
 p=rollback/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,p);shutil.copyfile(C/n,ROOT/n);changed[n]={'before':sha(p),'after':sha(ROOT/n)}
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p);old=sha(p);change=False
 for n,h in d.get('files',{}).items():
  if n in products:d['files'][n]=sha(ROOT/n);change=True
 if change:
  back=rollback/p.relative_to(ROOT);back.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,back)
  p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');changed[str(p.relative_to(ROOT))]={'before':old,'after':sha(p)}
p=ROOT/'00_SYSTEM/PIPELINE.json';d=read(p);old=sha(p)
def rebind(x):
 if isinstance(x,dict):
  for k,v in list(x.items()):
   if k in changed and isinstance(v,str) and len(v)==64:x[k]=sha(ROOT/k)
   elif isinstance(v,str) and k in ('manifest','manifest_path') and v in changed:
    for hk in ('manifest_sha256','sha256'):
     if hk in x:x[hk]=sha(ROOT/v)
   elif isinstance(v,(dict,list)):rebind(v)
 elif isinstance(x,list):
  for v in x:rebind(v)
rebind(d);back=rollback/'00_SYSTEM/PIPELINE.json';back.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,back);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
changed[str(p.relative_to(ROOT))]={'before':old,'after':sha(p)}
put(ART/'working-integration.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'products':products,'changes':changed,'same_product_hashes_as_verified':all(sha(ROOT/n)==after['selected_files'][n] for n in products),'candidate_final_tables_ablation_not_integrated':True,'selected_main_changed':False})
put(DES/'candidate-working.json',{'code_root':'.','selected_files':{n:sha(ROOT/n) for n in read(DES/'baseline-after.json')['release']['files']}})
print('Integrated',len(products),'product modules and',len(changed)-len(products),'pins; MAIN136 not changed.')
