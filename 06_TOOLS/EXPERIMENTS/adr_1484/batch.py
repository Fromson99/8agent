"""Each question once per arm (baseline, then candidate), one isolated process per request; no automatic retries."""
from common import *
import subprocess, time, fcntl


def main():
    cases = read(DES/'live-cases.json'); limits = read(DES/'criteria.json')['limits']; results = []; consecutive_unknown = 0
    lock = (ART/'batch.lock').open('a+'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (ART/'batch-started.json').exists(): raise RuntimeError('Existing batch may not be replayed')
    started = time.time(); put(ART/'batch-started.json', {'time': started, 'pid': os.getpid(), 'cases': len(cases)})
    stop = None
    for case, arm in [(c, a) for c in cases for a in ('candidate',)]:
        cid = case['id']; folder = ART/'live'/(cid+'-'+arm)
        with (ART/'batch.log').open('a') as log:
            proc = subprocess.run([sys.executable, str(Path(__file__).with_name('live.py')), cid, arm], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        calls = read(folder/'calls.json') if (folder/'calls.json').exists() else []
        result = read(folder/'result.json') if (folder/'result.json').exists() else {}
        turn = (result.get('turns') or [{}])[-1]
        unknown = any(c['status'] in ('unknown', 'started') for c in calls)
        row = {'case_id': cid, 'arm': arm, 'returncode': proc.returncode, 'http_status': turn.get('http_status'), 'seconds': turn.get('request_seconds'),
               'physical_calls': len(calls), 'unknown': unknown, 'claims': turn.get('claims', 0), 'needs_guidance': turn.get('needs_guidance')}
        results.append(row); put(folder/'worker-exit.json', row)
        consecutive_unknown = consecutive_unknown+1 if unknown else 0
        if proc.returncode != 0: stop = 'Runner or resource failure; inspect preserved worker diagnostics'
        elif consecutive_unknown >= 3: stop = 'Three consecutive UNKNOWN requests'
        allcalls = [c for p in (ART/'live').glob('*/calls.json') for c in read(p)]
        if len(allcalls) >= limits['physical_total'] or sum((c.get('usage') or {}).get('cost', 0) for c in allcalls) >= limits['reported_cost_usd']:
            stop = 'Frozen experiment budget reached'
        if not stop and time.time()-started >= limits['time_box_minutes']*60 and len(results) < len(cases):
            stop = 'Time box reached before the next request'
        put(ART/'batch-status.json', {'state': 'STOPPED' if stop else 'RUNNING', 'completed_requests': len(results), 'total': len(cases), 'cases': results, 'stop': stop, 'physical_calls': len(allcalls)})
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if stop: break
    put(ART/'batch-completed.json', {'state': 'STOPPED' if stop else 'EXECUTION_FINISHED_REVIEW_REQUIRED', 'cases': results, 'stop': stop,
                                     'remaining': [(c['id'], a) for c in cases for a in ('candidate',)][len(results):], 'quality_certified': False})


if __name__ == '__main__':
    main()
