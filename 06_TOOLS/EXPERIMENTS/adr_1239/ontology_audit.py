"""Actual ordinary ASSESS with ontology; no scenario-selection claim or legal judge."""
from pathlib import Path
import json,gzip,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1239-main124-gold-live-revalidation';O=A/'artifacts/run-001';P=O/'live/gold-369'
def read(p):
 with (gzip.open(p,'rt') if str(p).endswith('.gz') else p.open()) as f:return json.load(f)
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary,write_raw_json
put=write_summary
def walk(v):
 if isinstance(v,dict):
  yield v
  for x in v.values():yield from walk(x)
 elif isinstance(v,list):
  for x in v:yield from walk(x)
def strings(v):
 if isinstance(v,str):yield v
 elif isinstance(v,dict):
  for x in v.values():yield from strings(x)
 elif isinstance(v,list):
  for x in v:yield from strings(x)
C=R/read(R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json')['engine_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.contracts import digest
views=[];claims=[];events=[];assessments=[]
for cp in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 v=read(cp)['view']
 if not str(v.get('source_stage','')).startswith('memory-assess'):continue
 op=cp.with_name(cp.name.replace('.json.gz','-output.json.gz'));out=read(op) if op.exists() else None
 views.append({'path':str(cp.relative_to(R)),'view':v,'accepted_output':out})
 if out:claims.extend(out.get('claims',[]))
for jp in P.rglob('journal.sqlite'):
 with connect(jp.as_uri()+'?mode=ro',uri=True) as db:
  for r in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq'):
   if any(k in r[1] for k in ('ONTOLOGY','SCENARIO','REJECT','FAILED')):events.append({'seq':r[0],'kind':r[1],'payload':json.loads(r[2])})
  for r in db.execute("SELECT payload_json FROM entity_version WHERE kind='case_stage' and entity_id='case:ASSESS'"):
   assessments.append(json.loads(r[0]))
paths={};source_refs={};cards=[]
for item in views:
 v=item['view'];cards.extend(v.get('ontology_bundles',[]))
 for op in v.get('evidence_options',[]):source_refs[op['id']]=op
 for card in v.get('ontology_bundles',[]):
  cat=card.get('payload',{}).get('scenario_catalog') or card.get('scenario_catalog')
  if cat:
   for path in cat['paths']:paths[path['id']]=path
raw_strings=[]
for rp in (P/'raw').glob('*/request.json.gz'):
 for m in read(rp)['messages']:
  try:raw_strings.extend(strings(json.loads(m['content'])))
  except (ValueError,TypeError):raw_strings.append(str(m['content']))
wire_paths={pid:any(path['body'] in s for s in raw_strings) for pid,path in paths.items()}
body=read(P/'response.json').get('body',{}) if (P/'response.json').exists() else {};answer=body.get('answer') or {};answer=answer if isinstance(answer,dict) else {};text=answer.get('text','')
# Full answer's structured claims are the authoritative output if available.
final_claims=answer.get('claims') or claims
required={'PER_SHARE':'1421','OWN_SHARES':'1422','CROSS_HOLDING':'1423'};lineage={}
for name,bid in required.items():
 refs={ref for ref,row in source_refs.items() if row['document_id']=='7bbe815ff43b6635' and str(row['block_id'])==bid}
 matched=[c for c in final_claims if refs.intersection(c.get('evidence_refs',[]))]
 norms=[n.get('text','') for c in matched for n in c.get('rule',{}).get('norms',[]) if refs.intersection(n.get('evidence_refs',[])) or n.get('source_ref') in refs]
 lineage[name]={'block_id':bid,'source_refs':sorted(refs),'claim_ids':list(dict.fromkeys(c.get('claim_id') for c in matched)),'norms':norms,'norm_in_answer':any(n and n in text for n in norms)}
profile=read(P/'binding.json')['profile']['candidate_navigation'];a=read(P/'audit.json');r=read(P/'result.json');gates={'ON_DB':profile['ontology_enabled'] is True and profile['ontology_context']=={'mode':'DB'},'actual_acquisition':any(e['kind']=='ONTOLOGY_BUNDLE_ACQUISITION' and e['payload']['status']=='ACQUIRED' for e in events),'all_three_paths_in_wire':set(required)<=paths.keys() and all(wire_paths.get(k) for k in required),'all_four_provisions_prepared':any(len(c.get('payload',{}).get('provisions',[]))==4 and all(p.get('source_refs') for p in c['payload']['provisions']) for c in cards),'three_rule_proposals_with_current_originals':all(v['claim_ids'] for v in lineage.values()),'three_rules_in_final_answer':all(v['norm_in_answer'] for v in lineage.values()),'final_answer_issued':r.get('http_status')==200 and bool(text.strip()),'exact_originals_ACL_wire':not a['source_mismatches'] and not a['acl_violations'] and not a['wire_request_mismatches'],'budget_exact':a['physical_budget_matches'],'saved_answer_matches':a['storage'].get('checked') and a['storage'].get('answer_equal'),'no_unknown_resource_stop':not r['unknown'] and not a['resource']['stop']}
result={'status':'PASS_KNOWN_QUESTION_GOLD_ONTOLOGY_ORDINARY_ASSESS_E2E' if all(gates.values()) else 'INCOMPLETE_GOLD_ONTOLOGY_ORDINARY_ASSESS_E2E','gates':gates,'lineage':lineage,'paths_presented':len(paths),'answer_chars':len(text),'quality_certified':False,'causal_ontology_use_proven':False,'scenario_selection_mode':False,'model_calls':r['model_calls'],'sql_calls':r['sql_calls'],'seconds':r['seconds'],'reported_cost_usd':a['reported_cost_usd'],'new_audit_model_calls':0}
put(O/'ontology-e2e.json',result)
receipt=write_raw_json(O/'ontology-lineage.json.gz',{'views':views,'events':events,'assessments':assessments,'wire_paths':wire_paths,'result':result});put(O/'ontology-lineage-reference.json',receipt)
print(json.dumps(result,ensure_ascii=False,indent=2))
