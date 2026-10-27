"""Read-only byte accounting of frozen r9 and prior saved requests.

No model/server/source database, product mutation, prompt replay or answer
evaluation. Outputs contain lengths, hashes and structural paths only.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'09_ARTIFACTS/AUDITS/20261025-mvp-state-format-diagnosis'
CODE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1046/shared-io-r9/revisions/rev-001/snapshot'
sys.path.insert(0, str(CODE/'02_BACKEND'))
from semantic_runtime.legal_agent.navigation_input import INSTRUCTIONS as OLD_GUIDE
from semantic_runtime.legal_agent.input_guidance import navigation_instructions, TEXT
from semantic_runtime.legal_agent.shared_input_values import (
    compact_shared_values, expand_shared_values, judgment_text_options)
from semantic_runtime.legal_agent.judgment_text_reuse import Projection, INSTRUCTIONS as REUSE_GUIDE
from semantic_runtime.legal_agent.wire_schema import factor_schema


def pack(value): return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
def size(value): return len(pack(value).encode())
def wire_string(text): return size(text)-2
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def ref(path): return {'path':str(path.relative_to(ROOT)), 'sha256':sha(path)}


def inline(node, definitions):
    if isinstance(node, list): return [inline(v, definitions) for v in node]
    if isinstance(node, dict):
        if set(node) == {'$ref'}:
            assert node['$ref'].startswith('#/$defs/')
            return inline(definitions[node['$ref'][8:]], definitions)
        return {k:inline(v, definitions) for k,v in node.items() if k != '$defs'}
    return node


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT/'measurements.json'
    assert not target.exists(), 'Do not overwrite an earlier audit'
    path = ROOT/'04_EXPERIMENTS/ADR/ADR-1046-ontology-mvp-shared-io/artifacts/saved-encoding-check.json'
    saved = json.loads(path.read_text())
    initial = ROOT/'04_EXPERIMENTS/ADR/ADR-1045-ontology-mvp-terminal-frame/artifacts/input-repetition-analysis.json'
    old = json.loads(initial.read_text())
    calls = []; totals = Counter(); metadata_total = 0
    for row in saved['calls']:
        file = ROOT/row['source_request']['path']
        assert sha(file) == row['source_request']['sha256']
        before = json.loads(file.read_text()); after = deepcopy(before)
        user = json.loads(before['messages'][1]['content']); view = user['view']
        v3 = view.get('input_projection') == 'compact-selection-source-v3'
        shared = compact_shared_values(view) if v3 else deepcopy(view)
        assert expand_shared_values(shared) == view
        before_schema = before['response_format']['json_schema']['schema']
        full_schema = inline(before_schema, before_schema.get('$defs', {}))
        assert factor_schema(full_schema) == before_schema
        options = judgment_text_options(shared)
        codec = Projection(full_schema, options, view_hash=hashlib.sha256(pack(shared).encode()).hexdigest(),
            enabled=v3 and view.get('source_stage') in {'memory-assess', 'memory-assess-repair'})
        delta = {'input_view':0, 'conditional_navigation_guide':0,
                 'sharing_guide_and_codec_markers':0, 'output_reuse_guide':0, 'output_schema':0}
        if v3:
            delta['input_view'] = wire_string(pack({**user, 'view':shared}))-wire_string(before['messages'][1]['content'])
            for message in after['messages']:
                if message['role'] != 'system': continue
                old_guide = OLD_GUIDE+' '+TEXT
                assert message['content'].count(old_guide) == 1
                base = navigation_instructions(view); current = navigation_instructions(shared)
                delta['conditional_navigation_guide'] += wire_string(base)-wire_string(old_guide)
                delta['sharing_guide_and_codec_markers'] += wire_string(current)-wire_string(base)
                message['content'] = message['content'].replace(old_guide, current)
                if codec.changed:
                    message['content'] += '\n'+REUSE_GUIDE
                    delta['output_reuse_guide'] += wire_string('\n'+REUSE_GUIDE)
            after['messages'][1]['content'] = pack({**user,'view':shared})
            after['response_format']['json_schema']['schema'] = factor_schema(codec.wire)
            delta['output_schema'] = size(after['response_format'])-size(before['response_format'])
        assert size(before) == row['before_request_bytes']
        assert size(after) == row['after_encoding_bytes']
        assert sum(delta.values()) == size(after)-size(before)
        totals.update(delta)
        pool = shared.get('shared_input_values')
        detail = None
        if pool:
            without_pool = {k:v for k,v in shared.items() if k != 'shared_input_values'}
            pool_wire = wire_string(pack({'view':shared}))-wire_string(pack({'view':without_pool}))
            replacement_wire = wire_string(pack({'view':without_pool}))-wire_string(pack({'view':view}))
            reduced = deepcopy(shared)
            reduced['shared_input_values'].pop('binding_sha256')
            for entry in reduced['shared_input_values']['entries'].values():
                entry.pop('paths'); entry.pop('owner', None)
            server_metadata_bytes = wire_string(pack({'view':shared}))-wire_string(pack({'view':reduced}))
            metadata_total += server_metadata_bytes
            entries = [{'kind':e['kind'], 'encoding':e['encoding'], 'occurrences':len(e['paths']),
                        'stored_value_wire_bytes':wire_string(pack(e['value'])),
                        'paths':e['paths']} for e in pool['entries'].values()]
            detail = {'entries':entries, 'single_occurrence_values':sum(e['occurrences']==1 for e in entries),
                'referenced_occurrences':sum(e['occurrences'] for e in entries),
                'pool_added_wire_bytes':pool_wire, 'replaced_values_delta_wire_bytes':replacement_wire,
                'server_binding_paths_owner_wire_bytes':server_metadata_bytes,
                'metadata_note':'Marginal field size only; not safe to delete from canonical state. '
                    'A future codec must keep validation metadata server-side and bind actual wire to it.'}
            assert pool_wire + replacement_wire == delta['input_view']
        calls.append({'cell':row['cell'], 'call':row['call'], 'stage':row['stage'],
                      'before_bytes':size(before), 'after_bytes':size(after),
                      'increase_bytes':size(after)-size(before), 'delta':delta,
                      'pool':detail, 'source':ref(file)})
        assert sha(file) == row['source_request']['sha256']
    assert sum(totals.values()) == -saved['totals']['reduction_bytes']
    result = {'schema_version':'r9-state-format-readonly-diagnosis-v1',
        'scope':{'saved_requests':11,'distinct_questions':1,'external_model_calls':0,
                 'real_source_database_opened':False,'product_code_changed':False,
                 'model_or_prompt_effect_evaluated':False},
        'method':{'unit':'compact outer HTTP JSON UTF-8 bytes including nested content escaping',
                  'positive_delta':'input increased',
                  'input_metadata':'Existing server verification is required; marginal bytes are opportunity size, not validated savings.',
                  'baseline':'already optimized r8, not the original pre-optimization system',
                  'compose_exclusion':'r9 COMPOSE caller augmentation omission not included in old 4.053% or this exact reconciliation'},
        'original_categories':old['totals']['categories'],
        'original_total_bytes':saved['totals']['before_request_bytes'],
        'r9_total_bytes':saved['totals']['after_encoding_bytes'],
        'delta_by_component':dict(totals), 'net_reduction_bytes':-sum(totals.values()),
        'server_pool_metadata_opportunity_bytes':metadata_total,
        'calls':calls,'sources':[ref(path),ref(initial),ref(Path(__file__))]}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'totals':dict(totals),'pool_metadata_bytes':metadata_total,
        'assess':[{k:r[k] for k in ('cell','call','delta','pool')} for r in calls if r['stage']=='memory-assess']},ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
