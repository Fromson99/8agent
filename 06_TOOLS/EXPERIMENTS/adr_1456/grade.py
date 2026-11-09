"""Offline grading of ADR-1456 cells (candidate r14 x 2 runs, ADR-1454 MAIN176 baseline) against the frozen per-turn expectations (no model calls).

Usage: grade.py  -> writes artifacts/grade.json and prints a table
"""
from common import *
import re

cases = {c['id']: c for c in read(DES/'live-cases.json')}
BASE = ROOT/'04_EXPERIMENTS/ADR/ADR-1454-multiturn-branch-scenarios-r12-qwen/artifacts/public-live'
ARMS = [('candidate-run1', ART/'public-live/run-1', 'candidate'), ('candidate-run2', ART/'public-live/run-2', 'candidate'), ('baseline', BASE, 'baseline')]
rows = []; summary = {}
for arm, folder, suffix in ARMS:
    ok = total = 0
    for cid, case in cases.items():
        cell = folder/(cid+'-'+suffix)
        if not (cell/'result.json').exists():
            rows.append({'arm': arm, 'case': cid, 'turn': None, 'verdict': 'NOT_RUN'}); continue
        turns = read(cell/'result.json')['turns']
        created = {}
        for t in turns:
            n = t['step']['number']; exp = next(s['expect'] for s in case['steps'] if s['number'] == n)
            article = next(s['article'] for s in case['steps'] if s['number'] == n)
            text = (cell/('turn-'+str(n))/'answer.txt').read_text() if (cell/('turn-'+str(n))/'answer.txt').exists() else ''
            goal, method, status = t.get('goal_id'), t.get('method'), t.get('status')
            new_goal = goal is not None and goal not in created.values() and method == 'CASE_START'
            if exp == 'new': good = new_goal and status in ('READY', 'REUSED')
            elif exp.startswith('continue:'):
                good = goal is not None and goal == created.get(int(exp.split(':')[1])) and status in ('READY', 'REUSED')
            elif exp.startswith('background:'):
                good = new_goal and status in ('READY', 'REUSED')
            elif exp == 'ask':
                good = status == 'CLARIFY' and bool(re.search(r'\d+번째 (질문|“)', text))
            else: good = False
            if new_goal: created[n] = goal
            elif goal is not None and n not in created: created[n] = goal
            grade = n != 1
            if grade:
                total += 1; ok += bool(good)
            mention = None
            if article:
                nums = re.findall(r'제\d+조(?:의\d+)?', article)
                mention = all(x in text for x in nums) if nums else None
            rows.append({'arm': arm, 'case': cid, 'turn': n, 'question': t['step']['question'], 'expect': exp,
                         'status': status, 'method': method, 'goal': (goal or '')[:10], 'http': t['http_status'],
                         'seconds': round(t['request_seconds'], 1), 'calls': t['physical_calls'],
                         'verdict': ('PASS' if good else 'FAIL') if grade else 'TURN1', 'article_in_answer': mention,
                         'answer_chars': len(text)})
        if len(turns) < len(case['steps']):
            for s in case['steps'][len(turns):]:
                rows.append({'arm': arm, 'case': cid, 'turn': s['number'], 'expect': s['expect'], 'verdict': 'NOT_RUN'})
                if s['number'] != 1: total += 1
    summary[arm] = {'pass': ok, 'graded_turns': total}
stable = {}
for r in rows:
    if r['arm'].startswith('candidate') and r.get('verdict') in ('PASS', 'FAIL', 'NOT_RUN'):
        stable.setdefault((r['case'], r['turn']), []).append(r['verdict'])
summary['stable_both_runs'] = sum(all(v == 'PASS' for v in vs) and len(vs) == 2 for vs in stable.values())
summary['graded_turns_per_run'] = len(stable)
calls = {}
for arm, folder, suffix in ARMS:
    c = [x for p in folder.glob('*-'+suffix+'/calls.json') for x in read(p)]
    calls[arm] = {'physical': len(c), 'unknown': sum(x['status'] == 'unknown' for x in c),
                  'http429': sum(x.get('http_status') == 429 for x in c),
                  'reported_cost_usd': round(sum((x.get('usage') or {}).get('cost', 0) or 0 for x in c), 6)}
put(ART/'grade.json', {'summary': summary, 'calls': calls, 'rows': rows})
for r in rows:
    if r.get('verdict') != 'TURN1':
        print(r['arm'][:14].ljust(14), r['case'][:22].ljust(22), r.get('turn'), str(r.get('expect')).ljust(13), str(r.get('status')).ljust(8),
              str(r.get('method')).ljust(16), r.get('verdict'), r.get('seconds'), r.get('article_in_answer'), r.get('answer_chars'))
print(summary, calls)
