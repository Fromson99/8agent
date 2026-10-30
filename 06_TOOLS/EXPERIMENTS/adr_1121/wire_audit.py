"""Verify actual request copies against bound canonical originals and ontology refs."""
from common import *
import gzip,sys
arm=sys.argv[1];f=read(ART/'freeze.json');C=ROOT/f['code_root']
sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
P=ART/'run-001'/arm/'cm-023';calls=read(P/'calls.json');rows=[]
def gz(p):return json.loads(gzip.decompress(p.read_bytes()))
def expand_tables(v):
 if isinstance(v,list):return [expand_tables(x) for x in v]
 if not isinstance(v,dict):return v
 if 'columns' in v and 'rows' in v:return [dict(zip(v['columns'],[expand_tables(x) for x in row])) for row in v['rows']]
 if 'table_columns' in v and 'table_rows' in v:return [dict(zip(v['table_columns'],[expand_tables(x) for x in row])) for row in v['table_rows']]
 return {k:expand_tables(x) for k,x in v.items()}
physical=0
for call in calls:
 cp=P/'canonical'/f"{call['generation']:03d}.json.gz";wp=P/'wire'/f"{call['call']:03d}.json.gz"
 canonical=gz(cp)['view'];wirebody=gz(wp);view=expand_tables(json.loads(wirebody['messages'][1]['content'])['view'])
 if call.get('new_model_call'):
  physical+=1;native=next((P/'raw').glob(f'call-{physical:03d}-*/request.json'));actual=read(native)
 else:actual=wirebody
 actual_view=expand_tables(json.loads(actual['messages'][1]['content'])['view'])
 row={'call':call['call'],'phase':call['phase'],'actual_view_equals_recorded':actual_view==view,'actual_model':actual['model'],
      'output_cap_fields':[k for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in actual],
      'ontology_cards':len(view.get('ontology_bundles',[])),'source_units':len(canonical.get('sources',[]))}
 if call['phase'].startswith('memory-assess'):
  refs=NavigationReferences(canonical);mapped=refs.view(canonical);options={o['id']:o for o in view.get('evidence_options',[])}
  texts={s['text_id']:s['text'] for s in view.get('sources',[]) if 'text_id' in s and 'text' in s}
  def option_text(o):
   if 'text' in o:return o['text']
   r=o.get('text_ref',{});return texts[r['text_id']][r['start']:r['end']] if r else None
  checks=[]
  for o in mapped.get('evidence_options',[]):
   w=options.get(o['id']);checks.append({'id':o['id'],'match':w is not None and option_text(w)==o['text']})
  row.update(original_option_count=len(checks),original_option_mismatches=[o for o in checks if not o['match']],
   presented_sources=[{'source_id':s['source_id'],'document_id':s['document_id'],'unit_id':s.get('unit_id'),'heading':s['heading']} for s in canonical.get('sources',[])],
   ontology=[])
  expected={c['bundle_id'] if 'bundle_id' in c else c['payload']['bundle_id']:c for c in mapped.get('ontology_bundles',[])}
  for card in view.get('ontology_bundles',[]):
   payload=card.get('payload',{});provisions=payload.get('provisions',[]);offered=[r for p in provisions for r in p.get('source_refs',[])]
   row['ontology'].append({'bundle_id':payload.get('bundle_id'),'status':card.get('status'),'provisions':len(provisions),'source_refs':offered,
     'unknown_source_refs':[r for r in offered if r not in options],
     'concept':payload.get('concept'),'relations':len(payload.get('relations',[])),'review_notes':len(payload.get('review_notes',[])),
     'provision_original_copy_count':sum('text' in p for p in provisions),
     'prepared':all(p.get('delivery_status')=='PREPARED' for p in provisions if p.get('source_refs'))})
 if call['phase'].startswith('memory-assess'):
  row['semantic_plans']=[]
  for card in view.get('ontology_bundles',[]):
   plan=card.get('payload',{}).get('semantic_plan')
   if not plan:continue
   used=[ref for n in plan['ordered_steps'] for ref in n.get('source_refs',[])]
   quotes=[b for n in plan['ordered_steps'] for b in n.get('basis',[])]
   def quoted(b):
    texts_for_refs=[option_text(options[r]) for r in b['source_refs'] if r in options]
    return b['quote'] in ''.join(x or '' for x in texts_for_refs)
   row['semantic_plans'].append({'steps':len(plan['ordered_steps']),'authority':plan['authority'],'unknown_refs':[r for r in used if r not in options],'quote_checks':len(quotes),'quote_failures':[b for b in quotes if not quoted(b)]})
 rows.append(row)
out={'arm':arm,'calls':rows,'request_copy_mismatches':sum(not r['actual_view_equals_recorded'] for r in rows),
 'output_cap_fields':sum(len(r['output_cap_fields']) for r in rows),'assess_original_mismatches':sum(len(r.get('original_option_mismatches',[])) for r in rows),
 'unknown_ontology_refs':sum(len(o['unknown_source_refs']) for r in rows for o in r.get('ontology',[]))}
out['semantic_unknown_refs']=sum(len(p['unknown_refs']) for r in rows for p in r.get('semantic_plans',[]));out['semantic_quote_failures']=sum(len(p['quote_failures']) for r in rows for p in r.get('semantic_plans',[]))
put(P/'wire-audit.json',out);print(arm,{k:v for k,v in out.items() if k!='calls'})
