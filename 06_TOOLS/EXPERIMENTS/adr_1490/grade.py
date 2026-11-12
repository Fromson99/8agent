"""Offline per-turn branch grading of ADR-1489/1490 cells against the frozen expectations (no model calls)."""
from common import *
import re, gzip
A89 = ROOT/'04_EXPERIMENTS/ADR/ADR-1489-multiturn-reply-loosen-qwen-r2/artifacts/live'
A57 = ROOT/'04_EXPERIMENTS/ADR/ADR-1457-multiturn-followups-r15-qwen/artifacts/public-live/run-1'
cases = {c['id']: c for c in read(DES/'live-cases.json')}
cases.update({c['id']: c for c in read(ROOT/'04_EXPERIMENTS/ADR/ADR-1489-multiturn-reply-loosen-qwen-r2/artifacts/design/live-cases.json')})
def grade(cell, cid):
    rows = []; created = {}
    if not (cell/'result.json').exists(): return rows
    turns = read(cell/'result.json')['turns']; case = cases[cid]
    for t in turns:
        n = t['step']['number']; exp = next(s['expect'] for s in case['steps'] if s['number'] == n)
        text = (cell/('turn-'+str(n))/'answer.txt').read_text() if (cell/('turn-'+str(n))/'answer.txt').exists() else ''
        goal, method, status = t.get('goal_id'), t.get('method'), t.get('status')
        new_goal = goal is not None and goal not in created.values() and method == 'CASE_START'
        good = (exp == 'any' or (exp in ('new',) or exp.startswith('background')) and new_goal and status in ('READY', 'REUSED')
                or exp.startswith('continue:') and goal is not None and goal == created.get(int(exp.split(':')[1])) and status in ('READY', 'REUSED')
                or exp == 'ask' and status == 'CLARIFY' and bool(re.search(r'\d+번째 (질문|“)', text)))
        if goal is not None and n not in created: created[n] = goal
        rows.append({'case': cid, 'turn': n, 'q': t['step']['question'][:34], 'expect': exp, 'status': status, 'method': method, 'http': t['http_status'], 'verdict': 'TURN1' if n == 1 else ('PASS' if good else 'FAIL'),
                     'conflict': '판단이 엇갈려' in text, 'seconds': round(t['request_seconds']), 'calls': t['physical_calls'], 'text': text[:150].replace('\n', ' ')})
    planned = [s['number'] for s in case['steps']]
    for n in planned[len(turns):]: rows.append({'case': cid, 'turn': n, 'expect': next(s['expect'] for s in case['steps'] if s['number'] == n), 'verdict': 'NOT_RUN'})
    return rows
out = {}
arms = [('1490-final', ART/'live', 'candidate'), ('1489-candidate', A89, 'candidate'), ('1489-baseline-MAIN203', A89, 'baseline'), ('1457-r15', A57, 'candidate')]
for name, folder, suffix in arms:
    rows = [r for cid in cases for r in grade(folder/(cid+'-'+suffix), cid)]
    out[name] = {'pass': sum(r['verdict'] == 'PASS' for r in rows), 'fail': sum(r['verdict'] == 'FAIL' for r in rows), 'not_run': sum(r['verdict'] == 'NOT_RUN' for r in rows), 'conflict': sum(bool(r.get('conflict')) for r in rows), 'rows': rows}
calls = [c for p in (ART/'live').glob('*/calls.json') for c in read(p)]
out['calls_1490'] = {'physical': len(calls), 'unknown': sum(c['status'] != 'responded' for c in calls), 'http429': sum(c.get('http_status') == 429 for c in calls), 'cost': round(sum((c.get('usage') or {}).get('cost', 0) or 0 for c in calls), 4)}
calls = [c for p in A89.glob('*/calls.json') for c in read(p)]
out['calls_1489'] = {'physical': len(calls), 'unknown': sum(c['status'] != 'responded' for c in calls), 'http429': sum(c.get('http_status') == 429 for c in calls), 'cost': round(sum((c.get('usage') or {}).get('cost', 0) or 0 for c in calls), 4)}
put(ART/'grade.json', out)
for name in out:
    if not name.startswith('calls'):
        print('#', name, {k: out[name][k] for k in ('pass', 'fail', 'not_run', 'conflict')})
        for r in out[name]['rows']:
            if r['verdict'] in ('FAIL', 'NOT_RUN') or (name == '1490-final' and r['verdict'] != 'TURN1') or r.get('conflict'):
                print('  ', r['case'][:20].ljust(20), r['turn'], str(r.get('expect')).ljust(12), str(r.get('status')).ljust(8), str(r.get('method')).ljust(16), r['verdict'], r.get('seconds'), r.get('text', '')[:70])
print(out['calls_1490'], out['calls_1489'])
