from common import *
import shutil
source=ROOT/'04_EXPERIMENTS/ADR/ADR-1394-main146-multiturn-audit/artifacts'
for name in ['live-cases','authorization','source-scope','provider-policy']:
    obj=read(source/'design'/(name+'.json'))
    if name=='live-cases':obj[0]['arms']=['repaired']
    put(DES/(name+'.json'),obj)
shutil.copytree(source/'transport',ART/'transport',dirs_exist_ok=True)
m=read(ADR/'실험/manifest.json');m['design']['code_isolation']['candidates'][0]['runner_path']=str((Path(__file__).parent/'live_public.py').relative_to(ROOT));m['design']['code_isolation']['candidates'][0]['runner_sha256']=sha(Path(__file__).parent/'live_public.py');put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.name!='freeze-public.json'},'before_model_calls':True})
