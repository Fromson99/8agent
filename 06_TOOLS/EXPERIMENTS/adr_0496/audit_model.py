"""Verify actual request and returned model/usage receipts without new calls."""
import json,hashlib
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0496-qwen-source-workflow-cm51-fsc10';ART=A/'artifacts';EXPECTED='qwen/qwen3.5-122b-a10b'
def read(p):return json.loads(p.read_text())
def main():
 rows=[]
 for p in sorted((ART/'run-001').rglob('call-*/request.json')):
  x=read(p);response=p.parent/'response.json';v=read(response) if response.exists() else {};binding=read(p.parent/'binding.json')
  rows.append({'path':str(p.relative_to(R)),'role':'judge' if 'judge' in p.parts else 'product','requested_model':x['model'],'actual_model':v.get('model'),'actual_provider':v.get('provider'),'fp8_requested':x.get('provider',{}).get('quantizations')==['fp8'],'provider_fallbacks_disabled':x.get('provider',{}).get('allow_fallbacks') is False,'reasoning_disabled':x.get('reasoning',{}).get('enabled') is False and x.get('chat_template_kwargs',{}).get('enable_thinking') is not True,'optional_chat_template_thinking':x.get('chat_template_kwargs',{}).get('enable_thinking'),'reasoning_tokens':(v.get('usage',{}).get('completion_tokens_details') or {}).get('reasoning_tokens'),'has_usage':bool(v.get('usage')),'response_present':response.exists(),'model_matches':v.get('model')==EXPECTED if v.get('model') else None,'policy_sha256':binding['policy_sha256']})
 summary={}
 for role in ['product','judge']:
  rr=[x for x in rows if x['role']==role];summary[role]={'requests':len(rr),'returned_models':dict(Counter(x['actual_model'] for x in rr)),'returned_providers':dict(Counter(x['actual_provider'] for x in rr)),'nonzero_reasoning_receipts':sum(bool(x['reasoning_tokens']) for x in rr),'missing_usage':sum(not x['has_usage'] for x in rr),'request_policy_all_valid':all(x['fp8_requested'] and x['reasoning_disabled'] and x['provider_fallbacks_disabled'] and x['requested_model']==EXPECTED for x in rr),'returned_model_mismatches':[x['path'] for x in rr if x['model_matches'] is False]}
 out={'summary':summary,'rows':rows,'notes':['Quantization is the requested provider routing constraint, not independent verification of provider weight precision.','Missing/unknown transport responses have no reliable actual-model or usage receipt.','Pinned policy requires reasoning.enabled=false; optional provider chat_template flag may be absent, but must not enable thinking.']};(ART/'model-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
