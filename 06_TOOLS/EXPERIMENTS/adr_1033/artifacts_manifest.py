from common import *
from datetime import datetime,timezone
p=ART/'manifest.json';created=read(p)['created_at'] if p.exists() else datetime.now(timezone.utc).isoformat();files=[]
for item in sorted(ART.rglob('*')):
 if item.is_file() and item!=p and not item.name.endswith('validation.log'):
  files.append({'path':str(item.relative_to(ROOT)),'sha256':sha(item),'bytes':item.stat().st_size,
   'description':'Frozen implementation design, contract/API logs, baseline failures, integration/rollback or validation record.',
   'contains_raw_prompts_and_outputs':False})
for item in sorted(Path(__file__).parent.glob('*.py')):
 files.append({'path':str(item.relative_to(ROOT)),'sha256':sha(item),'bytes':item.stat().st_size,
  'description':'Implementation staging, frozen contract runner or offline completion record.',
  'contains_raw_prompts_and_outputs':False})
save(p,{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1033','created_at':created,'files':files})
print('Artifact hashes:',len(files))
