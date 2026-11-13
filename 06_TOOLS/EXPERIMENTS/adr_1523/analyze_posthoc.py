"""ADR-1523 analysis (frozen before the run; the ADR-1507 post-hoc counts, now pre-registered; no model calls).

Per cell: external articles (document, heading) read but in no table row, rows with a comparison verdict, rows with both
sides, STOP failure point stage, pairing calls and their input chars. Prints the ADR-1507/1508/1510 rows of the same questions next
to these (earlier run, read from that ADR's frozen posthoc-analysis.json)."""
from common import *
from collections import Counter
def key(s):return ((s.get('document') or '').split(' > ')[-1],(s.get('heading') or '').split('(')[0][:40])
out=[]
for cell in read(DES/'cells.json'):
    arm,cid=cell['arm'],cell['case']
    folder=ART/'live'/arm/(cid+'-rerun') if (ART/'live'/arm/(cid+'-rerun')/'result.json').exists() else ART/'live'/arm/cid
    t=read(folder/'turn-1/result.json');rows=t['table']['rows']
    inrow={side:{key(s) for r in rows if r.get('placement')!='UNPAIRED' for s in r[side]} for side in ('internal','external')}
    unrev={side:{key(s) for s in t['table']['unreviewed'] if s['side']==side} for side in ('internal','external')}
    out.append({'case':cid,'arm':arm,'counted':folder.name,'rows':len(rows),'both_sides':sum(1 for r in rows if r['internal'] and r['external']),
                'rows_with_verdict':sum(1 for r in rows if r['verdicts'] and r.get('placement')!='UNPAIRED'),'verdicts':dict(Counter(v for r in rows for v in r['verdicts'])),
                'external_articles_in_table':len(inrow['external']),'internal_articles_in_table':len(inrow['internal']),
                'external_articles_read_not_in_any_row':sorted('%s %s'%k for k in unrev['external']-inrow['external']),
                'unplaced_card':[p['title'] for p in t['failure_points'] if p['kind']=='UNPLACED'],
                'stop':[(p.get('stage'),p['title']) for p in t['failure_points'] if p['kind']=='STOP'],
                'calls':t['physical_calls'],'seconds':t['request_seconds'],'non_model_seconds':t['non_model_seconds'],
                'pairing_calls':[{'number':g['number'],'status':g.get('status'),'input_chars':len(json.dumps(read(folder/'canonical'/('%03d.json.gz'%g['number']))['view'],ensure_ascii=False))}
                                 for g in read(folder/'generations.json') if g['stage']=='workflow-concepts'],
                'stages':sorted({g['stage'] for g in read(folder/'generations.json') if g['stage'].startswith('workflow')}),
                'comparison_rows':sum(1 for r in rows if r.get('placement')!='UNPAIRED' and any(not v.startswith('미비 후보') for v in r['verdicts'])),
                'unpaired_rows':sum(1 for r in rows if r.get('placement')=='UNPAIRED'),
                'unpaired_card':next((p['title'] for p in t['failure_points'] if p['kind']=='UNPLACED'),None),
                'pair_skips':t.get('pair_skips'),
                'budget':t.get('budget'),
                'followups':sum(1 for g in read(folder/'generations.json') if g['stage']=='source-request-route'),
                'first_compare_call':min((g['number'] for g in read(folder/'generations.json') if g['stage']=='workflow-compare'),default=None),
                'item_research_reads_held_for_comparison':json.dumps(t['failure_points'],ensure_ascii=False).count('비교할 몫을 남기려고'),
                'held_for_time':json.dumps(t['failure_points'],ensure_ascii=False).count('비교할 시간을 남기려고'),
                'items_held_by_share':json.dumps(t['failure_points'],ensure_ascii=False).count('비교에 쓸 몫(호출·시간)을 남기려고'),
                'calls_by_stage':dict(Counter(g['stage'] for g in read(folder/'generations.json'))),
                'provider_switches':[(c['number'],c.get('provider_name'),c.get('failure')) for c in read(folder/'calls.json') if c['status']=='switched'],
                'duplicate':t.get('duplicate')})
put(ART/'posthoc-analysis.json',{'rows':out,'note':__doc__})
for adr in ('ADR-1515-compare-r5-provider-fallback-qwen','ADR-1520-compare-r8-call-limit-applied-qwen','ADR-1521-compare-r9-review-limit-skip-qwen'):
  for r in read(ROOT/'04_EXPERIMENTS/ADR'/adr/'artifacts/posthoc-analysis.json')['rows']:
    print(adr[:8],r['case'],r['arm'],'rows',r['rows'],'unpaired',r.get('unpaired_rows'),'both',r['both_sides'],'verdictRows',r['rows_with_verdict'],'cmpRows',r.get('comparison_rows'),'calls',r.get('calls'),'stopAt',r.get('stop'),'extReadNotInRow',len(r['external_articles_read_not_in_any_row']),'stop',r['stop'])
for r in out:
    print(r['case'],r['arm'],'budget',r['budget'],'rows',r['rows'],'unpairedRows',r['unpaired_rows'],r['unpaired_card'],'pairSkips',r['pair_skips'],'both',r['both_sides'],'verdictRows',r['rows_with_verdict'],'cmpRows',r['comparison_rows'],'firstCompareCall',r['first_compare_call'],'held',r['item_research_reads_held_for_comparison'],'heldTime',r['held_for_time'],'itemsHeld',r['items_held_by_share'],'byStage',r['calls_by_stage'],'switches',r['provider_switches'],r['verdicts'],'extInTable',r['external_articles_in_table'],
          'extReadNotInRow',len(r['external_articles_read_not_in_any_row']),r['external_articles_read_not_in_any_row'],'stop',r['stop'],r['unplaced_card'])
