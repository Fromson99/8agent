"""ADR-1508 analysis (frozen before the run; the ADR-1507 post-hoc counts, now pre-registered; no model calls).

Per cell: external articles (document, heading) read but in no table row, rows with a comparison verdict, rows with both
sides, STOP failure point stage, pairing calls and their input chars. Prints the ADR-1507 rows of the same questions next
to these (earlier run, read from that ADR's frozen posthoc-analysis.json)."""
from common import *
from collections import Counter
def key(s):return ((s.get('document') or '').split(' > ')[-1],(s.get('heading') or '').split('(')[0][:40])
out=[]
for cell in read(DES/'cells.json'):
    arm,cid=cell['arm'],cell['case']
    folder=ART/'live'/arm/(cid+'-rerun') if (ART/'live'/arm/(cid+'-rerun')/'result.json').exists() else ART/'live'/arm/cid
    t=read(folder/'turn-1/result.json');rows=t['table']['rows']
    inrow={side:{key(s) for r in rows for s in r[side]} for side in ('internal','external')}
    unrev={side:{key(s) for s in t['table']['unreviewed'] if s['side']==side} for side in ('internal','external')}
    out.append({'case':cid,'arm':arm,'counted':folder.name,'rows':len(rows),'both_sides':sum(1 for r in rows if r['internal'] and r['external']),
                'rows_with_verdict':sum(1 for r in rows if r['verdicts']),'verdicts':dict(Counter(v for r in rows for v in r['verdicts'])),
                'external_articles_in_table':len(inrow['external']),'internal_articles_in_table':len(inrow['internal']),
                'external_articles_read_not_in_any_row':sorted('%s %s'%k for k in unrev['external']-inrow['external']),
                'unplaced_card':[p['title'] for p in t['failure_points'] if p['kind']=='UNPLACED'],
                'stop':[(p.get('stage'),p['title']) for p in t['failure_points'] if p['kind']=='STOP'],
                'calls':t['physical_calls'],'seconds':t['request_seconds'],'non_model_seconds':t['non_model_seconds'],
                'pairing_calls':[{'number':g['number'],'status':g.get('status'),'input_chars':len(json.dumps(read(folder/'canonical'/('%03d.json.gz'%g['number']))['view'],ensure_ascii=False))}
                                 for g in read(folder/'generations.json') if g['stage']=='workflow-concepts'],
                'stages':sorted({g['stage'] for g in read(folder/'generations.json') if g['stage'].startswith('workflow')})})
put(ART/'posthoc-analysis.json',{'rows':out,'note':__doc__})
prev=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1507-compare-general-flow-qwen/artifacts/posthoc-analysis.json')['rows']
for r in prev:
    print('ADR-1507',r['case'],r['arm'],'rows',r['rows'],'both',r['both_sides'],'verdictRows',r['rows_with_verdict'],'extReadNotInRow',len(r['external_articles_read_not_in_any_row']),'stop',r['stop'])
for r in out:
    print(r['case'],r['arm'],'rows',r['rows'],'both',r['both_sides'],'verdictRows',r['rows_with_verdict'],r['verdicts'],'extInTable',r['external_articles_in_table'],
          'extReadNotInRow',len(r['external_articles_read_not_in_any_row']),r['external_articles_read_not_in_any_row'],'stop',r['stop'],r['unplaced_card'])
