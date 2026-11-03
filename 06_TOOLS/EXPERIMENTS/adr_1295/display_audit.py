"""Read-only actual response and frozen UI projection audit; no model call."""
from common import *
import importlib.util, re
F=read(DES/'freeze.json'); C=ROOT/F['code_root']
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import assessment_input as ai
spec=importlib.util.spec_from_file_location('adr1295_workflow',C/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
workflow=importlib.util.module_from_spec(spec);spec.loader.exec_module(workflow)
P=ART/'live/review-whatif'; raw_rows=[]; offered=set()
for folder in sorted((P/'raw').glob('call-*')):
 request=read(folder/'request.json.gz'); started=read(folder/'started.json')
 v=json.loads(next(m['content'] for m in request['messages'] if m['role']=='user'));v=v.get('view',v)
 if ai.META not in v:continue
 restored=ai.restore(v);choices=restored.get('computed_gap_options',[])
 if isinstance(choices,dict):choices=[dict(zip(choices['table_columns'],r)) for r in choices['table_rows']]
 refs={r['computed_gap_ref'] for r in choices};offered.update(refs)
 response=read(folder/'response.json.gz') if (folder/'response.json.gz').exists() else {}
 try:output=json.loads(response['choices'][0]['message']['content'])
 except (ValueError,KeyError,IndexError,TypeError):output={}
 leaked=[i for i,g in enumerate(output.get('gaps',[])) if any(x in g.get('reason','') for x in refs)]
 selected=[g for g in output.get('gaps',[]) if 'computed_gap_ref' in g]
 raw_rows.append({'call':started['number'],'turn':started['turn'],'offered':len(refs),
  'exact_offered_id_in_reason_indexes':leaked,'structured_choices':selected,
  'repair_feedback':restored.get('repair_feedback'),'raw_path':str(folder.relative_to(ROOT))})
rows=[]
for label in ('low','high','rule'):
 path=P/('semantic-'+label+'-response.json.gz')
 if not path.exists():rows.append({'label':label,'observed':False});continue
 response=read(path);body=response.get('body') or {};meta=body.get('assembly',{}).get('term_agent',{});view=meta.get('review_explanation')
 row={'label':label,'observed':True,'http_status':response['status']}
 if view:
  rendered=workflow._review_explanation_text(body);(P/('semantic-'+label+'-ui.txt')).write_text(rendered)
  reasons=[x['reason'] for x in view['items']];declarations=[x['historical_declaration'] for x in view['items'] if x.get('historical_declaration')]
  histories=view.get('historical_issues',[])
  current_part=rendered.split('**기준 사건의',1)[0]
  old_amount=lambda s:bool(re.search(r'138\s*만|1,?380,?000|1380000',s))
  row.update(ui_projection_rendered=bool(rendered),current_reasons=reasons,
   historical_declarations=declarations,historical_issues=histories,
   historical_declarations_labelled=not declarations or '**기준 사건의 조사 이력 (현재 가정의 요구사항 아님)**' in rendered,
   historical_issues_labelled=not histories or '**기준 사건의 질문 이력 (현재 가정값은 계산표 참조)**' in rendered,
   exact_offered_ids_in_current_prose=[x for x in offered if x in current_part or x in (body.get('answer') or {}).get('text','')],
   original_cost_in_current_review=old_amount(current_part),
   original_cost_in_current_review_is_superseded=label!='rule' and old_amount(current_part),
   failed_checks=view.get('failed_checks',[]),claims=len((body.get('answer') or {}).get('claims',[])))
 rows.append(row)
observed=[r for r in rows if r.get('ui_projection_rendered')]
put(ART/'display-audit.json',{'responses':rows,'raw_proposals':raw_rows,'model_calls':0,
 'all_three_observed':len(observed)==3,
 'observed_exact_ids_absent':bool(observed) and all(not r['exact_offered_ids_in_current_prose'] for r in observed),
 'observed_history_separated':bool(observed) and all(r['historical_declarations_labelled'] and r['historical_issues_labelled'] and not r['original_cost_in_current_review_is_superseded'] for r in observed),
 'limits':'Exact offered references and UI current/history fields only. Original regulatory text and explicitly labelled comparisons retain original amounts. No browser, deployed GENOS, generic free-text correctness or legal quality certification.'})
print(json.dumps({'responses':[{k:v for k,v in r.items() if k not in ('current_reasons','historical_declarations','historical_issues')} for r in rows],
 'raw_id_leak_calls':[r['call'] for r in raw_rows if r['exact_offered_id_in_reason_indexes']]},ensure_ascii=False))
