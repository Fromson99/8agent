"""Read a GENOS live log; print only diagnostic names, counts and timings."""
import argparse
import json
import re

parser = argparse.ArgumentParser()
parser.add_argument('log')
args = parser.parse_args()
rows = []
markers = []
allowed = {'step', 'duration_ms', 'work_ms', 'thread_cpu_ms', 'start_log_ms', 'previous_log_ms',
           'previous_event', 'previous_step', 'document_count', 'unit_count', 'checked_count',
           'elapsed_ms', 'diagnostic_revision', 'request_id', 'run_id', 'worker_id'}
with open(args.log, encoding='utf-8', errors='replace') as stream:
    for line in stream:
        if line.startswith('{'):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            event = value.get('event', '')
        else:
            match = re.match(r'^\S+\s+(?:INFO|WARNING|ERROR|DEBUG)\s+([A-Za-z0-9_.:-]+)\b', line)
            if not match:
                continue
            event = match.group(1)
            value = dict(re.findall(r'\b([a-z_]+)=([A-Za-z0-9_.:-]+)', line))
        row = {'event': event}
        row.update({k: v for k, v in value.items() if k in allowed and isinstance(v, (str, int, float))})
        if event in ('step.finished', 'step.failed'):
            rows.append(row)
        elif event in ('rag.prepare.started', 'rag.loop.started', 'session.open.ready'):
            markers.append(row)
        try:
            slow_log = float(value.get('previous_log_ms', 0)) >= 100
        except (TypeError, ValueError):
            slow_log = False
        if slow_log:
            markers.append(row)
print('Timing only. Nested step durations overlap: DO NOT SUM. Low CPU does not identify NFS by itself.')
for row in markers:
    print(json.dumps(row, ensure_ascii=False))
print('Slowest completed/failed steps (top 30):')
def duration(row):
    try:
        return float(row.get('duration_ms', 0))
    except (TypeError, ValueError):
        return 0
for row in sorted(rows, key=duration, reverse=True)[:30]:
    print(json.dumps(row, ensure_ascii=False))
