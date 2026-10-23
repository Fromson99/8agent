# Offline artifact ID correction; frozen call runner is unchanged.
from common import *
p=ART/'manifest.json';old=read(p);files=[]
for item in sorted(ART.rglob('*')):
    if item.is_file() and item!=p and not item.name.endswith('validation.log'):
        files.append({'path':str(item.relative_to(ROOT)),'sha256':sha(item),'bytes':item.stat().st_size,
            'description':'Frozen design, native retest, or offline audit. See RESULT.txt for execution limits.',
            'contains_raw_prompts_and_outputs':'model' in item.parts or item.name=='runtime.tar.gz'})
for item in sorted(Path(__file__).parent.glob('*.py')):
    files.append({'path':str(item.relative_to(ROOT)),'sha256':sha(item),'bytes':item.stat().st_size,
        'description':'Runner or offline audit. Call runner hashes remain bound to design-freeze.json.',
        'contains_raw_prompts_and_outputs':False})
save(p,{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1027','created_at':old['created_at'],'files':files})
print('Recorded artifact hashes:',len(files))
