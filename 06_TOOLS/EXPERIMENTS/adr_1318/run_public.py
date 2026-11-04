"""Sequential declared cases; never retry any previously dispatched case."""
from common import *
import subprocess,time
from collections import Counter
frozen=read(DES/'freeze-public.json')
for p,h in frozen['files'].items():assert sha(ROOT/p)==h,p
public=set(read(DES/'source-scope.json')['public'])
groups=read(DES/'cases.json');results=[];consecutive=0
for group in groups:
 ident=group['id'];base=ART/'public-live'/(ident+'-selected-main')
 if not (set(group['document_ids'])<=public or all(s['mode']=='대사' for s in group['steps'])):
  results.append({'id':ident,'state':'INTERNAL_MODEL_REQUIRED','reason':'Do not relabel actual private history public'});continue
 if (ART/'STOP_EXTERNAL.json').exists():
  results.append({'id':ident,'state':'NOT_RUN','reason':'Unknown physical outcome stop'});continue
 if consecutive>=3:
  results.append({'id':ident,'state':'NOT_RUN','reason':'Three consecutive independent technical failures'});continue
 if base.exists():
  if not (base/'result.json').exists():
   results.append({'id':ident,'state':'NOT_RERUN','reason':'Existing incomplete dispatch'});consecutive+=1;continue
 else:
  with (ART/(ident+'-console.txt')).open('x') as log:
   proc=subprocess.run([str(ROOT/'.venv/bin/python'),str(Path(__file__).with_name('live_public.py')),ident,'selected-main'],env={**os.environ,'MALLOC_ARENA_MAX':'1'},stdout=log,stderr=subprocess.STDOUT)
  if proc.returncode or not (base/'result.json').exists():
   results.append({'id':ident,'state':'RUNNER_FAILURE','exit_code':proc.returncode});consecutive+=1;put(ART/'batch-progress.json',results);continue
 result=read(base/'result.json');failed=any(t['http_status']>=400 for t in result['turns'])
 consecutive=consecutive+1 if failed else 0
 results.append({'id':ident,'state':'TECHNICAL_FAILURE' if failed else 'REVIEW_RESPONSE','result':result})
 put(ART/'batch-progress.json',results)
 print(ident,results[-1]['state'],'calls',result['physical_calls'],'consecutive',consecutive,flush=True)
put(ART/'batch-progress.json',results)
print('BATCH_DONE',dict(Counter(x['state'] for x in results)),flush=True)
