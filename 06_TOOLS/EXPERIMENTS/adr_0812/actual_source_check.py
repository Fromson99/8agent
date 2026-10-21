"""Supplemental read-only location diagnostic; not a quality/accuracy experiment."""
import hashlib
import json
import resource
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

sys.dont_write_bytecode = True
ROOT = Path('/home/jin/8-AGENT')
OUT = ROOT / '04_EXPERIMENTS/ADR/ADR-0812-comparison-wire-context/artifacts/actual-source-after'
OUT.mkdir(parents=True,exist_ok=False)
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0812-comparison-wire-context'
freeze = json.loads((ADR / 'artifacts/design/freeze.json').read_text())
data = json.loads((ADR / 'artifacts/design/data-binding.json').read_text())
CODE = ROOT / freeze['code_root']
GEN = ROOT / data['path']
sys.path[:0] = [str(CODE / '02_BACKEND'), str(CODE), str(ROOT / '02_BACKEND')]
resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
started = time.monotonic()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage(value):
    print(value, flush=True)


def run():
    stage('verify frozen code and selected immutable data')
    assert sha(GEN / 'manifest.json') == data['manifest_sha256']
    code_hashes = {}
    for path, expected in freeze['serving_files'].items():
        actual = sha(CODE / path)
        assert actual == expected, path
        code_hashes[path] = actual
    from semantic_runtime.storage import Store, verify_store_binding
    from semantic_runtime.term_index import SourceMap
    from semantic_runtime.navigation_match import ReverseMatcher
    from semantic_runtime.inherited_navigation import bind_structure
    from semantic_runtime.team_scope import select_documents
    from semantic_runtime.legal_agent import structure_query as sq, definition_entry as de
    from semantic_runtime.term_references import reference_targets
    manifest = json.loads((GEN / 'manifest.json').read_text())
    nav_manifest = json.loads((GEN / 'navigation/manifest.json').read_text())
    verify_store_binding(GEN / 'store.sqlite', manifest['store_sha256'])
    assert sha(GEN / 'navigation/navigation.sqlite') == nav_manifest['index_sha256']
    # Direct readonly connection after independent hash proof avoids resident DB copies.
    store = Store(GEN, verify=False)
    nav = sqlite3.connect((GEN / 'navigation/navigation.sqlite').as_uri() + '?mode=ro', uri=True)
    nav.row_factory = sqlite3.Row
    nav.execute('PRAGMA query_only=ON')
    store.selection.bind(nav, navigation=True)
    scope = set(select_documents(store, 'risk_team'))
    definitions = {r[0]: json.loads(r[1]) for r in nav.execute('SELECT id,json FROM definition')}
    tools = NS(db=nav, terms={}, sources=SourceMap(nav), definitions=definitions,
               definition_summaries=tuple((k, v['source_id'], v.get('key') or v['label'])
                                         for k, v in definitions.items()))
    # These empty glossary/term catalogues are unrelated to explicit location and
    # definition entry. This diagnostic does not evaluate free-text term retrieval.
    lookup = sqlite3.connect(':memory:')
    lookup.execute('CREATE TABLE label(source TEXT,label TEXT,key TEXT)')
    stage('build actual document/structure metadata using frozen candidate loaders')
    matcher = bind_structure(ReverseMatcher(store.db, tools, NS(dbs={'lookup': lookup})), store)
    question = '유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?'
    session = NS(tools=tools, store=store, matcher=matcher, scope=scope,
                 context=NS(request={'question': question}))
    rows = de.matches(session)
    verified = [de.verified(session, row) for row in rows]
    origins = {v['definition']['document_id'] for v in verified}
    target_docs = {v['document_id'] for d in verified for c in d['connections'] for v in c['targets']}
    limited = NS(**{**vars(session), 'scope': scope - target_docs})
    limited_rows = [de.verified(limited, row) for row in rows]
    denied = NS(**{**vars(session), 'scope': set()})
    assert not de.matches(denied)
    stage('resolve stored annex and amendment coordinates; verify original blocks')
    query = '금융투자업규정시행세칙 별표10'
    default = sq.resolve(query, matcher, scope)
    cases = [{'name': 'named_annex_in_team_scope', 'query': query, 'result': default}]
    if default['status'] == 'MATCH':
        chosen_docs = {p['document_id'] for p in default['pairs']}
        cases.append({'name': 'annex_denied_by_request_scope', 'query': query,
                      'result': sq.resolve(query, matcher, scope - chosen_docs)})
        cases.append({'name': 'ambiguous_amendment_without_branch',
                      'query': '금융투자업규정시행세칙 부칙',
                      'result': sq.resolve('금융투자업규정시행세칙 부칙', matcher, scope)})
    for did in sorted(origins):
        cases.append({'name': 'version_bound_annex', 'document_id': did,
                      'document_name': matcher.documents[did], 'query': '별표10',
                      'result': sq.resolve('별표10', matcher, scope, document_id=did)})
    relevant_attachments = []
    from semantic_runtime.term_references import ANNEX, annex_coordinate
    from semantic_runtime.document_roles import role_of_metadata
    for did, meta in matcher.document_context.items():
        title = meta.get('document_title', '')
        mention = ANNEX.match(title)
        if ('금융투자업규정시행세칙' in meta.get('folder_names', []) and mention
                and annex_coordinate(mention[1], mention[2].replace('호', '')) == '별표10'
                and role_of_metadata(meta) != 'body'):
            relevant_attachments.append(did)
            cases.append({'name': 'explicit_detached_attachment_title', 'document_id': did,
                          'query': title, 'result': sq.resolve(title, matcher, scope),
                          'orphan_source_count': sum(s['document_id'] == did and s['unit_id'] is None
                                                     for s in matcher.sources.values())})
    from semantic_runtime.legal_agent.tool_availability import article_plan
    plans=[]
    for case in cases:
        if case['name'] in ('named_annex_in_team_scope','explicit_detached_attachment_title'):
            assert case['result']['status']=='MATCH',case
        if case['result']['status']=='MATCH':
            for pair in case['result']['pairs']:
                plan,unavailable=article_plan(session,sq.read_identity(pair))
                assert unavailable is None,(case['name'],pair,unavailable)
                hit,offer=plan
                assert offer['block_ids']
                plans.append({'case':case['name'],'source_id':hit['source_id'],'document_id':hit['document_id'],
                    'offer_id':offer['id'],'block_count':len(offer['block_ids']),'chars':offer['chars'],
                    'coordinate_complete':offer.get('coordinate_complete'),
                    'source_partition':hit.get('source_partition')})
    sources = {}
    for case in cases:
        for sid in case['result']['source_ids']:
            source = tools.sources[sid]
            original = store.sources(source['document_id'], [b['block_id'] for b in source['blocks']])
            assert all(o['text'] == b['text'] and o['source_artifact_sha256'] == source['source_artifact_sha256']
                       for o, b in zip(original, source['blocks'], strict=True))
            assert hashlib.sha256('\n'.join(b['text'] for b in original).encode()).hexdigest() == source['text_sha256']
            sources[sid] = {k: source[k] for k in ('document_id', 'unit_id', 'heading', 'text_sha256', 'source_artifact_sha256')}
            sources[sid].update(block_count=len(original), exact_original_blocks=True)
    references = []
    for item in verified:
        for row in nav.execute('SELECT id,json FROM reference WHERE json_extract(json,\'$.source_id\')=?',
                               (item['definition']['source_id'],)):
            ref = json.loads(row['json'])
            if ANNEX.search(ref.get('locator', '')):
                references.append({k: ref.get(k) for k in ('id', 'document_id', 'source_id', 'locator', 'resolution')}
                                  | {'targets': reference_targets(ref)})
    relevant = origins | target_docs | set(relevant_attachments) | {s['document_id'] for s in sources.values()}
    metadata = {}
    for did in sorted(relevant):
        row = store.db.execute('SELECT name,source_artifact_sha256,json FROM document WHERE document_id=?', (did,)).fetchone()
        meta = json.loads(row['json']).get('document_metadata', {})
        metadata[did] = {'name': row['name'], 'source_artifact_sha256': row['source_artifact_sha256'],
                         'document_metadata': meta, 'in_risk_team_scope': did in scope}
    imports = {}
    for name, module in sorted(sys.modules.items()):
        file = getattr(module, '__file__', None)
        if file and (name.startswith('semantic_runtime') or name.startswith('lawrag')):
            path = Path(file).resolve()
            if path.suffix == '.py':
                rel = str(path.relative_to(CODE))
                assert rel in code_hashes, rel
                imports[name] = {'path': rel, 'sha256': sha(path)}
    store.check_unchanged()
    stage('write supplemental diagnostic record')
    return {'diagnostic_kind': 'actual-source-location; supplemental, not quality certification',
            'limitations': ['Empty unrelated glossary/term catalogue; no free-text retrieval quality tested.',
                            'Scope helper and resolver enforcement tested; authentication/API ACL belongs to separate API checks.',
                            'No model, semantic answer, evidence adoption, acquisition execution, or service startup tested.',
                            'Stored version identity verified; legal applicability and effective date not inferred.'],
            'frozen_code_root': str(CODE.relative_to(ROOT)), 'freeze_sha256': sha(ADR / 'artifacts/design/freeze.json'),
            'data_binding': data, 'generation_id': manifest['generation_id'],
            'store_sha256': manifest['store_sha256'], 'navigation_sha256': nav_manifest['index_sha256'],
            'selection_fingerprint': store.selection.fingerprint, 'risk_scope_count': len(scope),
            'metadata_counts': {'documents': len(matcher.documents), 'units': len(matcher.units), 'sources': len(matcher.sources)},
            'definition_question': question, 'definitions': verified, 'definitions_with_target_scope_removed': limited_rows,
            'definitions_empty_scope': [], 'cases': cases, 'originals': sources,
            'definition_source_annex_references': references, 'documents': metadata, 'read_plans': plans,
            'imports': imports, 'elapsed_seconds': time.monotonic() - started,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'model_calls': 0, 'product_edits': 0}


if __name__ == '__main__':
    try:
        result = run()
    except BaseException as exc:
        (OUT / 'failure.json').write_text(json.dumps({'error_type': type(exc).__name__, 'message': str(exc),
                                                     'elapsed_seconds': time.monotonic() - started}, ensure_ascii=False, indent=2))
        raise
    (OUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'receipt.json').write_text(json.dumps({'script_sha256': sha(__file__), 'result_sha256': sha(OUT / 'result.json'),
                                                 'model_calls': 0, 'product_edits': 0}, indent=2) + '\n')
    print(json.dumps({'status': 'COMPLETED', 'cases': len(result['cases']), 'definition_count': len(result['definitions']),
                      'peak_rss_kib': result['peak_rss_kib'], 'elapsed_seconds': result['elapsed_seconds']}, ensure_ascii=False))
