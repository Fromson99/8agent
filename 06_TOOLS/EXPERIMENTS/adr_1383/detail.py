"""Read the final answer, wire-level scenario identity and claim sources separately."""
from common import *
import sqlite3
audit=read(ART/'source-wire-audit.json')
inspected={r['case_id']:r for r in read(ART/'usage-inspection.json')['rows']}
scenario=read(DES/'legacy365-context.json')['scenario_package']
rows=[]
for cell in audit['cells']:
    case=cell['case_id'];row=inspected[case]
    d=ART/'usage-live'/(case+'-'+cell['arm'])
    body=read(d/'turn-1/response.json.gz')['body'];term=body.get('assembly',{}).get('term_agent',{})
    term=term if isinstance(term,dict) else {}
    report=term.get('review_explanation') or {}
    contexts={s['id']:s for s in body.get('assembly',{}).get('context',[]) if 'id' in s}
    claim_records=[]
    for claim in (body.get('answer') or {}).get('claims',[]):
        claim_records.append({'text':claim['text'],'sources':[{'id':ref,'document_id':contexts[ref]['document_id'],'text':contexts[ref]['text']} for ref in claim['source_ids']]})
    packages=[b for b in cell['wire_ontology_inputs'] if b.get('payload',{}).get('bundle_id')==scenario['bundle_id'] and b['payload'].get('scenario_catalog',{}).get('package_sha256')==scenario['package_sha256']]
    if cell['arm']=='baseline':assert not cell['wire_ontology_inputs']
    repairs=[]
    for p in sorted((d/'canonical').glob('???.json.gz')):
        view=read(p)['view'];fb=view.get('repair_feedback',{})
        if fb:repairs.append({'stage':view.get('source_stage'), 'errors':fb.get('errors'),'validation':fb.get('validation')})
    decisions=[]
    for journal in (d/'runtime').rglob('journal.sqlite'):
        with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
            decisions.extend(json.loads(payload) for payload, in db.execute("SELECT payload_json FROM event WHERE kind='COMPLETION_ASSESSMENT_REJECTED' ORDER BY seq"))
    row['assessment_rejections']=decisions
    gens=read(d/'generations.json') if (d/'generations.json').is_file() else []
    calls=read(d/'calls.json') if (d/'calls.json').is_file() else []
    row.update(http_status=read(d/'turn-1/result.json')['http_status'],claim_records=claim_records,scenario_deliveries=len(packages),
        scenario_statuses=[b.get('status') for b in packages],scenario_review=report.get('scenario_review'),failed_checks=report.get('failed_checks'),
        repairs=repairs,rejected_stages=[g for g in gens if g.get('status')=='rejected'],
        providers=sorted({str(c.get('actual_provider')) for c in calls if c.get('actual_provider')}),
        final_review_policy=(body.get('answer',{}).get('provider_receipt') or {}).get('final_review_policy'),
        model_attempts=cell['attempts'])
    rows.append(row)
put(ART/'answer-evidence.json',{'rows':rows})
for row in rows:
    print(row['case_id'],row['http_status'],row['claims'],row['matching_inputs'],row['scenario_deliveries'],row['adoption_statuses'],round(row['request_seconds'],1),row['answer'][:650])
    print('REPAIR',[(x['stage'],str(x['errors'])[:200]) for x in row['repairs']])
