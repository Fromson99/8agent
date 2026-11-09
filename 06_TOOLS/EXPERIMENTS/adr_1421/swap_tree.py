"""Make every working inventory file equal one arm's exact bytes (root service imports some from ROOT)."""
from common import *
import shutil
arm=sys.argv[1];target=read(DES/('arm-'+arm+'.json'))
src=ROOT/target['code_root']
changed=[];skip=set(target.get('parallel_excluded',[]))
for n,h in target['selected_files'].items():
 if n in skip:continue  # another session's uncommitted edit; a loaded module with other bytes fails the binding check
 if sha(ROOT/n)!=h:
  assert sha(src/n)==h,n;shutil.copyfile(src/n,ROOT/n);changed.append(n)
assert all(sha(ROOT/n)==h for n,h in target['selected_files'].items() if n not in skip)
log=ART/'tree-swaps.json';rows=read(log) if log.exists() else [];rows.append({'arm':arm,'files_rewritten':len(changed),'time':__import__('time').time()});put(log,rows)
print('working inventory now equals',arm,'bytes;',len(changed),'files rewritten')
