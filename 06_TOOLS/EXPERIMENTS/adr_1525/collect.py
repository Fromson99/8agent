"""ADR-1525 summary after the cells: per case time, groups, calls, cost, the target pairs of doc-liquidity by script."""
from common import *
import re
out={}
grades={g['id']:g for g in read(DES/'grading-only.json')}
for case in read(DES/'cases.json'):
    cid=case['id'];base=ART/'live/candidate'/cid
    row={'ran':(base/'turn-1/result.json').exists()}
    for name in ('runner-failure.json','resource-stop.json','STOP_EXTERNAL.json'):
        if (base/name).exists():row[name]=read(base/name)
    if not row['ran']:
        out[cid]=row;continue
    r=read(base/'turn-1/result.json');calls=read(base/'calls.json') if (base/'calls.json').exists() else []
    doc=r.get('document') or {}
    row.update({k:r.get(k) for k in ('http_status','status','stop_code','resume_available','request_seconds','model_seconds','non_model_seconds','cpu_seconds',
                                     'physical_calls','unknown','blank','http429','generations','rejected_generations','duplicate','threads')})
    row['switched']=sum(c.get('status')=='switched' for c in calls)
    row['reported_cost_usd']=round(sum((c.get('usage') or {}).get('cost',0) or 0 for c in calls),4)
    row['groups']={k:doc.get(k) for k in ('groups_total','groups_finished','groups_held','groups_waiting')}
    runs=doc.get('group_runs') or []
    row['group_runs']=[{k:g.get(k) for k in ('title','status','result_status','rows','verdicts','model_calls','seconds','reason')} for g in runs]
    verdicts={}
    for g in runs:
        for label,n in (g.get('verdicts') or {}).items():verdicts[label]=verdicts.get(label,0)+n
    row['verdicts']=verdicts
    text=(base/'turn-1/answer.txt').read_text()
    sections=re.split(r'<h3>',text)[1:]
    found=[]
    for t in grades[cid]['targets']:
        hit=[n for n,sec in enumerate(sections) if t['internal']['article'] in sec and t['external']['article'] in sec and t['external']['document'] in sec]
        found.append({'target':t,'same_group_sections':hit})
    row['targets']=found;row['targets_found']=sum(bool(f['same_group_sections']) for f in found)
    final=read(base/'resource-final.json') if (base/'resource-final.json').exists() else {}
    row['peak_rss_GiB']=round(final.get('peak_rss_KiB',0)/1048576,2);row['code_unchanged']=final.get('code_unchanged')
    out[cid]=row
put(ART/'summary.json',out)
print(json.dumps(out,ensure_ascii=False,indent=1)[:6000])
