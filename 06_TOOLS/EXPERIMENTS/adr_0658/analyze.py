"""Read-only accounting of the completed native journal, without model calls."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0658-internal-accounting-manager-local-probe'
RUN = ADR / 'artifacts/run-001'


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def read(path):
    return json.loads(path.read_text())


def main():
    result = read(RUN / 'result.json')
    journals = list((RUN / 'runtime/legal-agent/runs').glob('*/*/journal.sqlite'))
    assert len(journals) == 1
    original = journals[0]
    snapshot = RUN / 'journal-snapshot.sqlite'
    assert not snapshot.exists()
    with sqlite3.connect('file:' + str(original) + '?mode=ro', uri=True) as source:
        with sqlite3.connect(snapshot) as copy:
            source.backup(copy)
    with sqlite3.connect('file:' + str(snapshot) + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        stages = [dict(row) for row in db.execute("SELECT entity_id,version,payload_json,created_seq FROM entity_version WHERE kind='case_stage' ORDER BY created_seq")]
        for row in stages:
            row['payload'] = json.loads(row.pop('payload_json'))
        events = [dict(row) for row in db.execute('SELECT seq,kind,payload_json,created_at FROM event ORDER BY seq')]
        for row in events:
            row['payload'] = json.loads(row.pop('payload_json'))
        observations = [dict(row) for row in db.execute('SELECT * FROM observation ORDER BY created_seq')]
        for row in observations:
            row['request'] = json.loads(row.pop('request_json'))
            row['result'] = json.loads(row.pop('result_json'))
        evidence = [dict(row) for row in db.execute('SELECT * FROM evidence_unit ORDER BY created_seq')]
        attempts = [dict(row) for row in db.execute('SELECT a.attempt_id,a.status,a.input_tokens,a.output_tokens,a.created_seq,v.body_json FROM model_attempt a JOIN model_view v USING(view_id) ORDER BY a.created_seq')]
        for row in attempts:
            row['view'] = json.loads(row.pop('body_json'))
        delivered = set(row[0] for row in db.execute("SELECT DISTINCT e.source_id FROM evidence_unit e JOIN presentation p USING(evidence_id) JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'"))
    put(RUN / 'native-stages.json', stages)
    put(RUN / 'native-events.json', events)
    put(RUN / 'native-observations.json', observations)
    put(RUN / 'native-evidence.json', evidence)
    put(RUN / 'native-model-views.json', attempts)
    by_stage = {row['entity_id'].removeprefix('case:'): row['payload'] for row in stages}
    recall = by_stage.get('RECALL', {})
    discovery = recall.get('discovery', {})
    acquired = by_stage.get('READ', {}).get('record', {})
    chosen = by_stage.get('SELECT', {})
    reads = [row for row in observations if row['tool'] == 'read']
    actual_read_ids = {row['source_id'] for row in evidence}
    # MEMORY_MODEL_INPUT is an exact additional receipt for source menus and
    # calls that may not register presentation rows (e.g. a failed selection).
    call_sources = []
    def walk(value, target):
        if isinstance(value, dict):
            sid = value.get('source_id')
            if isinstance(sid, str) and ('text' in value or 'original' in value):
                target.add(sid)
            for item in value.values():
                walk(item, target)
        elif isinstance(value, list):
            for item in value:
                walk(item, target)
    for event in events:
        if event['kind'] == 'MEMORY_MODEL_INPUT':
            ids = set()
            walk(event['payload'].get('data'), ids)
            call_sources.append({'phase': event['payload']['phase'], 'source_ids': sorted(ids), 'source_count': len(ids)})
    put(RUN / 'model-source-accounting.json', {'presentation_success_source_ids': sorted(delivered), 'memory_model_inputs': call_sources})
    branches = {name: {'selected': len(value.get('selected_for_read', [])),
                       'discovered': len(value.get('discovered', []))}
                for name, value in discovery.get('branches', {}).items()}
    progress = [json.loads(line) for line in (RUN / 'progress.jsonl').read_text().splitlines()] if (RUN / 'progress.jsonl').exists() else []
    source_rows = []
    binding = read(ADR / 'artifacts/design/binding.json')
    generation = ROOT / binding['release']['data_path']
    nav = read(generation / 'navigation/manifest.json')
    navdb = generation / 'navigation' / ('index.sqlite' if (generation / 'navigation/index.sqlite').exists() else 'navigation.sqlite')
    with sqlite3.connect('file:' + str(navdb) + '?mode=ro', uri=True) as db:
        for sid in discovery.get('selected_for_read', []):
            row = db.execute('SELECT json FROM source WHERE id=?', (sid,)).fetchone()
            if row:
                value = json.loads(row[0])
                source_rows.append({k: value.get(k) for k in ('id', 'document_id', 'document_name', 'unit_id', 'heading')})
    put(RUN / 'selected-for-read-labels.json', source_rows)
    summary = {'http_status': result['http_status'], 'seconds': result['seconds'],
               'active_release': binding['pointer']['release_id'],
               'data_generation': binding['source_manifest']['generation_id'],
               'model': binding['model_policy']['model'], 'question': result['request']['question'],
               'branches': branches, 'recall_candidates': len(discovery.get('selected_for_read', [])),
               'read_actions': len(reads), 'unique_read_sources': len(actual_read_ids),
               'read_complete_sources': len(acquired.get('read_complete', [])),
               'source_chars': acquired.get('source_chars'), 'source_recall_limits': acquired.get('limits', []),
               'answer_selected_sources': len(chosen.get('final_ids', [])),
               'final_source_ids': chosen.get('final_ids', []),
               'successfully_presented_sources': len(delivered),
               'physical_model_calls': result['physical_model_calls'],
               'input_tokens': sum(row.get('input_tokens') or 0 for row in result['usage']),
               'output_tokens': sum(row.get('output_tokens') or 0 for row in result['usage']),
               'cost_usd': sum(row.get('cost_usd') or 0 for row in result['usage']),
               'native_model_phases': [row['view'].get('source_stage', row['view'].get('phase')) for row in attempts],
               'progress_events_recorded': len(progress),
               'progress_capture_available': bool(progress),
               'progress_capture_limitation': 'The recorder used the workspace observability context, while the frozen release has its own context. Zero captured UI events is not zero actual activity. Native read observations and provider receipts were recorded independently.',
               'progress_by_kind': dict(Counter(row['kind'] for row in progress)) if progress else None,
               'read_progress_details': sum(len(row.get('details', [])) for row in progress if row['kind'] in ('reading', 'read_complete')) if progress else None,
               'recall_document_distribution': dict(Counter(row['document_name'] for row in source_rows)),
               'executed_native_stages': [row['entity_id'].removeprefix('case:') for row in stages],
               'quality_scored': False, 'genos_tested': False, 'main_unchanged': True}
    put(RUN / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
