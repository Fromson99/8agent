"""Deterministic, lossless serialization check on saved request JSON only.

No source lookup, server, model, prompt replay or answer evaluation. Does not
estimate tokens or latency. The COMPOSE caller augmentation change is excluded.
Only aggregate lengths/hashes/field paths are saved, never copied source prose.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT/'04_EXPERIMENTS/ADR/ADR-1046-ontology-mvp-shared-io/artifacts'
CODE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1046/shared-io-r9/snapshot'
sys.path.insert(0, str(CODE/'02_BACKEND'))
from semantic_runtime.legal_agent.navigation_input import INSTRUCTIONS as OLD_GUIDE
from semantic_runtime.legal_agent.input_guidance import navigation_instructions, TEXT
from semantic_runtime.legal_agent.shared_input_values import (
    compact_shared_values, expand_shared_values, judgment_text_options)
from semantic_runtime.legal_agent.judgment_text_reuse import Projection, INSTRUCTIONS as REUSE_GUIDE
from semantic_runtime.legal_agent.wire_schema import factor_schema


def pack(value): return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
def size(value): return len(pack(value).encode())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def inline(node, definitions):
    if isinstance(node, list): return [inline(v, definitions) for v in node]
    if isinstance(node, dict):
        if set(node) == {'$ref'}:
            assert node['$ref'].startswith('#/$defs/')
            return inline(definitions[node['$ref'][8:]], definitions)
        return {k:inline(v, definitions) for k,v in node.items() if k != '$defs'}
    return node


def main():
    output = ART/'saved-encoding-check.json'
    assert not output.exists(), 'Keep prior audit artifacts immutable'
    source = ROOT/'04_EXPERIMENTS/ADR/ADR-1045-ontology-mvp-terminal-frame/artifacts/input-repetition-analysis.json'
    ledger = json.loads(source.read_text()); rows = []
    for call in ledger['calls']:
        path = ROOT/call['request']['path']; before_hash = sha(path)
        assert before_hash == call['request']['sha256']
        before = json.loads(path.read_text()); after = deepcopy(before)
        user = json.loads(before['messages'][1]['content']); view = user['view']
        v3 = view.get('input_projection') == 'compact-selection-source-v3'
        compact = compact_shared_values(view) if v3 else deepcopy(view)
        assert expand_shared_values(compact) == view
        old_schema = before['response_format']['json_schema']['schema']
        expanded_schema = inline(old_schema, old_schema.get('$defs', {}))
        assert factor_schema(expanded_schema) == old_schema
        options = judgment_text_options(compact)
        codec = Projection(expanded_schema, options, view_hash=hashlib.sha256(pack(compact).encode()).hexdigest(),
                           enabled=v3 and view.get('source_stage') in {'memory-assess', 'memory-assess-repair'})
        replaced = 0
        if v3:
            for message in after['messages']:
                if message['role'] != 'system': continue
                old = OLD_GUIDE+' '+TEXT
                count = message['content'].count(old)
                assert count == 1
                message['content'] = message['content'].replace(old, navigation_instructions(compact))
                replaced += count
                if codec.changed: message['content'] += '\n'+REUSE_GUIDE
            after['messages'][1]['content'] = pack({**user, 'view': compact})
            after['response_format']['json_schema']['schema'] = factor_schema(codec.wire)
        assert replaced == int(v3)
        assert sha(path) == before_hash
        rows.append({'cell':call['cell'], 'call':call['call'], 'stage':view.get('source_stage'),
            'source_request':call['request'], 'http_status_in_old_run':call['http_status'],
            'before_request_bytes':size(before), 'after_encoding_bytes':size(after),
            'reduction_bytes':size(before)-size(after), 'before_view_bytes':size(view),
            'after_view_bytes':size(compact), 'before_schema_bytes':size(old_schema),
            'after_schema_bytes':size(after['response_format']['json_schema']['schema']),
            'shared_values':len(compact.get('shared_input_values', {}).get('entries', {})),
            'judgment_text_choices':len(options), 'output_text_reuse_offered':codec.changed,
            'exact_input_restored':True, 'source_unchanged':True})
    total_before = sum(row['before_request_bytes'] for row in rows)
    total_after = sum(row['after_encoding_bytes'] for row in rows)
    result = {'schema_version':'saved-encoding-contract-check-v1',
        'kind':'deterministic_serialization_audit', 'external_model_calls':0,
        'source_database_opened':False, 'answer_evaluation_performed':False,
        'actual_token_or_latency_savings':None,
        'limitation':'11 saved requests from one question, A0/A1 only; includes rejected HTTP429. '
            'Exact view round trips and schema refactoring only. COMPOSE caller augmentation is excluded. '
            'Not a new model run, quality comparison, or claim of end-to-end request identity.',
        'source_ledger':{'path':str(source.relative_to(ROOT)), 'sha256':sha(source)},
        'totals':{'requests':len(rows), 'before_request_bytes':total_before,
                  'after_encoding_bytes':total_after, 'reduction_bytes':total_before-total_after,
                  'reduction_percent':round(100*(total_before-total_after)/total_before, 3)},
        'calls':rows}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result['totals'], ensure_ascii=False))


if __name__ == '__main__': main()
