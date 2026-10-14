"""Native connection/navigation/fulltext rebuild, without authoring or serving packaging."""
from contextlib import closing, contextmanager
import functools
import json
import os
from pathlib import Path
import sqlite3


def prepared(data, run):
    from lawrag.pipeline import genos_stages, glossary_assembly
    from lawrag.pipeline.genos_status import validate_run_id
    from semantic_runtime.contracts import sha
    validate_run_id(run)
    parent = genos_stages.plain_path(Path(data).resolve() / 'TERM_RELEASES' / run)
    plan_path = parent / 'plan.json'; plan = json.loads(plan_path.read_text())
    source = parent / 'sources/store.sqlite'; draft = parent / 'glossary-draft'
    selection_path = parent / 'sources/selection.json'; selection = json.loads(selection_path.read_text())
    report = glossary_assembly.inspect(draft)
    source_sha = sha(source)
    identity = report['document_update']['identity']
    if source_sha != selection['store_sha256'] or source_sha != identity['source_sha256'] or identity['parent_dictionary_sha256'] != plan['glossary_sha256']:
        raise ValueError('Prepared source/dictionary binding mismatch')
    if selection['identity']['exclude_document_ids'] != plan['exclude']:
        raise ValueError('Prepared exclusion scope mismatch')
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        if sorted(r[0] for r in db.execute('SELECT document_id FROM document')) != sorted(selection['document_ids']):
            raise ValueError('Prepared document scope mismatch')
    pins = {str(plan_path): sha(plan_path), str(source): source_sha, str(selection_path): sha(selection_path),
            str(draft / 'report.json'): sha(draft / 'report.json'), str(draft / 'dictionary.sqlite'): report['dictionary_sha256']}
    from lawrag.pipeline import glossary_knowledge
    knowledge = glossary_knowledge.selected_for(draft)
    if knowledge: pins[str(knowledge / 'manifest.json')] = sha(knowledge / 'manifest.json')
    mode = os.environ.get('GENOS_REFERENCE_SCOPE_V2', '0')
    if mode not in {'0', '1'}: raise ValueError('Invalid reference scope mode')
    return {'parent': parent, 'source': source, 'draft': draft, 'selection': selection, 'pins': pins,
            'reindex_policy': 'connections-navigation-fulltext-only-v1', 'reindex_settings': {'reference_scope_v2': mode},
            'knowledge': str(knowledge) if knowledge else None}


def select_completed_glossary(context, directory):
    """Select an explicit completed review derived from this exact prepared glossary."""
    from lawrag.pipeline import document_release, genos_stages, glossary_assembly, glossary_knowledge
    from semantic_runtime.contracts import sha
    directory = genos_stages.plain_path(Path(directory)).resolve(strict=True)
    verified = document_release.verify_glossary(directory)
    report = glossary_assembly.inspect(directory)
    review = report['llm_review']
    if review['source_glossary_sha256'] != sha(context['draft'] / 'dictionary.sqlite'):
        raise ValueError('Completed glossary belongs to another prepared input')
    state = Path(review['state']).resolve(strict=True)
    knowledge = glossary_knowledge.selected_for(directory)
    pins = dict(context['pins'])
    for path in (directory / 'report.json', directory / 'dictionary.sqlite',
                 state / 'completion.json', state / 'review.sqlite'):
        pins[str(path)] = sha(path)
    if knowledge: pins[str(knowledge / 'manifest.json')] = sha(knowledge / 'manifest.json')
    return {**context, 'draft': directory, 'pins': pins,
            'knowledge': str(knowledge) if knowledge else None,
            'reindex_settings': {**context['reindex_settings'], 'completed_glossary': str(directory),
                                'reused_review_status': verified['review_status']}}


