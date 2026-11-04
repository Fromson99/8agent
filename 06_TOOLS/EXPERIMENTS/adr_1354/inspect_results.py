"""Read-only mechanical inspection; semantic scores are recorded separately."""
from common import *
from collections import Counter
rows=[]
for d in sorted((ART/'usage-live').glob('*')):
 if not (d/'result.json').exists():continue
 stages=[];targets=[];repairs=[]
 for p in sorted((d/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  v=read(p).get('view',{});c=v.get('read_judgments',{});cont=c.get('need_continuity',{})
  if cont:
   ts=[{k:t.get(k) for k in ('id','coordinate','acquisition_status','acquired','available_complete','available_evidence_refs')} for t in cont['targets']]
   targets.append({'call':p.name,'source_stage':v.get('source_stage'),'targets':ts})
  fb=v.get('repair_feedback') or {}
  if fb:repairs.append({'call':p.name,'validation':fb.get('validation')})
  out=p.with_name(p.name.replace('.json.gz','-output.json.gz'))
  if out.exists():
   value=read(out);review=value.get('read_judgment_review',{})
   if 'original_reviews' in review:
    stages.append({'call':p.name,'original_review_rows':len(review['original_reviews']),'dispositions':dict(Counter(r['disposition'] for r in review['original_reviews'].values())),'original_ids':[r['basis_refs'] for r in review['original_reviews'].values()]})
 body=read(d/'turn-1/response.json.gz')['body'];outcome=(body.get('assembly',{}).get('term_agent',{}).get('accepted_outcome') or {})
 row={'cell':d.name,'case_id':read(d/'result.json')['case_id'],'actual_result':read(d/'result.json'),'target_inputs':targets,'original_review_outputs':stages,'repair_feedback':repairs,'coverage':outcome.get('answer_coverage'),'disposition':outcome.get('disposition'),'incomplete_failure':outcome.get('model_proposal',{}).get('failure'),'body_keys':list(body)}
 rows.append(row)
 print(json.dumps({'cell':d.name,'coverage':row['coverage'],'disposition':row['disposition'],'result':row['actual_result'],'repair_codes':[i.get('code') for r in repairs for i in (r['validation'] or {}).get('issues',[])]},ensure_ascii=False))
put(ART/'actual-flow-inspection.json',{'cells':rows,'model_calls':0,'source':'Saved exact model inputs and outputs, no replay'})
b=ART/'build-live';build=read(b/'result.json');checks=[]
if (b/'statements.json').exists():
 statements=read(b/'statements.json');proposal=read(b/'proposal.json.gz');inputs=read(b/'canonical/001.json.gz')['context'];raw=read(b/'canonical/001-output.json.gz')
 materials=inputs['material_options'];kept={k:m for k,m in materials.items() if raw['selections'][k]['disposition']=='CONTENT'}
 assert len(kept)==len(statements)==len(proposal['operations'])
 for op in proposal['operations']:
  key=op['target'].removeprefix('@material_');assert op['value']['text']==kept[key]['text']
  checks.append({'material':key,'raw_id':kept[key]['raw_id'],'source_ref':kept[key]['source_ref'],'statement_sha256':digest_text(op['value']['text']) if False else hashlib.sha256(op['value']['text'].encode()).hexdigest(),'source_basis_count':len(op['value']['source_basis'])})
 phases=[]
 for p in sorted((b/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  v=read(p);ctx=v['context'];prior=(ctx.get('repair') or {}).get('previous') or {}
  phases.append({'call':p.name,'operation':ctx.get('operation'),'repair_error':prior.get('error')})
 put(ART/'build-mechanical-inspection.json',{'result':build,'selected_literal_checks':checks,'phases':phases,'new_model_calls':0,'semantic_accuracy_not_implied':True})
 print(json.dumps({'build':build,'selected_literal_checks':len(checks),'repairs':[p for p in phases if p['repair_error']]},ensure_ascii=False))
