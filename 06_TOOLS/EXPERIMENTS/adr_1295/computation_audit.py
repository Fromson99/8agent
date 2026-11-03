"""Read-only current computation/gap observations; no claim rewriting or model call."""
from common import *
F=read(DES/'freeze.json');sys.path.insert(0,str(ROOT/F['code_root']/'02_BACKEND'))
from semantic_runtime.legal_agent import scenario_computation as calc,assessment_input as ai
P=ART/'live/review-whatif';rows=[];wire=[]
for label in ('low','high','rule'):
 path=P/('semantic-'+label+'-response.json.gz')
 if not path.exists():rows.append({'label':label,'observed':False});continue
 response=read(path);body=response.get('body') or {};meta=body.get('assembly',{}).get('term_agent',{});c=meta.get('scenario_context');r=meta.get('review_explanation',{}).get('scenario_calculation')
 row={'label':label,'observed':True,'http_status':response['status'],'claims':len((body.get('answer') or {}).get('claims',[])),'has_calculation':bool(r)}
 if c and r:
  expected=calc.build(c)
  row.update(receipt_matches=expected==r,render_in_answer=calc.render(r) in body['answer']['text'],
   inputs=r['inputs'],changes=r['changes'],predicate_statuses=[{'node':x['node_id'],'before':x['before']['status'],'current':x['current']['status']} for x in r['predicates']],
   missing_fields=r['missing_fields'],unregistered_effects=[x['node_id'] for x in r['unresolved_effects']],legal_conclusion_confirmed=r['legal_conclusion_confirmed'],
   saved_gaps=meta.get('gaps',[]),failed_checks=meta.get('review_explanation',{}).get('failed_checks',[]))
 rows.append(row)
for folder in sorted((P/'raw').glob('call-*')):
 request=read(folder/'request.json.gz');started=read(folder/'started.json')
 v=json.loads(next(m['content'] for m in request['messages'] if m['role']=='user'))
 v=v.get('view',v)
 if ai.META not in v:continue
 restored=ai.restore(v);schema=request.get('response_format',{}).get('json_schema',{}).get('schema',{})
 scenario=schema.get('properties',{}).get('scenario_review',{}).get('properties',{})
 output={}
 if (folder/'response.json.gz').exists():
  raw=read(folder/'response.json.gz')
  try:output=json.loads(raw['choices'][0]['message']['content'])
  except (ValueError,KeyError,IndexError,TypeError):pass
 choices=restored.get('computed_gap_options',[])
 if isinstance(choices,dict) and 'table_columns' in choices:
  choices=[dict(zip(choices['table_columns'],r)) for r in choices['table_rows']]
 selected=[{'index':i+1,**g} for i,g in enumerate(output.get('gaps',[])) if 'computed_gap_ref' in g]
 offered={r['computed_gap_ref'] for r in choices}
 wire.append({'number':started['number'],'turn':started['turn'],'stage':started['stage'],
  'offered_count':len(choices),'selected':selected,'all_selected_offered':all(r['computed_gap_ref'] in offered for r in selected),
  'condition_results_requested':'condition_results' in scenario,'application_links_requested':'application_links' in scenario,
  'execution_catalog_in_model_context':'calculation_catalog' in restored['hypothetical_scenario'],
  'obsolete_application_options_in_model_context':any(k in restored['hypothetical_scenario'] for k in ('application_values','application_conditions')),
  'computation_prompt_once':request['messages'][0]['content'].count(calc.PROMPT)==1})
checks={'all_three_calculations_verified':len(rows)==3 and all(r.get('receipt_matches') and r.get('render_in_answer') for r in rows),
 'no_legal_conclusion_inferred':all(r.get('legal_conclusion_confirmed') is False for r in rows),
 'new_wire_observed':bool(wire),'no_server_rewriting':bool(wire) and all(not r['condition_results_requested'] and not r['application_links_requested'] for r in wire),
 'no_extra_plan_or_role_copy':bool(wire) and all(not r['execution_catalog_in_model_context'] and not r['obsolete_application_options_in_model_context'] for r in wire),
 'explicit_gap_refs_offered':all(r['all_selected_offered'] for r in wire),'one_computation_prompt':bool(wire) and all(r['computation_prompt_once'] for r in wire)}
put(ART/'computation-audit.json',{'checks':checks,'responses':rows,'wire':wire,'model_calls':0,'limits':'Host display and exact offered choices, not legal truth or semantic adoption; inspect unmodified claims/gaps separately.'})
print(json.dumps({'checks':checks,'offered':sum(r['offered_count'] for r in wire),'selected':sum(len(r['selected']) for r in wire)},ensure_ascii=False))
