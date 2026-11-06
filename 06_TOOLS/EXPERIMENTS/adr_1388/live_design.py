from common import *
import shutil
# Reuse only the archived public case and provider binding. No old job is resumed.
seed_source=ROOT/'04_EXPERIMENTS/ADR/ADR-1387-main145-stored-review-recovery/artifacts'
for name in ['source-scope','provider-policy','parent-profile','live-cases']:
    v=read(seed_source/'design'/(name+'.json'))
    if name=='live-cases':v[0]['arms']=['repaired']
    put(DES/(name+'.json'),v)
shutil.copytree(seed_source/'transport',ART/'transport')
for name in ['origin','action-request']:
    put(ART/'action-seed'/(name+'.json'),read(seed_source/'action-seed'/(name+'.json')))
put(DES/'authorization.json',{'user':'수정해봐; preceding explicit actual Qwen test','public_documents':read(DES/'source-scope.json')['public'],'principal':'same authorized experiment owner as parent','source_archive':read(DES/'origin.json')['archive'],'case_hash':sha(DES/'live-cases.json'),'conditional_action':False})
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json'),*(ART/'action-seed').glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.name!='freeze-public.json'},'before_model_calls':True})
