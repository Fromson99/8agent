"""Read-only Gemma experiment progress, including provider errors before generation."""
import json,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0498-gemma4-fp8-compatible-schema-cm51-fsc10/artifacts'
def read(p):return json.loads(p.read_text())
def main():
 rows=[]
 for p in (A/'run-001').glob('*/gemma/result.json'):
  try:rows.append(read(p))
  except (OSError,ValueError):pass
 replies=[];errors=[]
 for p in (A/'run-001').glob('*/gemma/calls/call-*/response.json'):
  try:x=read(p)
  except (OSError,ValueError):continue
  if x.get('error'):errors.append({'case':p.parts[-5],'error':x['error']})
  elif x.get('choices'):replies.append(x)
 processes={}
 for label in ['product','offline']:
  p=A/(label+'-process.json')
  if p.exists():
   x=read(p);pid=x['pid'];cmd=Path('/proc')/str(pid)/'cmdline'
   try:running='adr_0498/' in cmd.read_bytes().decode()
   except OSError:running=False
   processes[label]={'pid':pid,'running_in_this_namespace':running}
 print(json.dumps({'experiment':'ADR-0498','planned':61,'completed':len(rows),'reviewed_answers':sum(bool(x.get('result',{}).get('answer',{}).get('claims')) for x in rows),'requests':len(list((A/'run-001').glob('*/gemma/calls/call-*/request.json'))),'generated_replies':len(replies),'provider_errors':errors,'models':sorted({x.get('model') for x in replies}),'providers':sorted({x.get('provider') for x in replies}),'reasoning_tokens':sum(((x.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') or 0 for x in replies),'product_batch_complete':(A/'run-001/results.json').exists(),'scored':(A/'metrics.json').exists(),'completion':read(A/'completion.json') if (A/'completion.json').exists() else None,'processes':processes},ensure_ascii=False))
if __name__=='__main__':main()
