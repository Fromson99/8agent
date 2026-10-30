from common import *
tool_files={str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
put(DES/'runner-inventory-final.json',{'files':tool_files,'scope':'Exact technical test and promotion helpers; no product data'})
runtime_files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted((ART/'test-runtime').rglob('*')) if p.is_file()]
ref=write_raw_json(ART/'test-runtime-inventory.json.gz',runtime_files)
put(ART/'test-runtime-reference.json',{'raw_json':ref,'files':len(runtime_files),'scope':'Synthetic and stored-response runtime fixture files; compressed inventory only'})
a=read(ART/'manifest.json');a['files']=[]
for p in sorted(ART.rglob('*')):
 if not p.is_file() or p==ART/'manifest.json' or any(x.startswith('staged-code') or x in ('__pycache__','test-runtime') for x in p.parts):continue
 a['files'].append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen criterion, technical evidence, preserved failure, or integration receipt','contains_raw_prompts_and_outputs':False})
(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print('Registered',len(a['files']),'artifacts')
