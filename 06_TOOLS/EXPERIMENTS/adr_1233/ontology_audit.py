"""Read-only source/ontology/model/answer lineage after the frozen native run."""
from pathlib import Path
import gzip,json,sys,hashlib
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1233-gold-ontology-on-live';O=A/'artifacts/run-001';P=O/'live/gold-369'
def read(p):
 with (gzip.open(p,'rt') if str(p).endswith('.gz') else p.open()) as f:return json.load(f)
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def strings(v):
 if isinstance(v,str):yield v
 elif isinstance(v,dict):
  for x in v.values():yield from strings(x)
 elif isinstance(v,list):
  for x in v:yield from strings(x)
binding=read(R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json');C=R/binding['engine_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.contracts import digest
publications=read(R/'09_ARTIFACTS/AUDITS/20261030-gold-ontology-publication/publication-receipts.json')
pub_ids={p['publication_id'] for p in publications};events=[];states=[];budgets=[]
for path in (P/'runtime').rglob('journal.sqlite'):
 with connect(path.as_uri()+'?mode=ro',uri=True) as db:
  for row in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq'):
   if any(t in row[1] for t in ('ONTOLOGY','SCENARIO','VECTOR')):events.append({'seq':row[0],'kind':row[1],'payload':json.loads(row[2])})
  states.extend({'kind':r[0],'id':r[1],'version':r[2],'payload':json.loads(r[3])} for r in db.execute('SELECT kind,entity_id,version,payload_json FROM entity_version'))
  budgets.extend(dict(r) for r in db.execute('SELECT * FROM budget'))
calls=read(P/'calls.json') if (P/'calls.json').exists() else []
views=[]
for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 v=read(p)['view'];cards=v.get('ontology_bundles',[])
 if cards:views.append({'path':str(p.relative_to(R)),'stage':v.get('source_stage'),'cards':cards})
wire=[]
for p in sorted((P/'raw').glob('*/request.json.gz')):
 req=read(p);items=[]
 for msg in req['messages']:
  try:items.extend(strings(json.loads(msg['content'])))
  except (ValueError,TypeError):items.append(str(msg['content']))
 wire.append({'path':str(p.relative_to(R)),'strings':items})
package_bodies={}
for view in views:
 for card in view['cards']:
  catalog=card.get('payload',{}).get('scenario_catalog') or card.get('scenario_catalog')
  if catalog:
   for path in catalog['paths']:package_bodies[path['id']]=path['body']
wire_hits={pid:[w['path'] for w in wire if any(body in s for s in w['strings'])] for pid,body in package_bodies.items()}
found_pub_ids=sorted({x for state in states for x in strings(state['payload']) if x in pub_ids})
selected=[e for e in events if e['kind']=='SCENARIO_SELECTED']
selection=[]
for event in selected:
 for path in event['payload'].get('selected_paths',[]):
  selection.append(path)
response=read(P/'response.json') if (P/'response.json').exists() else {};answer=response.get('body',{}).get('answer') or {}
text=answer.get('text','') if isinstance(answer,dict) else str(answer)
answer_matches={pid:body in text for pid,body in package_bodies.items()}
profile=read(P/'binding.json')['profile']['candidate_navigation']
result=read(P/'result.json');integrity=read(P/'audit.json')
gates={'ontology_on_db':profile['ontology_enabled'] is True and profile['ontology_context']=={'mode':'DB'},
 'real_publication_acquired':bool(found_pub_ids),'scenario_presented_to_model':bool(package_bodies) and all(wire_hits.values()),
 'model_selected_scenario':bool(selection),'selected_body_in_answer':bool(selection) and all(
  any(digest(body)==p['body_sha256'] and body in text for body in package_bodies.values()) for p in selection),
 'final_answer_issued':response.get('http_status')==200 and bool(text.strip()),
 'originals_exact_and_authorized':not integrity['source_mismatches'] and not integrity['acl_violations'],
 'wire_exact':not integrity['wire_request_mismatches'] and integrity['wire_request_matches']==len(calls),
 'budget_exact':integrity['physical_budget_matches'],'no_unknown_or_resource_stop':result['unknown']==0 and not (P/'resource-stop.json').exists(),
 'saved_answer_matches':integrity['storage'].get('checked') and integrity['storage'].get('answer_equal')}
details={'events':events,'actual_publication_ids':found_pub_ids,'model_views_with_ontology':views,
         'wire_exact_path_bodies':wire_hits,'selected_paths':selection,'answer_body_matches':answer_matches}
with gzip.open(O/'ontology-lineage.json.gz','wt') as f:json.dump(details,f,ensure_ascii=False)
summary={'status':'PASS_GOLD_ONTOLOGY_REAL_NATIVE_E2E' if all(gates.values()) else 'INCOMPLETE_GOLD_ONTOLOGY_REAL_NATIVE_E2E',
 'gates':gates,'actual_publication_count':len(found_pub_ids),'presented_paths':len(package_bodies),
 'selected_paths':len(selection),'answer_chars':len(text),'ontology_events':len(events),
 'physical_calls':len(calls),'sql_calls':result['sql_calls'],'seconds':result['seconds'],
 'reported_cost_usd':integrity['reported_cost_usd'],'quality_certified':False,'new_audit_model_calls':0}
write(O/'ontology-e2e.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
