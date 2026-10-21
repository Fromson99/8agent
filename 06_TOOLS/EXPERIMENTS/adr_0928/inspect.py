"""Read-only scope and connected-exploration observations of closed requests."""
from pathlib import Path
import json,gzip,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0928-connected-source-other-cm-regression';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
G=R/read(D/'baseline.json')['manifest']['data_path'];source=sqlite3.connect('file:'+str(G/'store.sqlite')+'?mode=ro',uri=True)
for P in sorted(O.glob('*/*')):
 if not (P/'audit.json').exists() or (P/'exploration-audit.json').exists():continue
 arm=P.parent.name;b=read(D/(arm+'-binding.json'));grant=read(R/b['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json');allowed=set(grant['public_document_ids']);audit=read(P/'audit.json');views=[];events=[];scope_checks=[]
 for path in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  with gzip.open(path,'rt') as f:v=json.load(f)['view']
  op=path.with_name(path.name.replace('.json.gz','-output.json.gz'));out={}
  if op.exists():
   with gzip.open(op,'rt') as f:out=json.load(f)
  actions=v.get('actions') or [];actions=list(actions.values()) if isinstance(actions,dict) else actions
  chosen=next((x for x in actions if x.get('id')==out.get('target_id')),None)
  refs=v.get('references') or {};leads=v.get('investigation_leads') or {}
  views.append({'number':int(path.name[:3]),'stage':v.get('source_stage',v.get('phase')),'offered_reference_cards':len(refs.get('dependency_cards',[])),'offered_leads':len(leads.get('items',[])),'choice':chosen,'reason':out.get('reason'),'parent_next_tasks':[t for item in out.get('items',[]) for t in item.get('next_tasks',[])]})
 for j in audit['journals']:
  path=R/j['path'];db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
  for raw in db.execute("SELECT payload_json FROM event WHERE kind='DOCUMENT_TERM_CANDIDATES'"):events.append({'side':j['side'],**json.loads(raw[0])})
  for did, in db.execute('SELECT DISTINCT document_id FROM evidence_unit'):
   meta=source.execute('SELECT json FROM document WHERE document_id=?',(did,)).fetchone();meta=json.loads(meta[0]) if meta else {};category=meta.get('document_category')
   scope_checks.append({'side':j['side'],'document_id':did,'in_public_grant':did in allowed,'document_category':category,'side_matches':j['side']=='parent' or category==j['side']})
  db.close()
 result={'schema_version':'connected-regression-audit-v1','arm':arm,'case_id':P.name,'views':views,'document_term_queries':events,'scope_checks':scope_checks,'all_scope_checks_pass':all(r['in_public_grant'] and r['side_matches'] for r in scope_checks),'note':'No relevance/correctness inferred from term hits or additional reads. Known same-title variants retain separate source identities.'}
 (P/'exploration-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(arm,P.name,'term_queries',len(events),'scope_pass',result['all_scope_checks_pass'])
source.close()
