"""Inspect saved complete/partial SSE. No model request or outcome rewriting."""
from common import *
import base64
rows=[]
for p in sorted((ART/'public-live').glob('*/raw/call-*/partial.json.gz')):
 v=read(p);body=base64.b64decode(v['body_base64']);text=body.decode('utf-8',errors='replace').replace('\r\n','\n')
 events=[];comments=[];content=[];ids=set();errors=[]
 for frame in text.split('\n\n'):
  comments.extend(line for line in frame.splitlines() if line.startswith(':'))
  data='\n'.join(line[5:].removeprefix(' ') for line in frame.splitlines() if line.startswith('data:'))
  if not data or data=='[DONE]':continue
  try:event=json.loads(data)
  except ValueError:continue
  events.append(event)
  if event.get('id'):ids.add(event['id'])
  if event.get('error'):errors.append(event['error'])
  for c in event.get('choices',[]):
   x=c.get('delta',{}).get('content')
   if isinstance(x,str):content.append(x)
 diag=v.get('diagnostics',{});header=diag.get('response_headers',{}).get('x-generation-id')
 if header:ids.add(header)
 joined=''.join(content)
 rows.append({'path':str(p.relative_to(ROOT)),'generation_ids':sorted(ids),'sse_events':len(events),'comments':len(comments),'model_content_chunks':len(content),'model_content_chars':len(joined),'model_content_whitespace_only':bool(joined) and not joined.strip(),'model_content_prefix':joined[:600],'model_content_suffix':joined[-600:],'errors':errors,'diagnostics':diag})
put(ART/'stream-diagnosis.json',{'rows':rows,'model_calls':0,'raw_records_preserved':True})
print(json.dumps(rows,ensure_ascii=False,indent=2))
