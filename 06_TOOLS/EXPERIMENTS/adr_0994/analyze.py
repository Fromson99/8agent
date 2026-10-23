"""Read exact native records; separate entering a check from cancelling a gap."""
from common import *
import sqlite3
out=ART/'known-query/candidate';trace=[]
def expand(value):
 if isinstance(value,dict) and 'table_rows' in value:return [dict(zip(value['table_columns'],r)) for r in value['table_rows']]
 return value
for p in sorted((out/'model').glob('call-*/request.json')):
 request=read(p);view={};value={}
 for m in request.get('messages',[]):
  if m.get('role')=='user':
   try:view=json.loads(m['content']).get('view',{})
   except (ValueError,AttributeError):pass
 raw=read(p.with_name('response.json')) if p.with_name('response.json').exists() else {}
 try:value=json.loads(raw['choices'][0]['message']['content'])
 except (KeyError,IndexError,ValueError):pass
 options=expand(view.get('tool_options',[]))
 row={'call':p.parent.name,'phase':view.get('source_stage',view.get('phase')),'input_gaps':expand(view.get('assessment_gaps',[])),
 'previous_assessments_present':bool(view.get('previous_assessments')),'source_headings':[s.get('heading') for s in expand(view.get('sources',[])) if isinstance(s,dict)],
 'choice':value.get('choice'),'target':value.get('target'),'target_options':[o for o in options if isinstance(o,dict) and o.get('target')==value.get('target')],
 'decision':{k:v for k,v in value.items() if k not in ('claims','issue_assessments','gaps')},
 'claims':len(value.get('claims',[])),'issue_assessments':value.get('issue_assessments',[]),'gaps':value.get('gaps',[]),'provider_error':raw.get('error'),
 'system_chars':sum(len(m.get('content','')) for m in request.get('messages',[]) if m.get('role')=='system')}
 trace.append(row)
events=[]
for p in (out/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'):
 with sqlite3.connect(p) as db:
  for seq,kind,payload in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq'):
   if kind in ('ASSESSMENT_GAP_REENTRY_PLANNED','ASSESSMENT_GAP_REPEATED','INVESTIGATION_BOUNDED_STOP','ACQUIRED_ORIGINALS_TO_ASSESS','UNIT_READ_CHOICE','UNIT_READ_FINISHED','DIRECT_SEARCH_SCOPE_BOUND','GAP_ROUND_OPENED','GAP_ROUND_CLOSED','LAW_DECISION_REJECTED','LAW_DECISION_ACCEPTED') or ('GAP' in kind and 'MODEL' not in kind):
    events.append({'seq':seq,'kind':kind,'payload':json.loads(payload)})
result=read(out/'result.json') if (out/'result.json').exists() else {}
response=read(out/'response.json') if (out/'response.json').exists() else {};b=response.get('body',{});agent=b.get('assembly',{}).get('term_agent',{})
report={'native_result':result,'service_status':response.get('status'),'answer':b.get('answer',{}).get('text'),'outcome':agent.get('accepted_outcome'),'citation_integrity':agent.get('citation_integrity'),'trace':trace,'events':events}
save(ART/'observations.json',report)
for row in trace:print(json.dumps({k:row[k] for k in ('call','phase','choice','decision','claims','issue_assessments','gaps')},ensure_ascii=False))
print(json.dumps({'service_status':report['service_status'],'calls':result.get('model_calls'),'seconds':result.get('seconds'),'outcome':report['outcome']},ensure_ascii=False))
