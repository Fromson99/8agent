"""Validate this design package only; no corpus/model/runtime execution.

Run from the repository with .venv/bin/python <this-file> --output /tmp/report.json.
The JSON Schema deliberately covers only the contracts named in DESIGN.md.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    schema = json.loads((root / 'contracts.json').read_text())
    examples = json.loads((root / 'examples.json').read_text())
    errors, results = [], []
    Draft202012Validator.check_schema(schema)
    ids = set()
    for case in examples['cases']:
        if case['id'] in ids:
            errors.append('duplicate case: ' + case['id'])
        ids.add(case['id'])
        target = copy.deepcopy(schema)
        target['$ref'] = '#/$defs/' + case['definition']
        validation_errors = list(Draft202012Validator(target).iter_errors(case['value']))
        actual = not validation_errors
        results.append({'id': case['id'], 'definition': case['definition'],
                        'expected_valid': case['expected_valid'], 'actual_valid': actual,
                        'passed': actual == case['expected_valid']})
        if actual != case['expected_valid']:
            errors.append('case mismatch: ' + case['id'])
        if actual and case['definition'] == 'ReadPacket':
            packet = case['value']
            canonical = {k: v for k, v in packet.items() if k != 'packet_sha256'}
            if digest(canonical) != packet['packet_sha256']:
                errors.append('packet digest mismatch: ' + case['id'])
            if packet['target'] not in packet['covered_refs']:
                errors.append('fixture target not covered: ' + case['id'])
            if len({s['span_id'] for s in packet['spans']}) != len(packet['spans']):
                errors.append('duplicate fixture span ID: ' + case['id'])
            for span in packet['spans']:
                if span['end'] <= span['start'] or span['end'] - span['start'] != len(span['text']):
                    errors.append('fixture span extent mismatch: ' + case['id'])
                if hashlib.sha256(span['text'].encode()).hexdigest() != span['text_sha256']:
                    errors.append('fixture span digest mismatch: ' + case['id'])
    text = (root / 'DESIGN.md').read_text()
    links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', text)
    checked_links = []
    for link in links:
        if link.startswith(('https://', 'http://', '#')):
            continue
        local = link.split('#', 1)[0]
        path = root / local
        # The result file is produced only after this check succeeds.
        if local != 'validation.json' and not path.is_file():
            errors.append('missing local link: ' + local)
        checked_links.append(local)
    tool_names = [v['properties']['tool']['const'] for v in schema['$defs']['Action']['oneOf']]
    tested_tools = {c['value'].get('tool') for c in examples['cases']
                    if c['definition'] == 'Action' and c['expected_valid']}
    if set(tool_names) != tested_tools:
        errors.append('not all tool action shapes have a valid example')
    if not examples['synthetic_only']:
        errors.append('examples must be marked synthetic')
    report = {
        'status': 'PASS' if not errors else 'FAIL',
        'scope': 'Design JSON Schema, synthetic valid/invalid shapes, fixture hashes, local Markdown links only',
        'not_verified': ['production implementation', 'ACL or generation enforcement',
                         'per-tool payload semantics', 'corpus completeness',
                         'model quality', 'performance', 'GENOS deployment'],
        'schema_draft': '2020-12', 'tool_action_shapes': len(tool_names),
        'cases': len(results), 'passed': sum(r['passed'] for r in results),
        'valid_cases': sum(r['expected_valid'] for r in results),
        'invalid_cases': sum(not r['expected_valid'] for r in results),
        'local_links_checked': len(checked_links), 'errors': errors,
        'files_sha256': {n: sha(root / n) for n in
                         ('DESIGN.md', 'contracts.json', 'examples.json', 'evidence.json', 'validate_design.py')},
        'results': results,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ('results', 'files_sha256', 'not_verified')}, ensure_ascii=False))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