@contextmanager
def index_knowledge(log):
    """Validate only files read by native linkage/navigation; never certify unused evidence."""
    from lawrag.pipeline import glossary_knowledge as module
    from semantic_runtime.contracts import sha
    original_verify, original_knowledge = module.verify, module.Knowledge
    cache = {}
    @functools.wraps(original_verify)
    def scoped(directory, *, force=False):
        directory = Path(directory).resolve()
        manifest = json.loads((directory / 'manifest.json').read_text())
        if manifest['schema_version'] != module.VERSION: raise ValueError('Unknown knowledge bundle version')
        rows = {r['path']: r for r in manifest['files']}
        required = ('lookup.sqlite', 'legal.sqlite')
        for name in required:
            row = rows[name]; path = directory / name
            if any(p.is_symlink() for p in (path, *path.parents)): raise ValueError('Knowledge symlink')
            stat = path.stat(); wal = Path(str(path) + '-wal')
            if wal.is_file() and wal.stat().st_size: raise ValueError('Knowledge database has unbound WAL changes')
            identity = (str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
            if force or cache.get(identity) != row['sha256']:
                with log.phase('index-input-database-check', path=str(path), bytes=stat.st_size):
                    if stat.st_size != row['bytes'] or sha(path) != row['sha256']:
                        raise ValueError('Index knowledge payload hash mismatch: ' + name)
                cache[identity] = row['sha256']
        return manifest
    scoped.__code__ = scoped.__code__.replace(co_filename=original_verify.__code__.co_filename)
    class IndexKnowledge(original_knowledge):
        def __init__(self, directory):
            self.directory = Path(directory); self.identity = module.binding(directory)
            self.dbs = {'lookup': module.read_db(self.directory / 'lookup.sqlite')}
    module.verify, module.Knowledge = scoped, IndexKnowledge
    log.emit('knowledge-validation-policy', 'SELECTED', required_files=['lookup.sqlite', 'legal.sqlite'],
             historical_evidence_scan=False, serving_certified=False)
    try: yield
    finally: module.verify, module.Knowledge = original_verify, original_knowledge


def verify(output, pins):
    from semantic_runtime.contracts import sha
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import TermIndex
    from semantic_runtime.fulltext import FulltextIndex
    from semantic_runtime import navigation_storage
    output = Path(output); receipt = json.loads((output / 'release.json').read_text())
    if receipt['pins'] != pins: raise ValueError('Index rebuild input/code selection changed')
    if receipt['settings']['reference_scope_v2'] != os.environ.get('GENOS_REFERENCE_SCOPE_V2', '0'):
        raise ValueError('Index rebuild reference scope setting changed')
    for name, expected in pins.items():
        if sha(name) != expected: raise ValueError('Pinned input changed: ' + name)
    if receipt.get('knowledge'):
        from lawrag.pipeline import glossary_knowledge
        glossary_knowledge.verify(receipt['knowledge'], force=True)
    baseline = output / 'baseline'; result = json.loads((baseline / 'result.json').read_text())
    generation = baseline / 'generation'
    if sha(baseline / 'result.json') != receipt['result_sha256'] or sha(generation / 'manifest.json') != receipt['manifest_sha256']:
        raise ValueError('Index generation receipt mismatch')
    if sha(baseline / 'links/report.json') != receipt['links_report_sha256']:
        raise ValueError('Connection report changed')
    for name, expected in receipt['links_files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or sha(baseline / 'links' / relative) != expected:
            raise ValueError('Connection artifact changed: ' + name)
    with closing(Store(generation)) as store:
        nav = store.manifest['navigation']; navigation = generation / nav['path']
        if sha(navigation / 'manifest.json') != nav['manifest_sha256']: raise ValueError('Navigation manifest drift')
        index = TermIndex(navigation, store)
        if index.manifest['document_count'] != receipt['document_count']:
            raise ValueError('Index document coverage mismatch')
        ft_path = output / 'fulltext'
        if sha(ft_path / 'manifest.json') != receipt['fulltext_manifest_sha256']: raise ValueError('Fulltext manifest drift')
        FulltextIndex(ft_path, index.manifest)
    if result.get('navigation_audit'):
        navigation_storage.verify_audit(baseline / result['navigation_audit']['path'],
            expected_manifest_sha256=result['navigation_audit']['manifest_sha256'],
            expected_index_sha256=index.manifest['index_sha256'])
    return {**receipt, 'generation_path': str(generation), 'fulltext_path': str(ft_path), 'release_path': str(output),
            'unresolved_references': index.manifest.get('unresolved_references'), 'counts': index.manifest['counts']}


def rebuild(context, *, log):
    from genos_reindex_logging import atomic, observe
    from lawrag.pipeline import term_generation
    from semantic_runtime import fulltext
    from semantic_runtime.contracts import sha
    import genos_meaning_variants as variants
    output = context['parent'] / 'reindex'
    pins = context['pins']
    with variants.locked(output / '.lock'), observe(log), index_knowledge(log):
        if (output / 'release.json').is_file():
            with log.phase('verify-completed-index'): return verify(output, pins)
        scope = {'document_version_ids': context['selection']['document_ids'],
                 'source_selection_sha256': sha(context['parent'] / 'sources/selection.json')}
        with log.phase('connections-and-navigation', model_calls=0, serving_bundle_copy=False):
            result = term_generation.build_generation(context['source'], context['draft'], output / 'baseline', serving=False, scope=scope)
        fulltext_path = output / 'fulltext'
        if fulltext_path.exists() and not (fulltext_path / 'manifest.json').is_file():
            import os, time
            retained = output / ('incomplete-fulltext-' + str(time.time_ns()))
            os.rename(fulltext_path, retained)
            log.emit('fulltext-resume', 'RETAINED', path=str(retained), navigation_reused=True)
        with log.phase('fulltext-index-only', navigation_reused=True):
            if not (fulltext_path / 'manifest.json').is_file():
                fulltext.build(output / 'baseline/generation/navigation', fulltext_path)
        receipt = {'schema_version': 'genos-connections-index-only-v1', 'completed': True, 'pins': pins,
                   'knowledge': context.get('knowledge'), 'settings': context['reindex_settings'],
                   'document_count': len(scope['document_version_ids']), 'model_calls': 0, 'meaning_review': 'NOT_RUN',
                   'reference_model_review': 'NOT_RUN', 'reference_policy': 'native-rules; ambiguity remains unresolved',
                   'serving_packaged': False, 'serving_verified': False, 'activated': False,
                   'historical_evidence_validated': False, 'knowledge_validation': 'lookup.sqlite + legal.sqlite only',
                   'manifest_sha256': sha(output / 'baseline/generation/manifest.json'),
                   'links_report_sha256': sha(output / 'baseline/links/report.json'),
                   'links_files': json.loads((output / 'baseline/links/report.json').read_text())['files'],
                   'fulltext_manifest_sha256': sha(fulltext_path / 'manifest.json'),
                   'result_sha256': sha(output / 'baseline/result.json')}
        atomic(output / 'release.json', receipt)
        try:
            with log.phase('verify-new-connections-and-index'): verified = verify(output, pins)
        except BaseException:
            (output / 'release.json').rename(output / ('failed-verification-' + str(__import__('time').time_ns()) + '.json'))
            raise
        log.emit('reindex', 'VERIFIED', documents=receipt['document_count'], model_calls=0,
                 generation=verified['generation_path'], fulltext=verified['fulltext_path'], serving_packaged=False)
        return verified


def rebuild_serving(context, *, log):
    """Rebuild downstream assets from pinned prepared inputs; never invoke authoring."""
    import importlib.util
    from genos_reindex_logging import atomic, observe
    import genos_meaning_variants as variants
    from lawrag.pipeline import glossary_knowledge, term_generation, term_serving_bundle
    from semantic_runtime.contracts import sha
    output = context['parent'] / 'serving'
    settings = context['reindex_settings']
    if not settings.get('serving') or settings.get('fulltext_granularity') not in {'article', 'unit'}:
        raise ValueError('Explicit serving and fulltext granularity required')
    if settings['reference_scope_v2'] != os.environ.get('GENOS_REFERENCE_SCOPE_V2', '0'):
        raise ValueError('Reference scope setting changed')
    if not context.get('knowledge'):
        raise ValueError('Completed full knowledge bundle required for serving reuse')
    code_root = Path(context['code_root']).resolve(strict=True)
    gate_path = code_root / '06_TOOLS/COMMANDS/genos_generation_e2e.py'
    gate_spec = importlib.util.spec_from_file_location('prepared_serving_gate', gate_path)
    gate = importlib.util.module_from_spec(gate_spec)
    gate_spec.loader.exec_module(gate)

    def check_pins():
        for name, expected in context['pins'].items():
            if sha(name) != expected:
                raise ValueError('Pinned prepared input/code changed: ' + name)

    with variants.locked(output / '.lock'), observe(log):
        with log.phase('verify-full-prepared-inputs'):
            check_pins()
            glossary_knowledge.verify(context['knowledge'], force=True)
        receipt_path = output / 'release.json'
        previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        if previous and (previous['pins'] != context['pins'] or previous['settings'] != settings):
            raise ValueError('Serving output inputs/code/settings changed; use another run ID')
        scope = {'document_version_ids': context['selection']['document_ids'],
                 'source_selection_sha256': sha(context['parent'] / 'sources/selection.json')}
        with log.phase('reuse-inputs-build-serving', model_calls=0):
            worker_options = {'fulltext_workers': settings['fulltext_workers']} if 'fulltext_workers' in settings else {}
            result = term_generation.build_generation(context['source'], context['draft'], output / 'baseline',
                serving=True, scope=scope, fulltext_granularity=settings['fulltext_granularity'],
                storage_profile=settings.get('storage_profile','legacy'), audit_profile=settings.get('audit_profile','materialized'), **worker_options)
        generation = output / 'baseline/generation'
        with log.phase('verify-serving-assets'):
            term_serving_bundle.verify_assets(generation)
            gate_result = gate.audit(code_root, generation)
            if gate_result['status'] != 'PASS':
                atomic(output / ('failed-e2e-' + str(__import__('time').time_ns()) + '.json'), gate_result)
                raise ValueError('Offline generation E2E failed; inspect failed-e2e-*.json')
            if previous:
                if json.loads((output / 'offline-e2e.json').read_text()) != gate_result:
                    raise ValueError('Completed offline E2E binding changed')
            else:
                atomic(output / 'offline-e2e.json', gate_result)
            check_pins()
        links = json.loads((output / 'baseline/links/report.json').read_text())
        for name, expected in links['files'].items():
            path = (output / 'baseline/links' / name).resolve()
            path.relative_to((output / 'baseline/links').resolve())
            if sha(path) != expected:
                raise ValueError('Connection artifact changed: ' + name)
        receipt = {'schema_version': 'genos-prepared-reuse-serving-v1', 'completed': True,
                   'pins': context['pins'], 'settings': settings,
                   'knowledge': context['knowledge'], 'document_count': len(scope['document_version_ids']),
                   'model_calls': 0, 'meaning_review': 'REUSED_NOT_RERUN', 'reference_model_review': 'NOT_RUN',
                   'reference_policy': 'native-rules; ambiguity remains unresolved',
                   'serving_packaged': True, 'serving_verified': True, 'historical_evidence_validated': True,
                   'offline_e2e': 'PASS', 'live_workflow_e2e': 'NOT_RUN', 'quality_certified': False,
                   'activated': False, 'generation_path': str(generation),
                   'manifest_sha256': sha(generation / 'manifest.json'),
                   'result_sha256': sha(output / 'baseline/result.json'),
                   'links_report_sha256': sha(output / 'baseline/links/report.json'),
                   'offline_e2e_sha256': sha(output / 'offline-e2e.json')}
        if previous and previous != receipt:
            raise ValueError('Completed serving receipt changed; previous receipt preserved')
        if not previous:
            atomic(receipt_path, receipt)
        log.emit('serving-reuse', 'OFFLINE_READY', generation=str(generation),
                 documents=receipt['document_count'], model_calls=0, live_workflow_e2e='NOT_RUN', activated=False)
        return receipt


def publish_serving(context, shared_root, *, log):
    """Copy only a completed verified generation to a new shared path; no pointer writes."""
    import shutil
    import tempfile
    import genos_meaning_variants as variants
    from genos_reindex_logging import atomic
    from lawrag.pipeline import genos_stages, term_serving_bundle
    from semantic_runtime.contracts import sha
    release = context['parent'] / 'serving'
    if not (release / 'release.json').is_file():
        raise ValueError('Complete the serving build before shared publication')
    verified = rebuild_serving(context, log=log)
    source = Path(verified['generation_path'])
    root = genos_stages.plain_path(shared_root).resolve(strict=True)
    if root == source or root in source.parents or source in root.parents:
        raise ValueError('Shared root must be separate from the built generation')
    target = root / context['parent'].name
    identity = {'schema_version': 'genos-prepared-reuse-shared-v1',
                'release_sha256': sha(release / 'release.json'), 'source_generation': str(source),
                'manifest_sha256': verified['manifest_sha256'],
                'files': genos_stages.files_hashes(source), 'activated': False}
    with variants.locked(root / ('.' + context['parent'].name + '.publish.lock')):
        if target.exists():
            if (json.loads((target / 'share-receipt.json').read_text()) != identity or
                    genos_stages.files_hashes(target / 'generation') != identity['files']):
                raise ValueError('Shared generation differs; previous publication preserved')
        else:
            temporary = Path(tempfile.mkdtemp(prefix='.' + target.name + '-', dir=root))
            try:
                with log.phase('copy-verified-generation-to-shared', target=str(target)):
                    shutil.copytree(source, temporary / 'generation')
                    if genos_stages.files_hashes(temporary / 'generation') != identity['files']:
                        raise ValueError('Shared generation copy mismatch')
                    term_serving_bundle.verify_assets(temporary / 'generation')
                    atomic(temporary / 'share-receipt.json', identity)
                    os.rename(temporary, target)
            except BaseException:
                shutil.rmtree(temporary)
                raise
        term_serving_bundle.verify_assets(target / 'generation')
        result = {'published': True, 'activated': False, 'generation_path': str(target / 'generation'),
                  'manifest_sha256': verified['manifest_sha256'], 'live_workflow_e2e': 'NOT_RUN'}
        atomic(context['parent'] / 'shared-publication.json', result)
        log.emit('shared-publication', 'VERIFIED', **result)
        return result
