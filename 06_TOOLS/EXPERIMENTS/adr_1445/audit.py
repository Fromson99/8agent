"""Read-only post-run audit: every model choice to read a located original and whether it was read.

Usage: audit.py <cell-dir>   (writes <cell-dir>/read-choice-audit.json; no model calls)
"""
import sys, json, gzip
from pathlib import Path
ROOT = Path('/home/jin/8-AGENT')
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime.legal_agent.journal_storage import connect

cell = Path(sys.argv[1]).resolve()
KINDS = ('GUIDED_ACTION_LIMIT', 'ANSWER_READ_REENTRY_PLANNED', 'ANSWER_READ_REENTRY_UNAVAILABLE',
         'CONTINUATION_ORIGINALS_ACQUIRED', 'ANSWER_REQUESTED_ORIGINALS_TO_ASSESS', 'GUIDED_ANSWER_WRITTEN',
         'ROLE_CHAIN_ORIGINAL_ACQUIRED', 'INVESTIGATION_BOUNDED_STOP')
runs = []
for journal in sorted((cell / 'runtime/legal-agent/runs').glob('*/*/journal.sqlite')):
    db = connect(journal)
    rows = [dict(r) for r in db.execute('SELECT seq,kind,payload_json FROM event WHERE kind IN (%s) ORDER BY seq'
                                         % ','.join('?' * len(KINDS)), KINDS)]
    db.close()
    events = [{'seq': r['seq'], 'kind': r['kind'], 'payload': json.loads(r['payload_json'])} for r in rows]
    if events:
        runs.append({'journal': str(journal.relative_to(cell)), 'events': events})


def gz(p):
    with gzip.open(p, 'rt') as f:
        return json.load(f)


# Model choices from the canonical generations: navigation READ and answer next_reads.
generations = json.loads((cell / 'generations.json').read_text()) if (cell / 'generations.json').exists() else []
choices = []
for row in generations:
    out = cell / 'canonical' / ('%03d-output.json.gz' % row['number'])
    if not out.exists():
        continue
    value = gz(out)
    if isinstance(value, dict) and value.get('choice') == 'READ':
        choices.append({'number': row['number'], 'turn': row['turn'], 'stage': row['stage'], 'kind': 'NAVIGATION_READ',
                        'targets': [s.get('target') for s in value.get('selections', [])]})
    if isinstance(value, dict) and value.get('next_reads'):
        choices.append({'number': row['number'], 'turn': row['turn'], 'stage': row['stage'], 'kind': 'ANSWER_NEXT_READS',
                        'targets': value['next_reads']})
summary = {'answer_read_rounds_planned': 0, 'answer_read_unavailable': 0, 'forced_or_continued_reads': 0,
           'chosen_reads_skipped': [], 'read_only_declined': 0, 'read_only_no_candidate': 0, 'limit_stops': 0}
for run in runs:
    for e in run['events']:
        p = e['payload']
        if e['kind'] == 'ANSWER_READ_REENTRY_PLANNED':
            summary['answer_read_rounds_planned'] += 1
        elif e['kind'] == 'ANSWER_READ_REENTRY_UNAVAILABLE':
            summary['answer_read_unavailable'] += 1
        elif e['kind'] == 'CONTINUATION_ORIGINALS_ACQUIRED':
            summary['forced_or_continued_reads'] += len(p.get('reads', []))
            summary['chosen_reads_skipped'] += [{k: s.get(k) for k in ('label', 'reason', 'role')} for s in p.get('skipped', [])]
        elif e['kind'] == 'GUIDED_ACTION_LIMIT':
            summary['limit_stops'] += 1
            summary['read_only_declined'] += p.get('read_only') == 'DECLINED'
            summary['read_only_no_candidate'] += p.get('read_only') == 'NO_LOCATED_READ'
final_unread = []
for turn in sorted(cell.glob('turn-*')):
    reply = json.loads((turn / 'guided-reply.json').read_text()) if (turn / 'guided-reply.json').exists() else {}
    final_unread.append({'turn': turn.name, 'proposed_reads_left': [r.get('label') for r in reply.get('proposed_reads') or []]})
# "Chose to read but not read": an answer choice the server could not read, a skipped chosen read,
# or a turn whose final answer still proposes located reads.
violations = (summary['answer_read_unavailable'] + len(summary['chosen_reads_skipped'])
              + sum(bool(t['proposed_reads_left']) for t in final_unread))
result = {'cell': cell.name, 'model_read_choices': choices, 'summary': summary, 'final_unread_proposals': final_unread,
          'chose_but_not_read': violations, 'runs': runs, 'model_calls': 0}
(cell / 'read-choice-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'summary': summary, 'final_unread_proposals': final_unread, 'chose_but_not_read': violations,
                  'model_read_choices': len(choices)}, ensure_ascii=False))
