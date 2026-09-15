from pathlib import Path
import json,httpx,datetime,time
from dotenv import dotenv_values
A=Path('/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0384-gemini-available-model-policy/artifacts')
plan={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'models_in_price_order':['gemini-3.1-flash-lite','gemini-3.5-flash-lite'],'selection_rule':'First successful synthetic generation; advance only on404 model unavailability, not on quality/schema/quota errors','max_calls':2,'max_output_tokens':256,'thinking_level':'minimal','source':'synthetic ready boolean','quality_comparison':False}
(A/'availability-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
key=dotenv_values('/home/jin/8-AGENT/.env')['GEMINI_API_KEY'];results=[]
for model in plan['models_in_price_order']:
 payload={'contents':[{'parts':[{'text':'Return JSON {"ready":true} only.'}]}],'generationConfig':{'maxOutputTokens':256,'temperature':0,'thinkingConfig':{'thinkingLevel':'minimal'},'responseMimeType':'application/json'}}
 d=A/model;d.mkdir();(d/'request.json').write_text(json.dumps(payload,indent=2)+'\n');start=time.monotonic()
 with httpx.Client(timeout=60,trust_env=False,follow_redirects=False) as c:r=c.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',headers={'x-goog-api-key':key},json=payload)
 data=r.json();assert key not in json.dumps(data);(d/'response.json').write_text(json.dumps(data,indent=2)+'\n');results.append({'model':model,'http_status':r.status_code,'seconds':time.monotonic()-start});print(results[-1],flush=True)
 if r.is_success:
  print('SELECTED',model,flush=True);(A/'selected-model.json').write_text(json.dumps({'model':model,'checks':results,'usage':data.get('usageMetadata')},indent=2)+'\n');break
 if r.status_code!=404:break
(A/'availability-results.json').write_text(json.dumps(results,indent=2)+'\n')
