from common import *
T=ROOT/'06_TOOLS/EXPERIMENTS/adr_1230'
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1228/audit.py').read_text()
s=s.replace("if row['normalization']=='SAVED':", "if row['normalization']=='REUSED_VERIFIED':")
a=s.index("  attempts=[i for i,s in enumerate(x['stage_receipts'],1) if s['phase']=='normalize-'")
z=s.index("  normalizations.append",a)
s=s[:a]+"""  prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1228-source-first-authoring-live/artifacts/live'
  previous=read(prior/f'{case}-normalized.json')['normalized'];assert previous==n
  canonical=n['proposal'];receipt=n['model_receipt']['normalization_assembly']
"""+s[z:]
s=s.replace("'within_budget':x['calls']<=9", "'within_budget':x['calls']<=4 and read(DES/'continuation.json')['previous_physical_calls']+x['calls']<=9, 'prior_unchanged':all(sha(ROOT/n)==h for n,h in read(DES/'continuation.json')['files'].items())")
(T/'audit.py').write_text(s)
print('Continuation audit prepared')
