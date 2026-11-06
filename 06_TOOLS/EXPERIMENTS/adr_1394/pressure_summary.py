"""Summarize measured WSL pressure for each completed run from its raw samples."""
import gzip
import json
from common import ART, put, read

rows = []
for cell in sorted((ART/'public-live').glob('*')):
    baseline = read(cell/'resource-baseline.json')
    samples = [baseline]
    with gzip.open(cell/'resource-samples.jsonl.gz','rt') as stream:
        for line in stream:
            samples.append(json.loads(line))
    final = read(cell/'resource-final.json')
    samples.append(final['sample'])
    rows.append({
        'cell':cell.name,
        'samples':len(samples),
        'baseline_swap_used_bytes':baseline['swap_used'],
        'peak_swap_growth_bytes':max(s['swap_used']-baseline['swap_used'] for s in samples),
        'minimum_swap_free_bytes':min(s['swap_free'] for s in samples),
        'minimum_ram_available_bytes':min(s['available'] for s in samples),
        'peak_worker_rss_bytes':max(s['rss'] for s in samples),
        'resource_stop':(cell/'resource-stop.json').exists(),
        'system_wide_swap':True,
    })
put(ART/'pressure-summary.json',{'cells':rows,'configured_growth_limit_bytes':1024**3})
print(json.dumps(rows,ensure_ascii=False))
