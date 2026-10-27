"""Read saved requests only; exact byte attribution, no product/model execution."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1045-ontology-mvp-terminal-frame'
MIN_REPEAT_BYTES = 128


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def size(segment, nested=True):
    # Bytes contributed by inner JSON to the outer messages[].content string.
    return len((dump(segment)[1:-1] if nested else segment).encode())


GUIDE_PATHS = {
    ('view', 'connection_scope_rule'), ('view', 'concept_policy'),
    ('view', 'references', 'menu'), ('view', 'connection_review', 'rule'),
    ('view', 'read_judgments', 'rule'), ('view', 'read_judgments', 'retention_rule'),
    ('view', 'investigation_chain', 'compaction_rule'),
    ('view', 'investigation_chain', 'memory_rule'),
    ('view', 'previous_assessments', 'meaning'),
    ('view', 'document_term_candidates', 'meaning'),
    ('view', 'law_title_hints', 'no_match_means'),
}
QUESTION_TOP = {'request', 'question', 'current_request', 'original_requirements',
                'current_facts', 'user_fact_sources', 'request_quote_options', 'issues'}
JUDGMENT_TOP = {'read_judgments', 'previous_assessments', 'investigation_chain',
                'connection_action_history', 'gap_history', 'previous_reference_decisions',
                'previous_searches', 'structure_search_history', 'accepted_claims', 'limitations'}
CANDIDATE_TOP = {'tool_options', 'read_candidates', 'locator_options', 'connection_scope_choices',
                 'references', 'document_structures', 'document_term_candidates',
                 'law_title_hints', 'shared_navigation_cards', 'catalogue', 'domain_choice',
                 'ontology_bundles', 'ontology_context_limits'}
SOURCE_META_TOP = {'sources', 'exact_evidence', 'evidence_options', 'already_read',
                   'already_presented_reads', 'saved_inventory', 'retained_original_context'}


def category(path, value):
    top = path[1] if len(path) > 1 and path[0] == 'view' else ''
    leaf = path[-1] if path else ''
    if path in GUIDE_PATHS or top == 'capabilities' or (
        top == 'document_structures' and leaf == 'search_rule'
    ):
        return 'guide_user'
    if isinstance(value, str) and (
        (top in {'sources', 'exact_evidence', 'evidence_options'} and leaf == 'text')
        or leaf in {'source_quote', 'reference_witness', 'anchor_endpoint_quote'}
    ):
        return 'source_text'
    if top in QUESTION_TOP or leaf in {'request_quote', 'request_text'}:
        return 'state_question_and_facts'
    if top in JUDGMENT_TOP:
        return 'state_judgments_and_history'
    if top in CANDIDATE_TOP:
        return 'state_candidates_and_catalogue'
    if top in SOURCE_META_TOP:
        return 'state_source_metadata'
    return 'state_execution_and_structure'


@dataclass
class Node:
    path: tuple
    logical: tuple
    raw: str
    parts: Counter
    children: list
    string_value: str | None = None

    @property
    def nbytes(self):
        return sum(self.parts.values())

    @property
    def digest(self):
        return sha(self.raw.encode())


def node(value, path=(), logical=(), *, nested=True, fixed=None, table=None):
    cat = fixed or category(logical, value)
    raw = dump(value)
    children = []
    parts = Counter()
    if isinstance(value, dict):
        cols = value.get('table_columns')
        for k, v in value.items():
            child_logical = logical + (k,)
            child_table = None
            if k == 'table_rows' and isinstance(cols, list):
                child_table = (logical, cols, 'rows')
            if k == 'table_defaults':
                child_logical = logical
            ch = node(v, path + (k,), child_logical, nested=nested, fixed=fixed, table=child_table)
            children.append(ch)
            parts.update(ch.parts)
            parts[fixed or category(child_logical, v)] += size(dump(k) + ':', nested)
        parts[cat] += size('{' + ',' * max(0, len(value)-1) + '}', nested)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            child_logical = logical + (str(i),)
            child_table = None
            if table is not None:
                parent, cols, mode = table
                if mode == 'rows':
                    child_logical = parent + (str(i),)
                    child_table = (child_logical, cols, 'values')
                elif i < len(cols):
                    child_logical = parent + (str(cols[i]),)
            ch = node(v, path + (str(i),), child_logical, nested=nested, fixed=fixed, table=child_table)
            children.append(ch)
            parts.update(ch.parts)
        parts[cat] += size('[' + ',' * max(0, len(value)-1) + ']', nested)
    else:
        parts[cat] += size(raw, nested)
    assert sum(parts.values()) == size(raw, nested), (path, parts)
    return Node(path, logical, raw, parts, children, value if isinstance(value, str) else None)


def walk(root):
    yield root
    for child in root.children:
        yield from walk(child)


def pathstr(path):
    return '/' + '/'.join(path)


def descriptor(n):
    return {'path': pathstr(n.path), 'logical_path': pathstr(n.logical),
            'wire_value_bytes': n.nbytes, 'sha256': n.digest, 'categories': dict(n.parts)}


def repeat_nodes(root, previous=None):
    """Greedy maximal exact subtrees; selected parent prevents child double counting."""
    seen = {} if previous is None else previous
    chosen = []
    def visit(n):
        if n.nbytes >= MIN_REPEAT_BYTES and n.digest in seen:
            chosen.append({**descriptor(n), 'first_match': seen[n.digest]})
            return
        if previous is None and n.nbytes >= MIN_REPEAT_BYTES:
            seen[n.digest] = pathstr(n.path)
        for ch in n.children:
            visit(ch)
    visit(root)
    parts = Counter()
    for row in chosen:
        parts.update(row['categories'])
    return {'wire_bytes': sum(parts.values()), 'by_category': dict(parts),
            'selected_subtrees': len(chosen), 'items': chosen}


def ref(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(raw), 'bytes': len(raw)}


def system_split(text):
    """Task/semantic instructions are not mislabeled as pure JSON formatting."""
    parts = Counter()
    for line in text.splitlines(keepends=True):
        representation = line.startswith((
            '선택 ID는 ', '응답 스키마에 요구된 값만 ', 'Output keys only:',
            '[JSON transmission format]'))
        parts['guide_system_representation' if representation else 'guide_system_task'] += size(line)
    assert sum(parts.values()) == size(text)
    return parts


def main():
    accounting_path = ADR / 'artifacts/live-wire-accounting.json'
    accounting = json.loads(accounting_path.read_text())
    calls, total, accepted_total = [], Counter(), Counter()
    within_total, across_total = Counter(), Counter()
    history = defaultdict(dict)
    system_history = defaultdict(dict)
    schema_history = defaultdict(dict)
    source_groups, top_fields = [], Counter()
    for saved in accounting['calls']:
        p = ROOT / saved['sources']['request']['path']
        assert ref(p)['sha256'] == saved['sources']['request']['sha256']
        d = json.loads(p.read_text())
        cell = saved['cell']; call = saved['physical_call_within_cell']
        label = f'{cell}/call-{call:03d}'
        actual_wire = len(dump(d).encode())
        assert actual_wire == saved['request']['compact_utf8_bytes']
        parts, user_parts = Counter(), Counter()
        within_bytes, across_bytes = 0, 0
        within_items, across_items, fields = [], [], []
        system_repeat = 0
        for mi, m in enumerate(d['messages']):
            content = m['content']
            if m['role'] == 'system':
                parts.update(system_split(content))
                old_lines = system_history[cell]
                for line in content.splitlines(keepends=True):
                    if size(line) >= 32 and sha(line.encode()) in old_lines:
                        system_repeat += size(line)
                for line in content.splitlines(keepends=True):
                    if size(line) >= 32:
                        old_lines.setdefault(sha(line.encode()), label)
                continue
            if m['role'] != 'user':
                raise AssertionError('Unexpected saved message role')
            value = json.loads(content)
            assert dump(value) == content, 'Noncanonical inner JSON requires a lexical parser'
            root = node(value)
            parts.update(root.parts); user_parts.update(root.parts)
            intra = repeat_nodes(root)
            prior = repeat_nodes(root, history[cell])
            within_total.update(intra['by_category']); across_total.update(prior['by_category'])
            within_bytes += intra['wire_bytes']; across_bytes += prior['wire_bytes']
            within_items.extend(intra['items']); across_items.extend(prior['items'])
            for n in walk(root):
                if n.nbytes >= MIN_REPEAT_BYTES:
                    history[cell].setdefault(n.digest, label + pathstr(n.path))
            view = next(x for x in root.children if x.path == ('view',))
            for n in view.children:
                fields.append({'field': n.path[-1], 'wire_value_bytes': n.nbytes,
                               'categories': dict(n.parts)})
                top_fields[n.path[-1]] += n.nbytes
            groups = defaultdict(list)
            for n in walk(root):
                if n.string_value is not None and n.parts.get('source_text', 0):
                    groups[sha(n.string_value.encode())].append(n)
            for digest, nodes in groups.items():
                if len(nodes) > 1:
                    source_groups.append({'call': label, 'text_sha256': digest,
                       'occurrences': len(nodes), 'text_utf8_bytes': len(nodes[0].string_value.encode()),
                       'repeated_text_utf8_bytes': len(nodes[0].string_value.encode()) * (len(nodes)-1),
                       'repeated_wire_value_bytes': sum(n.nbytes for n in nodes[1:]),
                       'paths': [pathstr(n.path) for n in nodes]})
        schema = node(d['response_format'], nested=False, fixed='guide_schema')
        parts['guide_schema'] += schema.nbytes
        schema_repeat = repeat_nodes(schema, schema_history[cell])
        for n in walk(schema):
            if n.nbytes >= MIN_REPEAT_BYTES:
                schema_history[cell].setdefault(n.digest, label + '/response_format' + pathstr(n.path))
        other = actual_wire - sum(parts.values())
        assert other >= 0
        parts['wire_other'] = other
        assert sum(parts.values()) == actual_wire
        total.update(parts)
        if saved['http_status'] == 200:
            accepted_total.update(parts)
        calls.append({'cell': cell, 'call': call, 'stage': saved['stage'],
             'http_status': saved['http_status'], 'request': ref(p), 'wire_bytes': actual_wire,
             'categories': dict(parts), 'user_json_wire_bytes': sum(user_parts.values()),
             'user_categories': dict(user_parts),
             'user_same_request_exact_repetition': {'wire_bytes': within_bytes,
                  'selected_subtrees': len(within_items), 'items': within_items},
             'user_prior_call_exact_retransmission': {'wire_bytes': across_bytes,
                  'selected_subtrees': len(across_items), 'items': across_items},
             'system_prior_call_exact_line_retransmission_bytes': system_repeat,
             'schema_prior_call_exact_subtree_retransmission': schema_repeat,
             'top_fields': sorted(fields,key=lambda x:x['wire_value_bytes'],reverse=True)})
    def coarse(parts):
        return { 'source_text': parts['source_text'],
            'state_and_question': sum(v for k,v in parts.items() if k.startswith('state_')),
            'format_and_task_guidance': sum(v for k,v in parts.items() if k.startswith('guide_')),
            'wire_other': parts['wire_other'] }
    report = {
        'schema_version': 'saved-input-repetition-v1',
        'scope': {'requests': len(calls), 'accepted_responses': 10, 'rejected_requests': 1,
                  'unique_question_count': 1, 'arms': ['A0','A1'], 'model_calls_performed': 0,
                  'source_database_opened': False, 'product_code_changed': False},
        'method': {
            'unit': 'Exact compact UTF-8 HTTP JSON bytes, including nested content-string escaping; never estimated tokens.',
            'source_text': 'Only original text in sources/exact_evidence/evidence_options and explicit source_quote/witness fields. Metadata remains state.',
            'state': 'Question/facts, source coordinates, candidates, decisions/history, execution fields and their JSON structure. No assumption that all state is removable.',
            'guidance': 'Response format/schema, system task/format guidance, explicitly allowlisted user-view instruction fields; not all of this is pure format.',
            'guide_paths': [pathstr(x) for x in sorted(GUIDE_PATHS)],
            'tables': 'Classify table-row cells by their table_columns without expanding or duplicating shared defaults.',
            'within_request': 'Exact JSON value-subtree repeats; first occurrence retained, parent selection excludes children. Minimum nested wire value size 128 bytes.',
            'between_calls': 'Exact value-subtree seen in earlier calls of the same cell only; maximal matching parents, no child double count. Request-local IDs may change meaning; equality is syntactic.',
            'system_repetition': 'Exact lines at least 32 escaped bytes seen in earlier calls of same cell; no cross-arm sharing assumed.',
            'schema_repetition': 'Exact subtrees at least 128 bytes repeated across calls in same cell, reported separately.',
            'not_additive': 'Within-request and prior-call repeated byte sets may overlap. Do not add them as a savings estimate.',
            'not_savings': 'Observed repetition is gross size, not removable bytes or measured speed/cost reduction. Reference-dictionary overhead and behavioral validation remain.',
            'privacy': 'No source or generated text copied; paths, hashes, sizes and classifications only.'},
        'totals': {'wire_bytes':sum(total.values()), 'categories':dict(total), 'coarse':coarse(total),
            'accepted_only_wire_bytes':sum(accepted_total.values()), 'accepted_only_coarse':coarse(accepted_total),
            'user_same_request_repetition_bytes':sum(within_total.values()),
            'user_same_request_repetition_by_category':dict(within_total),
            'user_prior_call_retransmission_bytes':sum(across_total.values()),
            'user_prior_call_retransmission_by_category':dict(across_total),
            'system_prior_call_retransmission_bytes':sum(c['system_prior_call_exact_line_retransmission_bytes'] for c in calls),
            'schema_prior_call_retransmission_bytes':sum(c['schema_prior_call_exact_subtree_retransmission']['wire_bytes'] for c in calls),
            'exact_source_text_same_request_repeated_utf8_bytes':sum(x['repeated_text_utf8_bytes'] for x in source_groups),
            'exact_source_text_same_request_repeated_wire_value_bytes':sum(x['repeated_wire_value_bytes'] for x in source_groups)},
        'top_user_fields': [{'field':k,'wire_value_bytes':v} for k,v in top_fields.most_common()],
        'source_text_same_request_groups':sorted(source_groups,key=lambda x:x['repeated_wire_value_bytes'],reverse=True),
        'calls':calls,
        'evidence':[ref(accounting_path), ref(Path(__file__))],
        'verification': {'all_inner_json_exact_roundtrip':True,
            'all_request_sizes_match_prior_accounting':True,'all_category_sums_equal_request_bytes':True,
            'request_hashes_before_analysis_match_ledger':True},
    }
    for c in calls:
        assert ref(ROOT/c['request']['path'])['sha256']==c['request']['sha256']
    report['verification']['request_hashes_unchanged_after_analysis']=True
    output=ADR/'artifacts/input-repetition-analysis.json'
    if output.exists():
        raise SystemExit('Refusing to overwrite existing analysis')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'report':str(output.relative_to(ROOT)),'totals':report['totals'],
        'top_fields':report['top_user_fields'][:12],
        'largest_source_repeats':report['source_text_same_request_groups'][:3]},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
