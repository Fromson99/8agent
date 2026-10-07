"""Read-only inspection of frozen logs and synthetic compatibility checks. No model calls."""
from pathlib import Path
from collections import defaultdict
import ast
import hashlib
import importlib.util
import json
import re
import statistics
import sys

ROOT = Path('/home/jin/8-AGENT')
OUT = Path(__file__).resolve().parent
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-0472-legal-agent-loop-rev3/artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3/revisions/rev-001/snapshot/02_BACKEND'
sys.path.insert(0, str(CAND))
from legal_agent.index import LegalIndex
from legal_agent.contracts import EvidenceUnit
from legal_agent.pipeline import answer_from_evidence
from jsonschema import Draft202012Validator

def read(path):
    return json.loads(path.read_text())

loops = read(ART / 'loop-results.json')['results']
gold = {r['case_id']: set(r['decisive_source_ids']) for r in read(ART / 'frozen-inputs.json')['cases']}
index = LegalIndex(ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1/store.sqlite')
results = {}
for arm in ('loop3-flash', 'loop3-qwen'):
    presented = defaultdict(set)
    payload_sizes = []
    card_counts = []
    clipped = []
    lost_fragments = []
    matched_calls = defaultdict(int)
    request_files = []
    for path in (ART / 'calls/run-001' / arm).rglob('request.json'):
        match = re.search(r'call-(\d+)-(loop-(cm-\d+)-(r\d+|compose))', str(path))
        if not match:
            continue
        call_no, phase, case_id, stage = match.groups()
        row = loops[f'{case_id}::{arm}::run-001']
        if not any(u['call'] == int(call_no) and u['phase'] == phase for u in row['usage']):
            continue
        matched_calls[(case_id, int(call_no), phase)] += 1
        raw = read(path)
        payload = raw['contents'][0]['parts'][0]['text'] if 'contents' in raw else raw['messages'][-1]['content']
        data = json.loads(payload)
        request_files.append(str(path.relative_to(ROOT)))
        by_handle = {c['handle']: c['source_id'] for c in row['cards']}
        if 'cards' in data:
            presented[case_id].update(by_handle[c['handle']] for c in data['cards'])
            payload_sizes.append(len(payload))
            card_counts.append(len(data['cards']))
        if 'evidence' in data:
            assert len(data['evidence']) == len(row['evidence_source_ids'])
            for sid, unit in zip(row['evidence_source_ids'], data['evidence']):
                full = index.article(sid).text()
                if len(unit['text']) >= len(full):
                    continue
                clipped.append({'case_id': case_id, 'source_id': sid, 'label': unit['label'],
                                'full_chars': len(full), 'sent_chars': len(unit['text'])})
                card = next((c for c in row['cards'] if c['source_id'] == sid), None)
                if card:
                    fragments = [t.strip() for t in card['text'].split('\n') if len(t.strip()) >= 20]
                    lost = [t for t in fragments if t in full and t not in unit['text']]
                    if lost:
                        lost_fragments.append({'case_id': case_id, 'source_id': sid, 'count': len(lost)})
    rows = [v for k, v in loops.items() if f'::{arm}::' in k]
    usage = [u for r in rows for u in r['usage']]
    never = [{'case_id': r['case_id'], 'source_ids': sorted(set(r['shown_source_ids']) - presented[r['case_id']])}
             for r in rows if set(r['shown_source_ids']) - presented[r['case_id']]]
    results[arm] = {
        'matched_request_files': len(request_files),
        'duplicate_matches': [list(k) for k, v in matched_calls.items() if v > 1],
        'created_card_case_pairs': sum(len(r['shown_source_ids']) for r in rows),
        'payload_card_case_pairs': sum(len(v) for v in presented.values()),
        'created_never_in_payload': never,
        'gold_created': sum(len(gold[r['case_id']] & set(r['shown_source_ids'])) for r in rows),
        'gold_in_payload': sum(len(gold[r['case_id']] & presented[r['case_id']]) for r in rows),
        'max_cards_in_payload': max(card_counts),
        'max_navigation_json_chars': max(payload_sizes),
        'composition_clipped': clipped,
        'prior_card_fragments_lost': lost_fragments,
        'model_call_seconds_sum_per_case_median': statistics.median(sum(u['seconds'] for u in r['usage']) for r in rows),
        'calls': len(usage),
        'calls_mean': sum(r['calls'] for r in rows)/len(rows),
        'cost_usd': sum((u.get('input_tokens') or 0)*.25/1e6 + (u.get('output_tokens') or 0)*1.5/1e6 for u in usage)
                    if arm == 'loop3-flash' else sum(u.get('cost_usd') or 0 for u in usage),
        'cost_basis': 'frozen policy arithmetic, not current price verification' if arm == 'loop3-flash' else 'stored provider receipts',
        'request_paths_sha256': hashlib.sha256('\n'.join(sorted(request_files)).encode()).hexdigest(),
    }
index.db.close()

# Execute the actual normalization function in isolation; do not initialize service/app/provider.
tree = ast.parse((ROOT/'service.py').read_text())
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_normalize')
namespace = {'Any': object}
exec(compile(ast.Module(body=[fn], type_ignores=[]), 'service.py::_normalize', 'exec'), namespace)
request = {'API_TYPE': 'ELS_QUERY', 'question': '모의 질문', 'channel': 'genos-chat',
           'session_id': 'synthetic-session', 'user_id': 'synthetic-user', 'request_id': 'synthetic-request'}
normalized = namespace['_normalize'](request)['json']
schema = read(ROOT/'00_SYSTEM/SCHEMAS/term-runtime-v1.schema.json')
request_validator = Draft202012Validator({'$ref': '#/$defs/Request', '$defs': schema['$defs']})
request_errors = [e.message for e in request_validator.iter_errors(normalized)]

# The bridge's render-only functions do not make network calls.
spec = importlib.util.spec_from_file_location('review_bridge', ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
body = {'answer': {'text': '모의 답변', 'claims': [{'id': 'claim:1', 'text': '모의 답변', 'source_ids': ['used']}]},
        'assembly': {'context': [{'id': 'used', 'document_name': '사용한 모의규정'},
                                 {'id': 'unused', 'document_name': '사용하지 않은 모의규정'}]}}
rendered = bridge.render(body)
answer_errors = list(Draft202012Validator({'$ref': '#/$defs/Answer', '$defs': schema['$defs']}).iter_errors(
    {'text':'모의 답','citations':[],'findings':[],'composition':{'mode':'plain'}}))
assert request_errors
assert '사용하지 않은 모의규정' in rendered
assert answer_errors
compatibility = {'normalized_request_extra_keys': sorted(set(normalized)-set(schema['$defs']['Request']['properties'])),
                 'request_schema_errors': request_errors,
                 'bridge_used_source_ids': sorted(bridge._used_source_ids(body)),
                 'bridge_renders_unused_context': '사용하지 않은 모의규정' in rendered,
                 'candidate_answer_rejected_by_current_schema': bool(answer_errors)}
from legal_agent.references import ReferenceResolver
import sqlite3
from types import SimpleNamespace
resolver = ReferenceResolver.__new__(ReferenceResolver)
resolver.index = SimpleNamespace(documents={'local': '모의규정', 'external': '다른법'},
                                 article=lambda sid: SimpleNamespace(document_id='local'),
                                 by_label=lambda doc, label: None)
resolver.by_name = {'모의규정': 'local', '다른법': 'external'}
resolver.short_names = dict(resolver.by_name)
resolver.aliases = {}
resolver.nav = sqlite3.connect(':memory:')
resolver.nav.execute('CREATE TABLE reference(id, document_id, json)')
text = '「다른법」 제9조를 따른다.'
resolver.nav.execute('INSERT INTO reference VALUES(?,?,?)', ('ref:synthetic', 'local', json.dumps({
    'locator': '제9조', 'source_text': text, 'mention_start': text.index('제9조'),
    'source_id': 'article:from', 'target_source_ids': ['article:wrong-old-target']})))
resolution = resolver.resolve_all()[0]
compatibility['explicit_other_document_missing_article'] = {
    'via': resolution.via, 'returned_target': resolution.target_source_id,
    'wrong_old_target_preserved': resolution.target_source_id == 'article:wrong-old-target'}
assert compatibility['explicit_other_document_missing_article']['wrong_old_target_preserved']
resolver.nav.close()

result = {'method': 'Existing recorded inputs matched by case/call/phase; no replay of model decisions or regrading. Synthetic tests invoke actual pure functions.',
          'results': results, 'compatibility': compatibility}
(OUT/'existing-run-diagnostics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
for arm, r in results.items():
    print(arm, {k:v for k,v in r.items() if not isinstance(v,list)})
    print('never in payload',sum(len(x['source_ids']) for x in r['created_never_in_payload']),
          'clipped',len(r['composition_clipped']), 'lost prior card fragments',len(r['prior_card_fragments_lost']))
print('compatibility', compatibility)
