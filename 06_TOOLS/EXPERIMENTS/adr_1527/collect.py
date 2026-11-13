"""ADR-1527 summary: per arm time, calls, cost, groups; per group the pick and the table rows; expected external
articles in a row with their internal article (row level) or in the same group table, by script."""
from common import *
import sys
S=ROOT/read(DES/'code-candidate.json')['code_root']
sys.path[:0]=[str(S/'02_BACKEND'),str(S)]
from workflow.runtime import _saved_state
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
    row.update({k:r.get(k) for k in ('http_status','status','stop_code','request_seconds','model_seconds','cpu_seconds',
                                     'physical_calls','unknown','generations','rejected_generations','duplicate','embedding_calls')})
    row['switched']=sum(c.get('status')=='switched' for c in calls)
    row['reported_cost_usd']=round(sum((c.get('usage') or {}).get('cost',0) or 0 for c in calls),4)
    row['groups']={k:doc.get(k) for k in ('groups_total','groups_finished','groups_held','groups_waiting')}
    stage_calls={}
    for g in read(base/'generations.json'):stage_calls[g['stage']]=stage_calls.get(g['stage'],0)+1
    row['calls_by_stage']=stage_calls
    groups=[];hits=[];verdicts={};unpaired=0;compared=0
    for g in doc.get('group_runs') or []:
        st=json.loads(dict(_saved_state(base/'runtime'/'workflows'/g['run_id']/'journal.sqlite'))['checkpoint_json'])
        res=json.loads(dict(_saved_state(base/'runtime'/'workflows'/g['run_id']/'journal.sqlite'))['result_json'] or '{}')
        table=(res.get('comparison_table') or {}).get('rows',[])
        for t in table:
            v=[o['verdict_label'] for o in t.get('opinions',[])]
            for x in v:verdicts[x]=verdicts.get(x,0)+1
            if t.get('placement')=='UNPAIRED':unpaired+=1
            elif any(not x.startswith(('짝 미정','미비 후보')) for x in v):compared+=1
        pick=st.get('external_pick') or {}
        groups.append({'title':g['title'],'status':g['status'],'result_status':g.get('result_status'),'seconds':g.get('seconds'),'model_calls':g.get('model_calls'),
                       'vector':(pick.get('vector') or {}).get('status'),'read':pick.get('read'),'pick_failed':pick.get('pick_failed'),
                       'picks':pick.get('picks'),'rows':len(table),'stopped_at':st.get('stopped_at')})
        for target in grades[cid]['targets']:
            for want in target['external']:
                rowhit=[t['label'] for t in table if t.get('placement')!='UNPAIRED' and any(target['internal'] in (s.get('coordinate_label') or '') for s in t.get('internal',[]))
                        and any(want in ((s.get('coordinate_label') or '')+' '+(s.get('document_name') or '')) for s in t.get('external',[]))]
                intable=any(want in ((s.get('coordinate_label') or '')+' '+(s.get('document_name') or '')) for t in table for s in t.get('external',[]))
                internal_here=any(target['internal'] in (s.get('coordinate_label') or '') for t in table for s in t.get('internal',[]))
                if internal_here:hits.append({'internal':target['internal'],'external':want,'same_row':rowhit[:3],'same_table':intable})
    row['groups_detail']=groups;row['targets']=hits
    row['targets_same_row']=sum(bool(h['same_row']) for h in hits);row['targets_same_table']=sum(h['same_table'] for h in hits)
    row['verdicts']=verdicts;row['unpaired_rows']=unpaired;row['compared_rows']=compared
    final=read(base/'resource-final.json') if (base/'resource-final.json').exists() else {}
    row['peak_rss_GiB']=round(final.get('peak_rss_KiB',0)/1048576,2);row['code_unchanged']=final.get('code_unchanged')
    out[cid]=row
put(ART/'summary.json',out)
for cid,row in out.items():
    print('==',cid,{k:row.get(k) for k in ('http_status','status','request_seconds','physical_calls','reported_cost_usd','groups','targets_same_row','targets_same_table','compared_rows','unpaired_rows')})
