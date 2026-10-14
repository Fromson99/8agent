from pathlib import Path
R=Path(__file__).resolve().parents[3]
s=(R/'06_TOOLS/EXPERIMENTS/adr_0707/analyze.py').read_text()
s=s.replace('ADR-0707-grounded-law-title-entry','ADR-0708-grounded-title-body-retest')
s=s.replace("f['codes']['baseline']","f['codes']['body-retest']")
s=s.replace("('baseline','title-entry')","('body-retest',)")
a=s.index('for case in dataset[\'cases\']:',s.index('pairs=[]'));b=s.index('by_arm={}',a);s=s[:a]+s[b:]
s=s.replace("  for u in r['usage']:\n   phase=u['phase'];", "  usage={u['call']:u for u in r['usage']}\n  for attempt in r['attempts']:\n   u={**usage.get(attempt['call'],{}),'seconds':attempt['seconds']};phase=attempt['phase'];")
s=s.replace("model_seconds=sum(u['seconds'] for u in r['usage'])", "model_seconds=sum(u['seconds'] for u in r['attempts'])")
s=s.replace("attempt_count_matches=len(r['attempts'])==r['model_calls']==len(r['usage'])", "attempt_count_matches=len(r['attempts'])==r['model_calls'] and len(r['usage'])==sum(a['status']=='completed' for a in r['attempts'])")
s=s.replace('Three known public questions, one run each; no population speed or accuracy claim','One frozen identical-code retry after upstream429; no speed comparison or accuracy claim')
s=s.replace('Three distinct known questions, one observation each','One public question, one observation; failed usage unknown')
(R/'06_TOOLS/EXPERIMENTS/adr_0708/analyze.py').write_text(s)
