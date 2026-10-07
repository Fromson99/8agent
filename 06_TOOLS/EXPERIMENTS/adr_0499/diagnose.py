"""Read-only journal diagnostics, independent of Qwen evaluator labels."""
import json,sqlite3,math,statistics
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0499-qwen-interrupted-five-retry';ART=A/'artifacts'
def read(p):return json.loads(p.read_text())
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True)
def parse_response(x):
 try:
  data=json.loads(x);body=data.get('body_json') or json.loads(data.get('body_text') or '{}');s=body['choices'][0]['message']['content'];return json.loads(s)
 except (ValueError,KeyError,TypeError,IndexError):return None

def transmitted_view(raw):
 for message in reversed(json.loads(raw).get('messages',[])):
  try:body=json.loads(message.get('content',''))
  except (ValueError,TypeError):continue
  if isinstance(body,dict) and isinstance(body.get('view'),dict):return body['view']
 return {}

def main():
 fixture=read(A/'product-cases.json');gold={c['case_id']:set(c['decisive_source_ids']) for c in read(A/'gold-cases.json')['cases']};rows=[]
 for case in fixture['cases']:
  cid=case['case_id'];p=ART/'run-001'/cid/'repaired';r=read(p/'result.json');t=read(p/'trace.json');g=gold[cid]
  with sqlite3.connect('file:'+str(p/'journal.sqlite')+'?mode=ro',uri=True) as db:
   db.row_factory=sqlite3.Row
   events=[{**dict(x),'payload':json.loads(x['payload_json'])} for x in db.execute('SELECT * FROM event ORDER BY seq')]
   attempts=[{**dict(x),'view':transmitted_view(x['request_json']),'parsed':parse_response(x['response_json'])} for x in db.execute('SELECT a.*,v.phase,v.body_json FROM model_attempt a JOIN model_view v USING(view_id) ORDER BY a.created_seq')]
  workflow=[e for e in events if e['kind']=='WORKFLOW_REPAIR'];semantic=[e for e in events if e['kind']=='SEMANTIC_REPAIR'];schemas=[e for e in events if e['kind']=='OUTPUT_SCHEMA_INVALID']
  errors=[]
  for ev in workflow:
   for err in ev['payload'].get('errors',[]):
    actual=err.get('actual',{});signature=canon({'tool':actual.get('tool'),'args':actual.get('args')});msg=err.get('message','')
    later=next((a for a in attempts if a['created_seq']>ev['seq'] and a['status']=='SUCCEEDED'),None)
    error_shown=False;same_again=None
    if later:
     error_shown=msg in canon(later['view'].get('errors',[]))
     proposal=later['parsed'] or {};acts=proposal.get('actions',[])
     same_again=any(canon({'tool':x.get('tool'),'args':x.get('args')})==signature for x in acts)
    correction_keys={canon({'tool':x.get('tool'),'args':x.get('args')}) for x in err.get('corrective_actions',[])}
    accepted_corrections=[]
    for action in t.get('actions',[]):
     if action['actor']!='MODEL' or action['created_seq']<=ev['seq']:continue
     req=json.loads(action['proposed_json']);res=json.loads(action['result_json'] or '{}')
     if canon({'tool':req.get('tool'),'args':req.get('args')}) in correction_keys and res.get('status') in ('OK','PARTIAL','REUSED'):accepted_corrections.append(action['action_id'])
    errors.append({'seq':ev['seq'],'message':msg,'actual':actual,'corrective_actions':err.get('corrective_actions',[]),'next_successful_view_received_error':error_shown,'same_tool_args_in_next_proposal':same_again,'supplied_correction_later_succeeded':accepted_corrections})
  actions=[]
  for x in t.get('actions',[]):
   q=json.loads(x['proposed_json']);res=json.loads(x['result_json'] or '{}');actions.append({'actor':x['actor'],'seq':x['created_seq'],'tool':q.get('tool'),'args':q.get('args'), 'status':res.get('status'),'evidence_ids':res.get('evidence_ids',[]),'new_read_chars':res.get('budget',{}).get('new_read_chars',0)})
  modelactions=[x for x in actions if x['actor']=='MODEL'];modelreads=[x for x in modelactions if x['tool']=='read'];firstread=min((x['seq'] for x in modelreads),default=None)
  drafts=[];reviews=[]
  for a in attempts:
   parsed=a['parsed'];v=a['view']
   if a['phase']=='compose':
    shown={e['evidence'] for e in v.get('exact_evidence',[])};allowed=set(v.get('evidence_roles',{}).get('support',[]));cited={e for para in (parsed or {}).get('paragraphs',[]) for e in para.get('evidence',[])}
    drafts.append({'view_id':a['view_id'],'seq':a['created_seq'],'parsed':parsed is not None,'shown_count':len(shown),'allowed_count':len(allowed),'cited':sorted(cited),'displayed_but_unselected_citations':sorted((cited&shown)-allowed),'not_displayed_citations':sorted(cited-shown),'paragraph_texts':[p.get('text') for p in (parsed or {}).get('paragraphs',[])]})
   if a['phase']=='review':reviews.append({'view_id':a['view_id'],'seq':a['created_seq'],'parsed':parsed})
  s=r.get('stages',{});counts={k:len(v) for k,v in s.items()};goldstages={k:len(set(v)&g) for k,v in s.items()}
  missed={}
  stages=['discovered','read','presented','selected','payload_sources','final_sources']
  for gid in sorted(g):missed[gid]=next((st for st in stages if gid not in s.get(st,[])),'delivered')
  rows.append({'case_id':cid,'suite':case['suite'],'stage_counts':counts,'gold_by_stage':goldstages,'required_source_first_missing_stage':missed,'workflow_errors':errors,'schema_events':[e['payload'] for e in schemas],'semantic_events':[e['payload'] for e in semantic],'event_counts':dict(Counter(e['kind'] for e in events)),'attempt_statuses':dict(Counter(a['status'] for a in attempts)),'phases':dict(Counter(a['phase'] for a in attempts)),'parsed_proposals':sum(a['parsed'] is not None for a in attempts),'attempts':len(attempts),'tool_counts_by_actor':{actor:dict(Counter(a['tool'] for a in actions if a['actor']==actor)) for actor in sorted({a['actor'] for a in actions})},'first_read_after_model_attempts':sum(a['created_seq']<firstread for a in attempts) if firstread else None,'zero_new_chars_model_reads':sum(a['new_read_chars']==0 and a['status']=='OK' for a in modelreads),'exact_repeated_model_operations':sum(n-1 for n in Counter(canon({'tool':x['tool'],'args':x['args']}) for x in modelactions).values()),'drafts':drafts,'reviews':reviews,'limitations':r.get('limitations',[]),'claims':len(r.get('result',{}).get('answer',{}).get('claims',[])),'publication_status':r.get('publication_status'),'execution_error':r.get('error'),'seconds':r['seconds'],'controller_seconds':r.get('controller_seconds'),'calls':r['physical_calls']})
 cohorts={}
 for name,rr in [('all',rows),('CM51',[x for x in rows if x['case_id'].startswith('cm-')]),('FSC10',[x for x in rows if x['case_id'].startswith('fsc-')])]:
  ee=[e for x in rr for e in x['workflow_errors']];drafts=[d for x in rr for d in x['drafts']]
  cohorts[name]={'total':len(rr),'stage_case_totals':{s:sum(x['stage_counts'].get(s,0)>0 for x in rr) for s in stages},'stage_source_totals':{s:sum(x['stage_counts'].get(s,0) for x in rr) for s in stages},'gold_by_stage':{s:sum(x['gold_by_stage'].get(s,0) for x in rr) for s in stages},'gold_total':sum(len(x['required_source_first_missing_stage']) for x in rr),'first_gold_loss_counts':dict(Counter(v for x in rr for v in x['required_source_first_missing_stage'].values())),'discovered_but_zero_read':[x['case_id'] for x in rr if x['stage_counts'].get('discovered',0)>0 and x['stage_counts'].get('read',0)==0],'read_but_zero_presented':[x['case_id'] for x in rr if x['stage_counts'].get('read',0)>0 and x['stage_counts'].get('presented',0)==0],'presented_but_zero_selected':[x['case_id'] for x in rr if x['stage_counts'].get('presented',0)>0 and x['stage_counts'].get('selected',0)==0],'selected_but_no_claims':[x['case_id'] for x in rr if x['stage_counts'].get('selected',0)>0 and x['claims']==0],'reviewed_answer_cases':sum(x['claims']>0 for x in rr),'workflow_error_cases':sum(bool(x['workflow_errors']) for x in rr),'workflow_error_events':len(ee),'workflow_error_messages':dict(Counter(e['message'] for e in ee)),'error_returned_next_view':sum(e['next_successful_view_received_error'] for e in ee),'same_rejected_operation_repeated_next_view':sum(e['same_tool_args_in_next_proposal'] is True for e in ee),'no_corrective_action_errors':sum(not e['corrective_actions'] for e in ee),'supplied_correction_later_succeeded':sum(bool(e['supplied_correction_later_succeeded']) for e in ee),'schema_error_cases':sum(bool(x['schema_events']) for x in rr),'schema_error_events':sum(len(x['schema_events']) for x in rr),'semantic_error_messages':dict(Counter(e.get('message','') for x in rr for e in x['semantic_events'])),'draft_attempts':len(drafts),'draft_displayed_unselected_citation_cases':sum(any(d['displayed_but_unselected_citations'] for d in x['drafts']) for x in rr),'draft_not_displayed_citation_cases':sum(any(d['not_displayed_citations'] for d in x['drafts']) for x in rr),'attempt_statuses':dict(sum((Counter(x['attempt_statuses']) for x in rr),Counter())),'calls':sum(x['calls'] for x in rr),'parsed_proposals':sum(x['parsed_proposals'] for x in rr),'attempts':sum(x['attempts'] for x in rr),'first_read_attempt_median':statistics.median(x['first_read_after_model_attempts'] for x in rr if x['first_read_after_model_attempts'] is not None) if any(x['first_read_after_model_attempts'] is not None for x in rr) else None}
 out={'schema_version':'adr0499-workflow-diagnostics-v1','by_cohort':cohorts,'by_case':rows,'notes':['Schema event count is strict validator signal; JSON parsing is reported separately.','Error repetition means same tool+args next successful proposal, regardless of prose reason; no inference of intent.','Displayed-but-unselected citation is a model constraint error with a server input-design contribution; not invented ID.','Canonical article hit does not certify complete paragraph/item coverage.','Zero new chars can be a legitimate reread; not all repeated operations are errors.']}
 (ART/'workflow-diagnostics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(cohorts,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
