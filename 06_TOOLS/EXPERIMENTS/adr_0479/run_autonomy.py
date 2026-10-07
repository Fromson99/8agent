"""Single autonomous Qwen CM003 component-path probe. No scripted choices or gold input."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0479-bounded-linked-evidence'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0479/linked-context'
MODEL = 'qwen/qwen3.5-122b-a10b'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def pin():
    freeze = read(ADR / 'artifacts/frozen-design.json')
    for p, value in freeze['file_hashes'].items():
        if sha(ROOT / p) != value:
            raise RuntimeError('Frozen input changed: ' + p)
    rev = next(r for r in read(CAND / 'candidate.json')['revisions'] if r['revision_id'] == 'rev-001')
    for row in rev['files']:
        if sha(ROOT / row['frozen_path']) != row['snapshot_sha256']:
            raise RuntimeError('Frozen candidate changed')
    frozen = CAND / 'revisions/rev-001/snapshot/02_BACKEND'
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    sys.path.insert(0, str(frozen))
    # lawrag is a regular package: pin its research namespace explicitly without copying unrelated code.
    import lawrag.research
    lawrag.research.__path__.insert(0, str(frozen / 'lawrag/research'))
    return freeze, frozen


def authorize(fixture, freeze):
    auth = freeze['export_authorization']
    manifest_path = ROOT / fixture['generation'] / 'manifest.json'
    manifest = read(manifest_path)
    if not auth['authorized'] or auth['model'] != MODEL or auth['destination'] != 'https://openrouter.ai/api/v1':
        raise RuntimeError('Explicit model/destination approval required')
    if manifest['store_sha256'] != auth['source_store_sha256'] or sha(ROOT / fixture['generation'] / 'store.sqlite') != auth['source_store_sha256']:
        raise RuntimeError('Approved source fingerprint differs')
    if sorted(fixture['public_scope_document_ids']) != auth['scope_document_ids']:
        raise RuntimeError('Source scope differs from approved fixture')
    return auth, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    freeze, frozen = pin()
    fixture = read(ADR / 'fixture.json')
    auth, source_manifest = authorize(fixture, freeze)
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.legal_agent.domain import DEFAULT_PROFILE, profile
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.repository import WorkRepository
    from semantic_runtime.legal_agent.source_tools import SourceSession
    from semantic_runtime.legal_agent.source_first_protocol import DOMAIN, NAVIGATION, FEEDBACK_POLICY, LINKED_CONTEXT_POLICY
    from semantic_runtime.legal_agent.source_first_gateway import SourceFirstGateway
    from semantic_runtime.legal_agent.source_first_session import SourceFirstSession
    from semantic_runtime.contracts import digest
    from lawrag.research.experiment_client import OpenRouterProxyClient
    from lawrag.research.openrouter_legal_adapter import OpenRouterSingleSendAdapter
    import semantic_runtime.legal_agent.source_first_session as implementation
    import lawrag.research.experiment_client as client_module
    assert Path(implementation.__file__).is_relative_to(frozen)
    assert Path(client_module.__file__).is_relative_to(frozen)
    if not args.execute:
        print(json.dumps({'preflight': 'pass', 'network_calls': 0, 'scope_documents': len(fixture['public_scope_document_ids']), 'model': MODEL}))
        return
    out = ADR / 'artifacts/run-001'
    out.mkdir(exist_ok=False)  # Never clobber or silently repeat a paid run.
    client = OpenRouterProxyClient(ROOT, out / 'calls', model=MODEL, max_calls=14,
                                   max_output_tokens=2800, schema_in_prompt=False, max_repairs=0)
    wire = OpenRouterSingleSendAdapter(client)
    settings = profile({**DEFAULT_PROFILE, 'model_binding': wire.binding}, require_model=True)
    start = time.monotonic()
    store = repo = session = None
    output = {'case_id': 'cm-003', 'arm': 'linked-context', 'model': MODEL,
              'main_wiring': 'unchanged', 'quality_certified': False, 'error': None}
    try:
        store = Store(ROOT / fixture['generation'])
        p = Pipeline(ROOT, store, implementation='legal-agent-v1', legal_agent_profile=settings, legal_agent_transport=wire)
        query = p.plan(fixture['question'], fixture['public_scope_document_ids'])
        request = {'question': fixture['question'], 'document_ids': fixture['public_scope_document_ids'], 'use_llm': True}
        source_agent = ServingDocumentAgent(p, p.term_agent.config)
        with source_agent.resources(query['scope']['document_version_ids']) as (index, tools, glossary, matcher):
            binding = {'generation_id': store.manifest['generation_id'], 'store_sha256': store.manifest['store_sha256'],
                       'source_export_allowed': store.manifest['export_allowed'], 'export_allowed': True,
                       'authorization_sha256': digest(auth), 'scope': query['scope'], 'model': wire.binding,
                       'domain_sha256': digest(DOMAIN), 'profile_sha256': digest(settings),
                       'navigation_policy': NAVIGATION, 'feedback_policy_sha256': digest(FEEDBACK_POLICY),
                       'linked_context_policy_sha256': digest(LINKED_CONTEXT_POLICY),
                       'index_sha256': index.manifest['index_sha256'], 'glossary': glossary.binding,
                       'fulltext_sha256': matcher.fulltext.manifest['fulltext_sha256']}
            context = RequestContext.create(query, request, binding, settings['wall_seconds'])
            repo = WorkRepository(out / 'journal.sqlite', context, settings)
            sources = SourceSession(store, tools, glossary, matcher, repo, context, settings)
            gateway = SourceFirstGateway(repo, context, settings, DOMAIN, wire)
            session = SourceFirstSession(context, repo, sources, gateway, settings, store.manifest['data_status'])
            # Same production controller components and phase transitions, not an API/publication test.
            session.check_sources_unchanged = glossary.check_unchanged
            retrieval = session.investigate()
            selected = session.select({'request': request, 'query': query, 'retrieval': retrieval})
            assembled = {'request': request, 'query': query, 'retrieval': retrieval,
                         'selection': selected, 'assembly': session.assemble()}
            for _ in range(settings['max_cycles'] + 1):
                result, control = session.answer_and_review(assembled)
                if control['decision'] == 'FINAL':
                    break
                if control['decision'] == 'RESEARCH':
                    retrieval = session.investigate()
                    selected = session.select({'retrieval': retrieval})
                    assembled = {'request': request, 'query': query, 'retrieval': retrieval,
                                 'selection': selected, 'assembly': session.assemble()}
            else:
                raise RuntimeError('Controller did not reach FINAL within frozen cycle cap')
            output.update(result=result, control=control)
            glossary.check_unchanged()
    except Exception as exc:
        output['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        if repo is not None:
            repo.fail(getattr(exc, 'code', type(exc).__name__))
    finally:
        if repo is not None:
            output.update(budget=repo.budget(), journal_run=repo.run())
            dump = {name: [dict(row) for row in repo.db.execute('SELECT * FROM ' + name)]
                    for name in ('event', 'model_attempt', 'model_view', 'presentation_receipt')
                    if repo.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()}
            write(out / 'journal-tables.json', dump)
            if session is not None:
                write(out / 'trace.json', {'cards': list(session.nav.cards.values()), 'evidence': repo.evidence(),
                                         'selected_evidence_ids': sorted(session.selected), 'packed': session.packed, 'aliases': session.ev_alias,
                                         'observations': repo.observations(10000), 'heads': repo.heads(),
                                         'limitations': session.limitations, 'recovery_used': session.recovery_used,
                                         'progress_notice': session.progress_notice,
                                         'last_action_results': session.last_action_results})
                session.close()
            repo.close()
        if store is not None:
            store.close()
        output.update(physical_calls=client.calls, usage=client.usage, seconds=round(time.monotonic() - start, 3))
        output['source_manifest_unchanged'] = read(ROOT / fixture['generation'] / 'manifest.json') == source_manifest
        write(out / 'result.json', output)
    print(json.dumps({'physical_calls': client.calls, 'error': output['error'],
                      'claim_count': len(output.get('result', {}).get('answer', {}).get('claims', [])),
                      'seconds': output['seconds']}, ensure_ascii=False))


if __name__ == '__main__':
    main()


