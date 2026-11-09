"""Make the working inventory equal MAIN177 bytes for the batch, then restore exactly.

The root service reads some inventory files (derived pins) from ROOT. A parallel
session's uncommitted edit (parallel_excluded) is never touched; if one of those
files is loaded, live.py's loaded-module byte check fails the request instead.
restore only rewrites files still holding the MAIN177 bytes this script wrote, so
a change made by another session during the batch is preserved and reported.
"""
from common import *
import shutil,time
mode=sys.argv[1];assert mode in ('apply','restore')
target=read(DES/'candidate-selected.json');src=ROOT/target['code_root'];skip=set(target['parallel_excluded'])
record=ART/'tree-swap.json';backup=ART/'tree-swap-backup'
if mode=='apply':
 assert not record.exists(),'swap already applied; restore first'
 swapped={}
 for n,h in target['selected_files'].items():
  if n in skip:continue
  if sha(ROOT/n)!=h:
   assert sha(src/n)==h,n
   b=backup/n;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,b)
   swapped[n]={'working_sha256':sha(b),'main_sha256':h}
 for n in swapped:shutil.copyfile(src/n,ROOT/n)
 assert all(sha(ROOT/n)==h for n,h in target['selected_files'].items() if n not in skip)
 put(record,{'applied_at':time.time(),'swapped':swapped,'parallel_excluded':sorted(skip)})
 print('applied',len(swapped),'files')
else:
 r=read(record);restored=[];kept=[]
 for n,v in r['swapped'].items():
  if sha(ROOT/n)==v['main_sha256']:
   assert sha(backup/n)==v['working_sha256'];shutil.copyfile(backup/n,ROOT/n);restored.append(n)
  else:kept.append({'path':n,'current_sha256':sha(ROOT/n)})
 assert all(sha(ROOT/n)==r['swapped'][n]['working_sha256'] for n in restored)
 put(ART/'tree-restore.json',{'restored_at':time.time(),'restored':len(restored),'changed_during_run_kept':kept})
 print('restored',len(restored),'kept',len(kept))
