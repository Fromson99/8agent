"""ADR-1507 post-hoc analysis (added after the run, not frozen; same raw results, no model calls).

The frozen collect.py counts unreviewed_originals entries, which are sentence pieces (spans), and includes pieces
of articles that are already in a table row. Here: unique (document, article heading) per side, and the external
articles read but in no table row at all. Also: rows with a comparison verdict, rows with both sides."""
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
                'calls':t['physical_calls'],'seconds':t['request_seconds'],'non_model_seconds':t['non_model_seconds']})
put(ART/'posthoc-analysis.json',{'rows':out,'note':__doc__})
for r in out:
    print(r['case'],r['arm'],'rows',r['rows'],'both',r['both_sides'],'verdictRows',r['rows_with_verdict'],r['verdicts'],'extInTable',r['external_articles_in_table'],
          'extReadNotInRow',len(r['external_articles_read_not_in_any_row']),r['external_articles_read_not_in_any_row'],'stop',r['stop'],r['unplaced_card'])
