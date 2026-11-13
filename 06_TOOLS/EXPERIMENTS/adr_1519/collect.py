"""ADR-1519 offline collection (grading targets never enter product input).

Per arm and case: the counted folder (the rerun when the first run had a provider failure), HTTP status, status,
physical calls, unknown/blank/429, model vs non-model seconds, process CPU seconds, duplicate-request check, and
the comparison table: rows, rows with both sides, verdict labels, failure points, read originals left out of
every row (unreviewed_originals, same definition on both arms). Target grading: a target (document + article)
is "in the table" when a row's source on its side has that document name and that article label in its heading
(exact label: 제3-24조 does not match 제3-24조의4); article None = any row source of that document.
Writes artifacts/summary.json and prints a short table."""
from common import *
import re
from collections import Counter
ART_RE=re.compile(r'제\d+(?:-\d+)?조(?:의\d+)?')
def hit(src,t):
    if t['document'] not in (src.get('document') or ''):return False
    return t.get('article') is None or t['article'] in ART_RE.findall(src.get('heading') or '')
def counted(arm,cid):
    q=ART/'live'/arm/cid;r=ART/'live'/arm/(cid+'-rerun')
    if r.is_dir() and ((r/'result.json').exists() or not (q/'result.json').exists()):return r,True
    return q,False
def collect():
    grades={g['id']:g for g in read(DES/'grading-only.json')};rows=[]
    for cell in read(DES/'cells.json'):
        cid,arm=cell['case'],cell['arm'];folder,rerun=counted(arm,cid)
        if not folder.is_dir():rows.append({'case_id':cid,'arm':arm,'state':'NOT_RUN'});continue
        calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
        res=read(folder/'result.json') if (folder/'result.json').exists() else {}
        t=(res.get('turns') or [{}])[-1]
        row={'case_id':cid,'arm':arm,'rerun':rerun,
             'state':'ANSWERED' if t.get('http_status')==200 else ('HTTP_'+str(t['http_status']) if t.get('http_status') else
                     ('RESOURCE_STOP' if (folder/'resource-stop.json').exists() else 'RUNNER_FAILURE' if (folder/'runner-failure.json').exists() else 'INCOMPLETE')),
             **{k:t.get(k) for k in ('http_status','status','error_code','message','request_seconds','model_seconds','non_model_seconds','cpu_seconds',
                                     'generations','rejected_generations','duplicate','answer_chars','sides','questions','concepts','failure_points')},
             'physical_calls':len(calls),'unknown':sum(c['status'] in ('unknown','started') for c in calls),'blank':sum(bool(c.get('blank')) for c in calls),
             'http429':sum(c.get('http_status')==429 for c in calls),'switched':sum(c['status']=='switched' for c in calls),
             'switch_kinds':dict(Counter(str(c.get('failure')) for c in calls if c['status']=='switched')),
             'answered_by':dict(Counter(str(c.get('actual_provider')) for c in calls if c['status']=='responded')),'cost':round(sum((c.get('usage') or {}).get('cost',0) or 0 for c in calls),5),
             'stages':dict(Counter(str(c.get('stage')) for c in calls)),
             'unknown_stages':[c.get('stage') for c in calls if c['status'] in ('unknown','started')],
             'runner_failure':(read(folder/'runner-failure.json').get('error')[:300] if (folder/'runner-failure.json').exists() else None)}
        table=t.get('table') or {}
        trs=table.get('rows',[]);unrev=table.get('unreviewed',[])
        row.update(table_rows=len(trs),both_sides=sum(1 for r in trs if r['internal'] and r['external']),
                   internal_only=sum(1 for r in trs if r['internal'] and not r['external']),external_only=sum(1 for r in trs if r['external'] and not r['internal']),
                   verdicts=dict(Counter(v for r in trs for v in r['verdicts'])),
                   external_sources_in_table=len({(s['document'],s['heading']) for r in trs for s in r['external']}),
                   internal_sources_in_table=len({(s['document'],s['heading']) for r in trs for s in r['internal']}),
                   unplaced_external=sum(1 for s in unrev if s['side']=='external'),unplaced_internal=sum(1 for s in unrev if s['side']=='internal'),
                   table=trs,unreviewed=unrev)
        text=(folder/'turn-1/answer.txt').read_text() if (folder/'turn-1/answer.txt').exists() else ''
        row['targets']=[{**g,'in_table':any(hit(s,g) for r in trs for s in r[g['side']]),
                         'read_not_placed':any(s['side']==g['side'] and hit(s,g) for s in unrev),
                         'in_answer_text':g['document'] in text and (g.get('article') is None or g['article'] in text)} for g in grades[cid]['targets']]
        rows.append(row)
    return rows
def summarize(rows):
    out={}
    for arm in ('baseline','candidate'):
        rs=[r for r in rows if r['arm']==arm and r['state']!='NOT_RUN']
        out[arm]={'cells':len(rs),'states':dict(Counter(r['state'] for r in rs)),'statuses':dict(Counter(str(r.get('status')) for r in rs)),
                  'targets_total':sum(len(r['targets']) for r in rs),'targets_in_table':sum(x['in_table'] for r in rs for x in r['targets']),
                  'targets_read_not_placed':sum(x['read_not_placed'] and not x['in_table'] for r in rs for x in r['targets']),
                  'unplaced_external':sum(r['unplaced_external'] for r in rs),'table_rows':sum(r['table_rows'] for r in rs),
                  'both_sides_rows':sum(r['both_sides'] for r in rs),'physical_calls':sum(r['physical_calls'] for r in rs),
                  'unknown':sum(r['unknown'] for r in rs),'blank':sum(r['blank'] for r in rs),'http429':sum(r['http429'] for r in rs),
                  'cost':round(sum(r['cost'] for r in rs),4),'request_seconds':round(sum(r.get('request_seconds') or 0 for r in rs),1),
                  'non_model_seconds':round(sum(r.get('non_model_seconds') or 0 for r in rs),1),'cpu_seconds':round(sum(r.get('cpu_seconds') or 0 for r in rs),1),
                  'duplicate_extra_calls':sum((r.get('duplicate') or {}).get('extra_model_calls',0) or 0 for r in rs),
                  'reruns':sum(r['rerun'] for r in rs)}
    return out
if __name__=='__main__':
    rows=collect();s=summarize(rows)
    put(ART/'summary.json',{'rows':rows,'by_arm':s,'grading_input_is_offline_only':True,'semantic_grades_automatically_generated':False})
    print(json.dumps(s,ensure_ascii=False,indent=1))
    for r in rows:
        if r['state']=='NOT_RUN':print(r['case_id'],r['arm'],'NOT_RUN');continue
        print(r['case_id'],r['arm'],r['state'],r.get('status'),r.get('error_code') or '','calls',r['physical_calls'],'unk',r['unknown'],
              's',r.get('request_seconds') and round(r['request_seconds']),'nm',r.get('non_model_seconds') and round(r['non_model_seconds']),
              'rows',r['table_rows'],'both',r['both_sides'],'unplacedExt',r['unplaced_external'],
              'targets',[('O' if x['in_table'] else 'R' if x['read_not_placed'] else 'X')+':'+x['document'][:6]+(x.get('article') or '') for x in r['targets']])
