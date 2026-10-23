from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
new='02_BACKEND/semantic_runtime/legal_agent/answer_progress.py'
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p)
 if 'files' in d:
  if '02_BACKEND/semantic_runtime/legal_agent/decision_projection.py' in d['files']:
   d['files'][new]=sha(C/new)
   for name in ('delegated_content.py','content_plan.py','definition_context.py'):
    n='02_BACKEND/semantic_runtime/legal_agent/'+name;d['files'][n]=sha(C/n)
  d['files']={n:sha(C/n) for n in d['files']};save(p,d)
p=C/'00_SYSTEM/PIPELINE.json';d=read(p)
for e in d['engines'].values():e['sha256']=sha(C/e['manifest'])
save(p,d)
