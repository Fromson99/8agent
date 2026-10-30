from common import *
import shutil
f=read(DES/'freeze.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json');S=ART/'serving-code';assert not S.exists();assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
files={n:h for n,h in f['files'].items() if n!='02_BACKEND/lawrag/research/experiment_client.py'};assert len(files)==432
for n,h in files.items():
 assert sha(C/n)==h;dest=S/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,dest)
changed=[n for n in files if files[n]!=b['release']['files'].get(n)];assert len(changed)==53
put(DES/'staging.json',{'code_root':str(S.relative_to(ROOT)),'files':files,'changed':changed,'excluded_candidate_paths':{'02_BACKEND/lawrag/research/experiment_client.py':{'sha256':f['files']['02_BACKEND/lawrag/research/experiment_client.py'],'reason':'experiment-only external call instrumentation; not a serving dependency'}}})
print('432 staged exact candidate files;53 changes vsMAIN107')
