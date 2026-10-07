"""Offline evidence extraction; no requests and no automatic semantic grading."""
import hashlib
import json
import sqlite3
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0506-gemma-v5-main-three-case-probe'


def read(path):
    return json.loads(path.read_text())


def walk(value, path=''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f'{path}.{key}')
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk(child, f'{path}[{i}]')
    else:
        yield path, value


def main():
    rows = []
    for case in read(ADR / 'product-cases.json')['cases']:
        base = ADR / 'artifacts/run-001' / case['case_id'] / 'hardened'
        calls = []
        for response_path in sorted((base / 'calls').glob('*/response.json')):
            request = read(response_path.with_name('request.json'))
            raw = read(response_path)
            view = json.loads(request['messages'][1]['content'])['view']
            schema = request['response_format']['json_schema']['schema']
            try:
                output = json.loads(raw['choices'][0]['message']['content'])
                invalid = [str(e.message) for e in jsonschema.Draft202012Validator(schema).iter_errors(output)]
                original = read(response_path.with_name('original-validation-schema.json'))
                original_invalid = [str(e.message) for e in jsonschema.Draft202012Validator(original).iter_errors(output)]
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                output, invalid, original_invalid = None, [str(exc)], [str(exc)]
            one_char = [path for path, value in walk(output)
                        if isinstance(value, str) and len(''.join(value.split())) == 1
                        and path.rsplit('.', 1)[-1] in ('requirement', 'reason', 'issue', 'text', 'draft_quote', 'quote')]
            decision = output or {}
            evidence = {e['evidence']: e for e in view.get('exact_evidence', [])}
            quote_checks = []
            for check in (output or {}).get('checks', []):
                for source in check.get('source_checks', []):
                    spans = evidence.get(source['source'], {}).get('spans', [])
                    quote_checks.append({'source': source['source'], 'quote': source['quote'],
                                         'verbatim_span': any(source['quote'] in s['text'] for s in spans)})
            calls.append({
                'call': response_path.parent.name, 'phase': view['phase'],
                'wire_schema_errors': invalid, 'original_schema_errors': original_invalid,
                'source_quote_checks': quote_checks, 'one_character_explanations': one_char,
                'intent': decision.get('intent'), 'actions': len((output or {}).get('actions', [])),
                'source_choices': len(((output or {}).get('source_selection') or {}).get('choices', [])),
                'decision_reason': decision.get('reason'),
                'finish_reason': raw.get('choices', [{}])[0].get('finish_reason'),
            })
        with sqlite3.connect(f'file:{base / "journal.sqlite"}?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            attempts = [dict(r) for r in db.execute('SELECT * FROM model_attempt')]
            events = [dict(r) for r in db.execute('SELECT * FROM event')]
        rows.append({'case_id': case['case_id'], 'calls': calls, 'attempts': attempts, 'events': events})
    pointer = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    result = {'schema_version': 'gemma-v5-trace-audit-v1', 'cases': rows,
              'main_unchanged': pointer.read_bytes() == (ADR / 'artifacts/main-before.json').read_bytes(),
              'main_sha256': hashlib.sha256(pointer.read_bytes()).hexdigest(),
              'semantic_grading': 'Not performed by this script; see CASE_REVIEW.md'}
    (ADR / 'artifacts/structural-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'main_unchanged': result['main_unchanged'], 'cases': [
        {'case_id': r['case_id'], 'calls': len(r['calls']),
         'schema_invalid': sum(bool(c['wire_schema_errors']) for c in r['calls']),
         'one_character_calls': sum(bool(c['one_character_explanations']) for c in r['calls']),
         'attempt_statuses': [a['status'] for a in r['attempts']]} for r in rows]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
