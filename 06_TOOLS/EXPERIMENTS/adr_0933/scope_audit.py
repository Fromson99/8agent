"""Offline audit of the actual workflow grant and stored ingestion metadata."""
from pathlib import Path
import json,gzip,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0933-packet-update-threaded-validation';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
G=R/read(D/'baseline.json')['manifest']['data_path'];db=sqlite3.connect('file:'+str(G/'store.sqlite')+'?mode=ro',uri=True)
manifest=read(G/'manifest.json');cases=read(D/'cases.json')
for arm in ('baseline','fixed'):
 b=read(D/(arm+'-binding.json'));grant=read(R/b['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['workflow_authorization']
 assert grant['authorized_by']=='user' and grant['generation_id']==manifest['generation_id'] and grant['store_sha256']==manifest['store_sha256']
 for c in cases:
  P=O/arm/c['id']
  out=A/('artifacts/scope-'+arm+'-'+c['id']+'.json')
  if not (P/'audit.json').exists() or out.exists():continue
  audit=read(P/'audit.json');checks=[];seen=set();views=[]
  for side,child in audit['children'].items():
   for e in child['all_read_evidence']:
    did=e['document_id']
    if (side,did) in seen:continue
    seen.add((side,did));raw=db.execute("SELECT json_extract(json,'$.document_metadata'),json_extract(json,'$.document_category') FROM document WHERE document_id=?",(did,)).fetchone()
    meta=json.loads(raw[0]) if raw and raw[0] else {};category=raw[1] or meta.get('source_category')
    checks.append({'side':side,'document_id':did,'in_workflow_grant':did in grant['document_ids'],'stored_category':category,'side_matches':category==side,'basis':'Immutable ingestion document_metadata.source_category or explicit document_category; no title inference.'})
  for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
   with gzip.open(p,'rt') as f:v=json.load(f)['view']
   op=p.with_name(p.name.replace('.json.gz','-output.json.gz'));value={}
   if op.exists():
    with gzip.open(op,'rt') as f:value=json.load(f)
   acts=v.get('actions') or [];acts=list(acts.values()) if isinstance(acts,dict) else acts
   views.append({'number':int(p.name[:3]),'stage':v.get('source_stage',v.get('phase')),'offered_leads':len((v.get('investigation_leads') or {}).get('items',[])),'offered_reference_cards':len((v.get('references') or {}).get('dependency_cards',[])),'selected_action':next((r for r in acts if r.get('id')==value.get('target_id')),None),'reason':value.get('reason'),'next_tasks':[t for item in value.get('items',[]) for t in item.get('next_tasks',[])]})
  result={'arm':arm,'case_id':c['id'],'input_root':str(P.relative_to(R)),'checks':checks,'all_scope_checks_pass':bool(checks) and all(x['in_workflow_grant'] and x['side_matches'] for x in checks),'model_views':views,'authorization_kind':'USER_AUTHORIZED_WORKFLOW; source corpus is not all public','prior_diagnostic':'ADR0928 exploration-audit used wrong public-RAG grant and ignored ingestion metadata; its false flags are not evidence of a scope violation.'}
  out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(arm,c['id'],'scope_pass',result['all_scope_checks_pass'])
db.close()
