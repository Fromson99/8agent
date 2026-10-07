"""Join selected document builds, review existing and new definitions, and prepare a serving DRAFT.

No implicit base discovery or activation. GENOS pointer changes require explicit
confirmation and compare-and-swap; completed generations are never rewritten.
"""
import argparse
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
import uuid

from semantic_runtime.contracts import sha, digest, write
from semantic_runtime.storage import Store, TABLES
from . import glossary_linking, glossary_review, glossary_document_update
from . import genos_stages
from .term_generation import build_generation
from .term_serving_bundle import verify_assets


def verify_fulltext_binding(build, binding):
    """Verify an explicit legacy profile binding without selecting another reader."""
    build = Path(build).resolve()
    generation = build / 'generation'
    manifest = json.loads((generation / 'manifest.json').read_text())
    nav = generation / manifest['navigation']['path']
    index = json.loads((nav / 'manifest.json').read_text())
    path = (generation / binding['path']).resolve()
    path.relative_to(generation)
    if sha(path / 'manifest.json') != binding['manifest_sha256']:
        raise ValueError('Legacy fulltext manifest changed')
    value = json.loads((path / 'manifest.json').read_text())
    if (value['navigation_index_sha256'] != binding['navigation_index_sha256']
            or value['source_store_sha256'] != index['source_store_sha256']
            or value['generation_id'] != index['generation_id']):
        raise ValueError('Legacy fulltext source/index binding mismatch')
    if sha(path / 'fulltext.sqlite') != value['fulltext_sha256']:
        raise ValueError('Legacy fulltext payload changed')
    return value, index


def rebind_fulltext(build, binding, output):
    """Derive immutable build metadata for an explicitly pinned legacy fulltext."""
    from semantic_runtime.navigation_storage import verify_build
    build, output = Path(build).resolve(), Path(output).resolve()
    if build == output or build.is_relative_to(output) or output.is_relative_to(build):
        raise ValueError('Fulltext binding output must be separate from its parent')
    identity = {'parent_build': str(build), 'parent_result_sha256': sha(build / 'result.json'),
                'fulltext_binding': binding, 'compiler_sha256': sha(__file__)}
    if output.exists():
        result = verify_build(output)
        if result['identity'] != identity:
            raise ValueError('Fulltext binding inputs changed; use a new output')
        value, index = verify_fulltext_binding(output, result['fulltext_binding'])
        if value['navigation_index_sha256'] != index['index_sha256']:
            raise ValueError('Rebound fulltext/navigation mismatch')
        return result
    verify_build(build)
    value, index = verify_fulltext_binding(build, binding)
    if value['navigation_index_sha256'] not in {
            index['index_sha256'], index.get('storage', {}).get('pre_split_index_sha256')}:
        raise ValueError('Legacy fulltext does not belong to the compact parent')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.' + output.name + '-', dir=output.parent))
    try:
        def copy(src, dst):
            if Path(src).suffix == '.json':
                return shutil.copyfile(src, dst)
            try:
                os.link(src, dst)
                return dst
            except OSError:
                return shutil.copyfile(src, dst)
        shutil.copytree(build / 'generation', temporary / 'generation', copy_function=copy)
        shutil.copytree(build / 'audit', temporary / 'audit', copy_function=copy)
        fulltext = temporary / 'generation' / binding['path']
        value['navigation_index_sha256'] = index['index_sha256']
        (fulltext / 'manifest.json').unlink()
        write(fulltext / 'manifest.json', value)
        updated = {**binding, 'manifest_sha256': sha(fulltext / 'manifest.json'),
                   'navigation_index_sha256': index['index_sha256']}
        result = {**json.loads((build / 'result.json').read_text()),
                  'schema_version': 'navigation-storage-fulltext-rebind-v1',
                  'identity': identity, 'fulltext_binding': updated,
                  'activated': False, 'quality_certified': False}
        manifest_path = temporary / 'generation/manifest.json'
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('fulltext'):
            manifest['fulltext'] = {**manifest['fulltext'], **updated}
            manifest_path.unlink()
            write(manifest_path, manifest)
            result['manifest_sha256'] = sha(manifest_path)
        # Legacy generations retain their profile-owned fulltext contract.
        # Consumers must pin result.fulltext_binding in the selected release config.
        write(temporary / 'result.json', result)
        verify_fulltext_binding(temporary, updated)
        if sha(build / 'result.json') != identity['parent_result_sha256']:
            raise ValueError('Parent build changed during fulltext rebinding')
        if output.exists():
            raise ValueError('Fulltext binding output appeared during execution')
        os.rename(temporary, output)
        return result
    except BaseException:
        shutil.rmtree(temporary)
        raise


def _verify_navigation_audit(build):
    """Release/resume/publish validates build evidence; requests need only generation."""
    build = Path(build).resolve()
    result = json.loads((build / 'result.json').read_text())
    generation = build / 'generation'
    manifest = json.loads((generation / 'manifest.json').read_text())
    navigation = (generation / manifest['navigation']['path']).resolve()
    navigation.relative_to(generation)
    index = json.loads((navigation / 'manifest.json').read_text())
    if index.get('storage') or result.get('navigation_audit'):
        from semantic_runtime import navigation_storage
        navigation_storage.verify_build(build)


def _copy_reference_audit(baseline, serving):
    """Preserve immutable construction bytes and bind the approved overlay lineage."""
    baseline, serving = Path(baseline).resolve(), Path(serving).resolve()
    result = json.loads((baseline / 'result.json').read_text())
    if not result.get('navigation_audit'):
        return None
    from semantic_runtime import navigation_storage
    navigation_storage.verify_build(baseline)
    generation = serving / 'generation'
    manifest = json.loads((generation / 'manifest.json').read_text())
    navigation = (generation / manifest['navigation']['path']).resolve()
    navigation.relative_to(generation)
    index = json.loads((navigation / 'manifest.json').read_text())
    apply_file = navigation / 'reference-resolution-apply.json'
    applied = json.loads(apply_file.read_text())
    original = baseline / 'audit/navigation'
    audit = json.loads((original / 'manifest.json').read_text())
    if (applied['parent_index_sha256'] != audit['serving_index_sha256']
            or applied['output_index_sha256'] != index['index_sha256']
            or sha(apply_file) != index['reference_resolution']['apply_receipt_sha256']):
        raise ValueError('Reference overlay audit lineage mismatch')
    target = serving / 'audit/navigation'
    target.mkdir(parents=True)
    try:
        os.link(original / 'navigation.sqlite', target / 'navigation.sqlite')
    except OSError:
        shutil.copyfile(original / 'navigation.sqlite', target / 'navigation.sqlite')
    audit = {**audit, 'serving_index_sha256': index['index_sha256'],
             'serving_index_bytes': (navigation / 'navigation.sqlite').stat().st_size,
             'parent_audit_manifest_sha256': sha(original / 'manifest.json'),
             'reference_resolution_apply_receipt_sha256': sha(apply_file),
             'reference_resolution_parent_index_sha256': applied['parent_index_sha256']}
    write(target / 'manifest.json', audit)
    index['storage'] = {**index['storage'], 'audit_manifest_sha256': sha(target / 'manifest.json')}
    (navigation / 'manifest.json').unlink()
    write(navigation / 'manifest.json', index)
    manifest['navigation'] = {**manifest['navigation'], 'manifest_sha256': sha(navigation / 'manifest.json')}
    (generation / 'manifest.json').unlink()
    write(generation / 'manifest.json', manifest)
    return {'path': 'audit/navigation', 'manifest_sha256': sha(target / 'manifest.json')}


def merge_sources(sources, output, *, exclude=()):
    sources = [genos_stages.plain_path(p).resolve() for p in sources]
    output = Path(output)
    identity = {'sources': [{'path': str(p), 'sha256': sha(p)} for p in sources],
                'exclude_document_ids': sorted(set(exclude)), 'compiler_sha256': sha(__file__)}
    if output.exists():
        receipt = json.loads((output / 'selection.json').read_text())
        if receipt['identity'] != identity or receipt['store_sha256'] != sha(output / 'store.sqlite'):
            raise ValueError('Integrated source selection changed; use a new run ID')
        return output / 'store.sqlite'
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.' + output.name, dir=output.parent))
    try:
        seen, excluded = {}, set()
        with closing(sqlite3.connect(temp / 'store.sqlite')) as db:
            db.executescript('''
              CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
              CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT,PRIMARY KEY(document_id,unit_id));
              CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT,PRIMARY KEY(document_id,block_id));
            ''')
            for path in sources:
                with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
                    for doc in source.execute('SELECT * FROM document ORDER BY document_id'):
                        did = doc[0]
                        if did in exclude:
                            excluded.add(did); continue
                        rows = {'document': [doc]}
                        for table, order in [('source_unit', 'unit_id'), ('source_block', 'block_id')]:
                            rows[table] = source.execute(f'SELECT * FROM {table} WHERE document_id=? ORDER BY {order}', (did,)).fetchall()
                        fingerprint = digest(rows)
                        if did in seen:
                            if seen[did] != fingerprint:
                                raise ValueError('Conflicting document version ID: ' + did)
                            continue
                        seen[did] = fingerprint
                        for table in TABLES:
                            if rows[table]:
                                db.executemany(f'INSERT INTO {table} VALUES (' + ','.join('?' * len(rows[table][0])) + ')', rows[table])
            if set(exclude) != excluded:
                raise ValueError('Excluded document is not in the explicit selection')
            if not seen:
                raise ValueError('Empty integrated source selection')
            db.commit()
        for item in identity['sources']:
            if sha(item['path']) != item['sha256']:
                raise ValueError('Source changed during integration')
        write(temp / 'selection.json', {'identity': identity, 'document_ids': sorted(seen),
                                       'document_hashes': seen, 'store_sha256': sha(temp / 'store.sqlite')})
        os.rename(temp, output)
        return output / 'store.sqlite'
    except BaseException:
        shutil.rmtree(temp)
        raise


def selected_sources(data, run_id, bases):
    from .structure_selection import verify_origin
    path = genos_stages.plain_path(data / 'LOGS' / run_id / 'structure-selection.json')
    selection = json.loads(path.read_text())
    paths, pins = verified_structures(data, selection)
    pins.update({str(path): sha(path), **verify_origin(path.parent, selection)})
    base_paths = []
    for base in bases:
        base = genos_stages.plain_path(base).resolve()
        with closing(Store(base)):
            pass
        pins[str(base / 'manifest.json')] = sha(base / 'manifest.json')
        base_paths.append(base / 'store.sqlite')
    return base_paths + paths, pins


def verified_structures(data, selection):
    """Shared receipt verification for full runs and explicit success-only snapshots."""
    if selection.get('schema_version') != 'structure-selection-v1' or not selection['documents']:
        raise ValueError('Completed structure selection is required')
    if (selection.get('completed') is not True or selection.get('input_inventory_valid', True) is not True
            or set(selection.get('expected_document_ids', [])) != set(selection['documents'])):
        raise ValueError('Structure selection is incomplete; rerun structure before release')
    paths, pins = [], {}
    for did, value in sorted(selection['documents'].items()):
        if not re.fullmatch(r'[0-9a-f]{64}', value['key']):
            raise ValueError('Invalid structure selection key')
        folder = data / 'STRUCTURE' / value['key']
        receipt = folder / 'structure-receipt.json'
        if sha(receipt) != value['receipt_sha256']:
            raise ValueError('Selected structure receipt changed')
        genos_stages.verify_structure(folder)
        with closing(sqlite3.connect((folder / 'source.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
            if {r[0] for r in db.execute('SELECT document_id FROM document')} != {did}:
                raise ValueError('Structure selection document mismatch')
        paths.append(folder / 'source.sqlite')
        pins[str(receipt)] = sha(receipt)
    return paths, pins


def build(data, run_id, glossary, *, bases=(), exclude=(), max_jobs=100, retry_failed=False,
          prepare_only=False, provider=None, reference_state=None, reference_profile=None,
          max_reference_cases=10000, reference_batch_size=8, stage='build', glossary_corpus_policy='append'):
    """One implementation for merge / prepare / review / index and automatic build.

    Explicit index never executes model work. references consumes completed glossary review.
    prepare retains its existing merge+draft+review-plan behavior.
    """
    if prepare_only:
        stage = 'prepare'
    if stage not in {'merge', 'prepare', 'review', 'references', 'index', 'build'}:
        raise ValueError('Unknown release stage: ' + stage)
    reference_profile = reference_profile or os.environ.get('REFERENCE_RESOLUTION_PROFILE')
    if reference_profile and reference_state:
        raise ValueError('Select a reference model profile or an existing review state, not both')
    if not 1 <= max_reference_cases <= 10000 or not 1 <= reference_batch_size <= 32:
        raise ValueError('invalid reference batch or case limit')
    reference_model = None
    if reference_profile:
        reference_profile = genos_stages.plain_path(reference_profile).resolve()
        reference_model = {'profile': str(reference_profile), 'sha256': sha(reference_profile),
                           'approval_mode': 'automatic'}
    if stage == 'references' and not reference_profile:
        raise ValueError('references requires --reference-model-profile or REFERENCE_RESOLUTION_PROFILE')
    if glossary_corpus_policy not in {'append', 'replace'}:
        raise ValueError('Unknown glossary corpus policy')
    index_started = time.monotonic()
    def index_progress(phase):
        if stage == 'index':
            print(f'RELEASE INDEX {phase} elapsed={time.monotonic()-index_started:.1f}s', flush=True)
    index_progress('select-sources.start')
    data = genos_stages.plain_path(data).resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', run_id):
        raise ValueError('Invalid run ID')
    sources, pins = selected_sources(data, run_id, bases)
    index_progress('select-sources.done')
    destination = data / 'TERM_RELEASES' / run_id
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if stage in {'review', 'references', 'index'} and not (destination / 'review/review.sqlite').is_file():
            raise ValueError('Run document-release prepare first')
        if stage in {'references', 'index'} and not (destination / 'review/completion.json').is_file():
            raise ValueError('Run document-release review to completion first')
        from . import glossary_assembly
        reference_binding = None
        if reference_state is not None:
            from . import reference_resolution
            reference_state = genos_stages.plain_path(reference_state).resolve()
            status = reference_resolution.auto_approve(reference_state)
            blocking = sum(status['cases'].get(state, 0) for state in
                           ('CANDIDATES_READY', 'MODEL_PENDING', 'MODEL_FAILED', 'MODEL_UNKNOWN', 'VALIDATED'))
            if blocking:
                return {'completed': False, 'status': 'REFERENCE_REVIEW_PENDING',
                        'reference_review': status, 'path': str(destination)}
            reference_binding = {'state': str(reference_state),
                                 'state_sha256': sha(reference_state / 'review.sqlite'),
                                 'schema_version': status['schema_version']}
        identity = {'pins': pins, 'glossary_sha256': glossary_assembly.inspect(glossary)['dictionary_sha256'],
                    'exclude': sorted(set(exclude)), 'compiler_sha256': sha(__file__),
                    'reference_review': reference_binding}
        if reference_model:
            identity['reference_model'] = reference_model
        if glossary_corpus_policy != 'append':
            identity['glossary_corpus_policy'] = glossary_corpus_policy
        plan = destination / 'plan.json'
        if plan.exists() and json.loads(plan.read_text()) != identity:
            raise ValueError('Release inputs changed; use a new run ID')
        if not plan.exists():
            write(plan, identity)
        index_progress('merge-sources.start')
        source = merge_sources(sources, destination / 'sources', exclude=exclude)
        index_progress('merge-sources.done')
        origin_path = data / 'LOGS' / run_id / 'selection-origin.json'
        coverage = None
        if str(origin_path) in pins:
            origin = json.loads(origin_path.read_text())
            coverage = {key: origin[key] for key in
                        ('parent_run_id', 'parent_attempt_id', 'coverage', 'omitted_count')}
            coverage['origin_sha256'] = sha(origin_path)
            coverage['selected_count'] = len(origin['selected_document_ids'])
        def stopped(status, **details):
            for path, expected in pins.items():
                if sha(path) != expected:
                    raise ValueError('Release input changed during preparation')
            return {'completed': False, 'stage': stage, 'stage_completed': True,
                    'status': status, 'path': str(destination), 'activated': False,
                    **({'structure_coverage': coverage} if coverage else {}), **details}
        if stage == 'merge':
            return stopped('MERGED', source=str(source))
        index_progress('prepare-glossary-draft.start')
        glossary_document_update.augment(glossary, source, destination / 'glossary-draft',
                                         corpus_policy=glossary_corpus_policy)
        index_progress('prepare-glossary-draft.done')
        state, reviewed = destination / 'review', destination / 'glossary-reviewed'
        if not state.exists():
            glossary_review.prepare(destination / 'glossary-draft', state)
        if stage == 'prepare':
            return stopped('PREPARED', review=glossary_review.inspect(state))
        if stage in {'references', 'index'}:
            index_progress('verify-review.start')
            # Reading the verified completion is deliberately separate from complete():
            # this command cannot create a provider or make a model request.
            verify_glossary(reviewed)
            review = json.loads((state / 'completion.json').read_text())
            if review['source_glossary_sha256'] != glossary_assembly.inspect(
                    destination / 'glossary-draft')['dictionary_sha256']:
                raise ValueError('Reviewed glossary belongs to a different draft')
            index_progress('verify-review.done')
        else:
            review = glossary_review.complete(destination / 'glossary-draft', state, reviewed,
                                             max_jobs=max_jobs, retry_failed=retry_failed, provider=provider)
        if not review['completed']:
            return stopped('REVIEW_PENDING', stage_completed=False, review=review)
        if stage == 'review':
            return stopped('REVIEWED', review=review)
        if (destination / 'release.json').exists():
            generation, receipt = verify_release(destination)
            index_progress('verify-existing-release.done')
            return {**receipt, 'path': str(destination), 'generation_path': str(generation), 'cached': True}
        selection_path = destination / 'sources/selection.json'
        selection = json.loads(selection_path.read_text())
        scope = {'document_version_ids': selection['document_ids'], 'source_selection_sha256': sha(selection_path)}
        if reference_state is None and reference_profile is None:
            index_progress('build-generation.start')
            result = build_generation(source, reviewed, destination / 'serving', serving=True, scope=scope)
            index_progress('build-generation.done')
            generation = destination / 'serving/generation'
            reference_apply = None
        else:
            from . import reference_resolution
            baseline = build_generation(source, reviewed, destination / 'serving-baseline', serving=True, scope=scope)
            if reference_profile:
                reference_state = destination / 'reference-review'
                reference_status = reference_resolution.advance(
                    destination / 'serving-baseline/generation', reference_state, reference_profile,
                    execute=stage in {'build', 'references'}, max_cases=max_reference_cases,
                    batch_size=reference_batch_size)
                if not reference_status['completed']:
                    return stopped('REFERENCE_RESOLUTION_PENDING', stage_completed=False,
                                   reference_resolution=reference_status)
                reference_binding = {'state': str(reference_state),
                                     'state_sha256': sha(reference_state / 'review.sqlite'),
                                     'schema_version': reference_status['schema_version']}
                if stage == 'references':
                    return stopped('REFERENCES_READY', reference_resolution=reference_status)
            serving = destination / 'serving'
            if serving.exists():
                raise ValueError('reference overlay serving output already exists')
            serving.mkdir()
            reference_apply = reference_resolution.apply(
                reference_state, destination / 'serving-baseline/generation', serving / 'generation')
            audit = _copy_reference_audit(destination / 'serving-baseline', serving)
            generation = serving / 'generation'
            generated_manifest = json.loads((generation / 'manifest.json').read_text())
            result = {**baseline, 'identity': {**baseline['identity'], 'reference_review': reference_binding},
                      'generation': 'generation', 'manifest_sha256': sha(generation / 'manifest.json'),
                      'navigation': generated_manifest['navigation'], 'reference_resolution': reference_apply}
            if audit:
                result['navigation_audit'] = audit
            write(serving / 'result.json', result)
        index_progress('verify-serving-assets.start')
        validation = verify_assets(generation)
        _verify_navigation_audit(destination / 'serving')
        index_progress('verify-serving-assets.done')
        for path, expected in pins.items():
            if sha(path) != expected:
                raise ValueError('Release input changed during preparation')
        receipt = {'schema_version': 'document-release-v1', 'completed': True, 'activated': False,
                   'quality_certified': False, 'generation': 'serving/generation', 'review_status': review['review_status'],
                   'review_completion_sha256': sha(state / 'completion.json'),
                   'plan_sha256': sha(plan), 'reviewed_report_sha256': sha(reviewed / 'report.json'),
                   'source_selection_sha256': sha(selection_path), 'source_store_sha256': sha(source),
                   'result_sha256': sha(destination / 'serving/result.json'),
                   'manifest_sha256': validation['manifest_sha256'], 'counts': result['counts']}
        if coverage:
            # Copy the exclusion audit into the portable release, pinned by its receipt.
            audit = destination / 'structure-selection-origin.json'
            if audit.exists() and sha(audit) != coverage['origin_sha256']:
                raise ValueError('Release structure selection audit changed')
            if not audit.exists():
                shutil.copyfile(origin_path, audit)
            receipt['structure_coverage'] = coverage
        if reference_apply is not None:
            receipt['reference_review_state_sha256'] = reference_binding['state_sha256']
            receipt['reference_apply_receipt_sha256'] = sha(
                generation / 'navigation/reference-resolution-apply.json')
            if reference_model:
                receipt['reference_model_profile_sha256'] = reference_model['sha256']
                receipt['reference_approval_mode'] = 'automatic'
        target = destination / 'release.json'
        if target.exists() and json.loads(target.read_text()) != receipt:
            raise ValueError('Completed release receipt changed')
        if not target.exists():
            write(target, receipt)
        index_progress('release-receipt.done')
        return {**receipt, 'path': str(destination), 'generation_path': str(generation)}


def index_without_meaning_review(data, run_id, reason):
    """Consume an existing prepared draft; do not modify or complete its review.

    A separate receipt records the explicit omission. The same index/serving
    compiler is used, with source and glossary evidence checks still enforced.
    """
    from . import glossary_assembly
    from .genos_status import validate_run_id
    validate_run_id(run_id)
    if not reason.strip():
        raise ValueError('Skipping meaning review requires a recorded reason')
    parent = genos_stages.plain_path(Path(data).resolve() / 'TERM_RELEASES' / run_id)
    if not (parent / 'review/review.sqlite').is_file():
        raise ValueError('Run document-release prepare first')
    with (parent / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source, glossary = parent / 'sources/store.sqlite', parent / 'glossary-draft'
        plan = json.loads((parent / 'plan.json').read_text())
        selection = json.loads((parent / 'sources/selection.json').read_text())
        report = glossary_assembly.inspect(glossary)
        source_hash = sha(source)
        if plan.get('reference_review') or plan.get('reference_model'):
            raise ValueError('Prepared reference overlay requires the reviewed release path')
        if (selection['store_sha256'] != source_hash
                or selection['identity']['exclude_document_ids'] != plan['exclude']
                or report['document_update']['identity']['source_sha256'] != source_hash
                or report['document_update']['identity']['parent_dictionary_sha256'] != plan['glossary_sha256']):
            raise ValueError('Prepared source/glossary binding mismatch')
        input_pins = {**plan['pins'], **{r['path']: r['sha256'] for r in selection['identity']['sources']}}
        for path, expected in input_pins.items():
            if sha(genos_stages.plain_path(path)) != expected:
                raise ValueError('Prepared input changed: ' + path)
        with closing(glossary_review.v1.read_db(parent / 'review/review.sqlite')) as db:
            review_identity = json.loads(db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0])
        if review_identity['glossary_sha256'] != report['dictionary_sha256']:
            raise ValueError('Prepared review/glossary binding mismatch')
        with closing(glossary_review.v1.read_db(source)) as db:
            if sorted(r[0] for r in db.execute('SELECT document_id FROM document')) != sorted(selection['document_ids']):
                raise ValueError('Prepared document scope changed')
        audits = {'parent-plan.json': (parent / 'plan.json').read_bytes(),
                  'source-selection.json': (parent / 'sources/selection.json').read_bytes(),
                  'draft-report.json': (glossary / 'report.json').read_bytes()}
        origin_path = Path(data).resolve() / 'LOGS' / run_id / 'selection-origin.json'
        coverage = None
        if str(origin_path) in plan['pins']:
            origin = json.loads(origin_path.read_text())
            coverage = {k: origin[k] for k in ('parent_run_id', 'parent_attempt_id', 'coverage', 'omitted_count')}
            coverage['selected_count'] = len(origin['selected_document_ids'])
            audits['structure-selection-origin.json'] = origin_path.read_bytes()
        identity = {'policy': 'skip-meaning-review', 'reason': reason.strip(),
                    'source_sha256': source_hash, 'glossary_sha256': report['dictionary_sha256'],
                    'parent_plan_sha256': sha(parent / 'plan.json'),
                    'parent_selection_sha256': sha(parent / 'sources/selection.json'),
                    'parent_report_sha256': sha(glossary / 'report.json'),
                    'compiler_sha256': sha(__file__), 'review_ledger_consumed': False}
        output = parent / 'serving-unreviewed'
        output.mkdir(exist_ok=True)
        index_plan = output / 'index-plan.json'
        if index_plan.exists():
            if json.loads(index_plan.read_text()) != identity:
                raise ValueError('Unreviewed index inputs changed; preserve this output and use a new run')
        else:
            write(index_plan, identity)
        for name, raw in audits.items():
            target = output / name
            if target.exists():
                if target.read_bytes() != raw:
                    raise ValueError('Unreviewed index audit changed')
            else:
                with target.open('xb') as stream:
                    stream.write(raw)
        if (output / 'release.json').exists():
            generation, receipt = verify_release(output)
            return {**receipt, 'path': str(output), 'generation_path': str(generation), 'cached': True}
        scope = {'document_version_ids': selection['document_ids'],
                 'source_selection_sha256': identity['parent_selection_sha256']}
        print('INDEX: using prepared documents and glossary; meaning review skipped; no LLM calls', flush=True)
        result = build_generation(source, glossary, output / 'serving', serving=True, scope=scope)
        validation = verify_assets(output / 'serving/generation')
        _verify_navigation_audit(output / 'serving')
        for path, expected in {**input_pins, str(source): source_hash,
                               str(glossary / 'dictionary.sqlite'): report['dictionary_sha256'],
                               str(parent / 'plan.json'): identity['parent_plan_sha256'],
                               str(parent / 'sources/selection.json'): identity['parent_selection_sha256'],
                               str(glossary / 'report.json'): identity['parent_report_sha256']}.items():
            if sha(path) != expected:
                raise ValueError('Prepared input changed during indexing')
        receipt = {'schema_version': 'document-release-unreviewed-v1', 'completed': True,
                   'stage': 'index', 'stage_completed': True, 'review_status': 'SKIPPED',
                   'review_reason': reason.strip(), 'canonical_approval': False,
                   'quality_certified': False, 'activated': False, 'llm_calls': 0,
                   'generation': 'serving/generation', 'manifest_sha256': validation['manifest_sha256'],
                   'counts': result['counts'], 'source_sha256': source_hash,
                   'glossary_sha256': report['dictionary_sha256'],
                   'files': {name: sha(output / name) for name in
                             [*audits, 'index-plan.json', 'serving/result.json']}}
        if coverage:
            receipt['structure_coverage'] = coverage
        write(output / 'release.json', receipt)
        return {**receipt, 'path': str(output), 'generation_path': str(output / 'serving/generation')}


def verify_unreviewed_release(path, receipt):
    if (receipt.get('completed') is not True or receipt.get('review_status') != 'SKIPPED'
            or receipt.get('canonical_approval') is not False or receipt.get('quality_certified') is not False
            or receipt.get('llm_calls') != 0 or not receipt.get('review_reason')):
        raise ValueError('Invalid unreviewed release status')
    required = {'parent-plan.json', 'source-selection.json', 'draft-report.json',
                'index-plan.json', 'serving/result.json'}
    if receipt.get('structure_coverage'):
        required.add('structure-selection-origin.json')
    if set(receipt['files']) != required:
        raise ValueError('Invalid unreviewed release audit files')
    for name, expected in receipt['files'].items():
        if sha(genos_stages.plain_path(path / name)) != expected:
            raise ValueError('Unreviewed release audit changed: ' + name)
    identity = json.loads((path / 'index-plan.json').read_text())
    result = json.loads((path / 'serving/result.json').read_text())
    selection = json.loads((path / 'source-selection.json').read_text())
    draft = json.loads((path / 'draft-report.json').read_text())
    if (identity['policy'] != 'skip-meaning-review' or identity['reason'] != receipt['review_reason']
            or identity['parent_plan_sha256'] != receipt['files']['parent-plan.json']
            or identity['parent_selection_sha256'] != receipt['files']['source-selection.json']
            or identity['parent_report_sha256'] != receipt['files']['draft-report.json']
            or selection['store_sha256'] != receipt['source_sha256']
            or draft['dictionary_sha256'] != receipt['glossary_sha256']
            or identity['source_sha256'] != receipt['source_sha256']
            or identity['glossary_sha256'] != receipt['glossary_sha256']
            or result['identity']['source_sha256'] != receipt['source_sha256']
            or result['identity']['glossary']['dictionary_sha256'] != receipt['glossary_sha256']
            or result['manifest_sha256'] != receipt['manifest_sha256']):
        raise ValueError('Unreviewed release input binding mismatch')
    if receipt.get('structure_coverage'):
        origin = json.loads((path / 'structure-selection-origin.json').read_text())
        coverage = {k: origin[k] for k in ('parent_run_id', 'parent_attempt_id', 'coverage', 'omitted_count')}
        coverage['selected_count'] = len(origin['selected_document_ids'])
        if coverage != receipt['structure_coverage']:
            raise ValueError('Unreviewed release coverage mismatch')
    if receipt['generation'] != 'serving/generation':
        raise ValueError('Invalid unreviewed generation path')
    generation = genos_stages.plain_path(path / receipt['generation'])
    if verify_assets(generation)['manifest_sha256'] != receipt['manifest_sha256']:
        raise ValueError('Unreviewed generation mismatch')
    _verify_navigation_audit(path / 'serving')
    return generation, receipt


def verify_glossary(path):
    from . import glossary_assembly
    path = Path(path).resolve()
    report = glossary_assembly.inspect(path)
    review = report.get('llm_review', {})
    state = Path(review.get('state', ''))
    receipt_path = state / 'completion.json'
    if not receipt_path.is_file():
        raise ValueError('Explicit glossary needs a completed review receipt')
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get('completed') is not True or receipt['dictionary_sha256'] != report['dictionary_sha256']
            or receipt['state_sha256'] != sha(state / 'review.sqlite')
            or review.get('state_sha256') != receipt['state_sha256']
            or (state / receipt['output_relative_to_state']).resolve() != path):
        raise ValueError('Completed glossary receipt mismatch')
    glossary_linking.binding(path)
    return {'verified': True, 'dictionary_sha256': report['dictionary_sha256'],
            'review_status': receipt['review_status']}


def verify_release(path):
    path = genos_stages.plain_path(path).resolve()
    receipt = json.loads((path / 'release.json').read_text())
    if receipt.get('schema_version') == 'document-release-unreviewed-v1':
        return verify_unreviewed_release(path, receipt)
    if receipt.get('schema_version') != 'document-release-v1' or not receipt.get('completed'):
        raise ValueError('Incomplete document release')
    if receipt.get('structure_coverage'):
        if sha(path / 'structure-selection-origin.json') != receipt['structure_coverage']['origin_sha256']:
            raise ValueError('Release structure selection audit changed')
    for file, field in [('plan.json', 'plan_sha256'), ('serving/result.json', 'result_sha256'),
                        ('review/completion.json', 'review_completion_sha256'),
                        ('glossary-reviewed/report.json', 'reviewed_report_sha256'),
                        ('sources/selection.json', 'source_selection_sha256'), ('sources/store.sqlite', 'source_store_sha256')]:
        if sha(path / file) != receipt[field]:
            raise ValueError('Release receipt binding mismatch: ' + file)
    review = json.loads((path / 'review/completion.json').read_text())
    if sha(path / 'review/review.sqlite') != review['state_sha256']:
        raise ValueError('Review audit state changed')
    if sha(path / 'glossary-reviewed/dictionary.sqlite') != review['dictionary_sha256']:
        raise ValueError('Reviewed glossary changed')
    generation = (path / receipt['generation']).resolve()
    generation.relative_to(path)
    if verify_assets(generation)['manifest_sha256'] != receipt['manifest_sha256']:
        raise ValueError('Release generation mismatch')
    _verify_navigation_audit(path / 'serving')
    if receipt.get('reference_apply_receipt_sha256'):
        apply_receipt = generation / 'navigation/reference-resolution-apply.json'
        if sha(apply_receipt) != receipt['reference_apply_receipt_sha256']:
            raise ValueError('Reference resolution apply receipt changed')
        if json.loads(apply_receipt.read_text())['review_state_sha256'] != receipt['reference_review_state_sha256']:
            raise ValueError('Reference review state binding mismatch')
    return generation, receipt


def publish_shared_generation(release, shared_root):
    """Copy a verified release generation to an explicit shared volume, without activation."""
    source, release_receipt = verify_release(release)
    release = genos_stages.plain_path(release).resolve()
    shared_root = genos_stages.plain_path(shared_root)
    if not shared_root.is_dir():
        raise ValueError('Shared root must already exist and be visible to code-serving')
    if shared_root == source or shared_root in source.parents or source in shared_root.parents:
        raise ValueError('Shared root must be separate from the generation being copied')
    variant = 'unreviewed' if release_receipt['schema_version'] == 'document-release-unreviewed-v1' else 'reviewed'
    run_id = release.parent.name if variant == 'unreviewed' else release.name
    from .genos_status import validate_run_id
    validate_run_id(run_id)
    destination = genos_stages.plain_path(shared_root / run_id / variant)
    source_hashes = genos_stages.files_hashes(source)
    identity = {'schema_version': 'document-release-shared-generation-v1',
                'run_id': run_id, 'variant': variant,
                'release_sha256': sha(release / 'release.json'),
                'manifest_sha256': release_receipt['manifest_sha256'],
                'files': source_hashes}
    if destination.exists():
        existing = json.loads((destination / 'share-receipt.json').read_text())
        if existing != identity or genos_stages.files_hashes(destination / 'generation') != source_hashes:
            raise ValueError('Shared generation differs; preserve it and use a new run ID')
        verify_assets(destination / 'generation')
        return {'published': True, 'cached': True, 'activated': False,
                'generation_path': str(destination / 'generation'), 'receipt_path': str(destination / 'share-receipt.json')}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.' + variant + '-', dir=destination.parent))
    started = last_logged = time.monotonic()
    copied = 0
    try:
        target = temporary / 'generation'
        target.mkdir()
        for path in sorted(source.rglob('*')):
            relative = path.relative_to(source)
            output = target / relative
            if path.is_symlink():
                raise ValueError('Generation contains a symlink: ' + str(relative))
            if path.is_dir():
                output.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                output.parent.mkdir(parents=True, exist_ok=True)
                with path.open('rb') as input_stream, output.open('xb') as output_stream:
                    while chunk := input_stream.read(8 * 1024 * 1024):
                        output_stream.write(chunk)
                        copied += len(chunk)
                        if time.monotonic() - last_logged >= 30:
                            print(f'SHARED PUBLISH copying elapsed={time.monotonic()-started:.1f}s bytes={copied}', flush=True)
                            last_logged = time.monotonic()
                shutil.copystat(path, output)
            else:
                raise ValueError('Generation contains a non-file entry: ' + str(relative))
        print('SHARED PUBLISH verifying copied generation', flush=True)
        if genos_stages.files_hashes(target) != source_hashes:
            raise ValueError('Shared generation copy hash mismatch')
        if verify_assets(target)['manifest_sha256'] != identity['manifest_sha256']:
            raise ValueError('Shared generation manifest mismatch')
        write(temporary / 'share-receipt.json', identity)
        if destination.exists():
            raise ValueError('Shared generation appeared during publication')
        os.rename(temporary, destination)
        print(f'SHARED PUBLISH complete bytes={copied} generation={destination / "generation"}', flush=True)
        return {'published': True, 'cached': False, 'activated': False,
                'generation_path': str(destination / 'generation'), 'receipt_path': str(destination / 'share-receipt.json')}
    except BaseException:
        shutil.rmtree(temporary)
        raise


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.pointer-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def change_pointer(root, *, release=None, rollback=None, expected_current, confirm=False):
    if not confirm:
        raise ValueError('Activation/rollback requires --confirm-main')
    if bool(release) == bool(rollback):
        raise ValueError('Select exactly one release or rollback receipt')
    root = genos_stages.plain_path(root).resolve()
    pointer = root / 'generations/CURRENT.json'
    pointer.parent.mkdir(parents=True, exist_ok=True)
    with (pointer.parent / '.activation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        actual = sha(pointer) if pointer.exists() else 'absent'
        if actual != expected_current:
            raise ValueError('CURRENT changed; inspect the new selection before activation')
        before = json.loads(pointer.read_text()) if pointer.exists() else None
        if release:
            generation, receipt = verify_release(release)
            generation.relative_to(root)
            manifest = json.loads((generation / 'manifest.json').read_text())
            after = {'schema_version': 'genos-current-generation-v1', 'generation_id': manifest['generation_id'],
                     'path': str(generation), 'manifest_sha256': receipt['manifest_sha256']}
        else:
            history = genos_stages.plain_path(rollback).resolve()
            history.relative_to(pointer.parent / 'receipts')
            event = json.loads(history.read_text())
            if before != event['after']:
                raise ValueError('Rollback receipt does not describe CURRENT')
            after = event['before']
            if after is not None:
                previous = genos_stages.plain_path(after['path']).resolve()
                previous.relative_to(root)
                if sha(previous / 'manifest.json') != after['manifest_sha256']:
                    raise ValueError('Rollback target changed')
                with closing(Store(previous)):
                    pass
        history = pointer.parent / 'receipts' / (uuid.uuid4().hex + '.json')
        event = {'schema_version': 'document-release-activation-v1', 'before': before, 'after': after,
                 'previous_pointer_sha256': actual, 'action': 'APPLY' if release else 'ROLLBACK',
                 'quality_certified': False, 'release': str(release) if release else None}
        _atomic(history, event)
        if after is None:
            pointer.unlink(missing_ok=True)
        else:
            _atomic(pointer, after)
        return {'activated': release is not None, 'action': event['action'], 'receipt': str(history),
                'current_sha256': sha(pointer) if pointer.exists() else 'absent', 'restart_required': True}


def recorded_status(data, run_id):
    """Read recorded milestones without creating files or claiming process liveness."""
    from .genos_status import validate_run_id
    validate_run_id(run_id)
    directory = genos_stages.plain_path(Path(data) / 'TERM_RELEASES' / run_id)
    selection_path = genos_stages.plain_path(Path(data) / 'LOGS' / run_id / 'structure-selection.json')
    milestones = {
        'select': selection_path, 'merge': directory / 'sources/selection.json',
        'prepare': directory / 'review/review.sqlite', 'review': directory / 'review/completion.json',
        'index': directory / 'release.json',
    }
    result = {'run_id': run_id, 'recorded_only': True, 'integrity_checked': False,
              'stages': {stage: {'recorded': genos_stages.plain_path(path).is_file(), 'path': str(path)}
                         for stage, path in milestones.items()},
              'note': 'Saved milestones only; use verify for release integrity. No liveness or activation claim.'}
    if selection_path.exists():
        selection = json.loads(selection_path.read_text())
        result['selected_documents'] = len(selection.get('documents', {}))
        result['selection_completed'] = selection.get('completed', False)
    origin = genos_stages.plain_path(selection_path.parent / 'selection-origin.json')
    if origin.exists():
        value = json.loads(origin.read_text())
        result['structure_coverage'] = {key: value[key] for key in ('coverage', 'parent_run_id', 'omitted_count')}
        result['exclusion_audit'] = str(origin)
    if milestones['prepare'].is_file():
        result['review'] = glossary_review.inspect(directory / 'review')
    if (directory / 'reference-review/review.sqlite').is_file():
        from . import reference_resolution
        result['reference_resolution'] = reference_resolution.inspect(directory / 'reference-review')
    unreviewed = directory / 'serving-unreviewed/release.json'
    if unreviewed.is_file():
        result['unreviewed_index'] = {'recorded': True, 'path': str(unreviewed), 'review_status': 'SKIPPED'}
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['select', 'merge', 'prepare', 'review', 'references', 'index', 'status',
                                     'build', 'verify', 'verify-glossary', 'publish-shared', 'activate', 'rollback',
                                     'compact-navigation', 'rebind-fulltext'])
    p.add_argument('--output', type=Path, help='compact-navigation: new build directory, including separate audit')
    p.add_argument('--fulltext-binding', type=Path, help='Explicit selected profile fulltext binding JSON')
    p.add_argument('--run-id'); p.add_argument('--glossary-dir', type=Path)
    p.add_argument('--glossary-corpus-policy', choices=['append', 'replace'], default='append',
                   help='replace rebuilds document evidence in a NEW draft from the selected corpus; preserves the parent glossary')
    p.add_argument('--from-run-id', help='Finished structure run to snapshot into a NEW --run-id')
    p.add_argument('--allow-incomplete', action='store_true', help='Explicitly omit failed inputs/structures in select')
    p.add_argument('--reason', default='', help='Recorded reason for the success-only selection')
    p.add_argument('--base-generation', action='append', type=Path, default=[])
    p.add_argument('--exclude-document', action='append', default=[])
    p.add_argument('--max-review-jobs', type=int, default=100)
    p.add_argument('--retry-review-failed', action='store_true')
    p.add_argument('--skip-meaning-review', action='store_true', help='index only: use the prepared draft and record SKIPPED without consuming review results')
    p.add_argument('--skip-review-reason', default='')
    p.add_argument('--reference-review-state', type=Path)
    p.add_argument('--reference-model-profile', type=Path, help='Run LLM reference resolution with automatic approval after deterministic indexing')
    p.add_argument('--max-reference-cases', type=int, default=10000)
    p.add_argument('--reference-batch-size', type=int, default=8)
    p.add_argument('--release', type=Path); p.add_argument('--receipt', type=Path)
    p.add_argument('--shared-root', type=Path)
    p.add_argument('--active-data-root', type=Path)
    p.add_argument('--expected-current'); p.add_argument('--confirm-main', action='store_true')
    a = p.parse_args(argv)
    if a.skip_meaning_review:
        if a.action != 'index' or not a.skip_review_reason.strip():
            p.error('--skip-meaning-review requires index and --skip-review-reason')
        if (a.glossary_dir or a.base_generation or a.exclude_document or a.reference_review_state or a.reference_model_profile
                or a.retry_review_failed or a.glossary_corpus_policy != 'append'):
            p.error('skip mode uses already prepared inputs; do not pass new inputs or review options')
    elif a.skip_review_reason:
        p.error('--skip-review-reason requires --skip-meaning-review')
    if a.action != 'select' and (a.from_run_id or a.allow_incomplete or a.reason):
        p.error('--from-run-id/--allow-incomplete/--reason are only supported by select')
    if a.action == 'compact-navigation':
        if len(a.base_generation)!=1 or not a.output:
            p.error('compact-navigation requires one --base-generation and --output')
        from semantic_runtime.navigation_storage import compact_generation
        parent = json.loads((a.base_generation[0] / 'manifest.json').read_text())
        legacy = not parent.get('fulltext') and (a.base_generation[0] / 'fulltext/manifest.json').is_file()
        if legacy and not a.fulltext_binding:
            p.error('legacy fulltext requires explicit --fulltext-binding from the selected release profile')
        intermediate = a.output.with_name(a.output.name + '-navigation') if a.fulltext_binding else a.output
        result = compact_generation(a.base_generation[0], intermediate)
        if a.fulltext_binding:
            result = rebind_fulltext(intermediate, json.loads(a.fulltext_binding.read_text()), a.output)
    elif a.action == 'rebind-fulltext':
        if not a.release or not a.fulltext_binding or not a.output:
            p.error('rebind-fulltext requires --release build-dir, --fulltext-binding and --output')
        result = rebind_fulltext(a.release, json.loads(a.fulltext_binding.read_text()), a.output)
    elif a.action in {'select', 'merge', 'prepare', 'review', 'references', 'index', 'status', 'build'}:
        if not a.run_id:
            p.error('--run-id is required')
        from .genos_status import validate_run_id
        validate_run_id(a.run_id)
        from lawrag.platform.paths import repository_root
        root = repository_root(); data = genos_stages.offline_data_root(root)
        if a.action == 'select':
            if not a.from_run_id:
                p.error('select requires --from-run-id and a new --run-id')
            from .structure_selection import select_completed
            result = select_completed(data, a.from_run_id, a.run_id,
                                      allow_incomplete=a.allow_incomplete, reason=a.reason)
        elif a.action == 'status':
            result = recorded_status(data, a.run_id)
        elif a.skip_meaning_review:
            result = index_without_meaning_review(data, a.run_id, a.skip_review_reason)
        else:
            if a.action == 'index' and a.retry_review_failed:
                p.error('index never runs review jobs; use review --retry-review-failed before completion')
            glossary = a.glossary_dir or glossary_review.configured_paths()['glossary']
            result = build(data, a.run_id, glossary, bases=a.base_generation, exclude=a.exclude_document,
                           max_jobs=a.max_review_jobs, retry_failed=a.retry_review_failed,
                           stage=a.action, reference_state=a.reference_review_state,
                           reference_profile=a.reference_model_profile, max_reference_cases=a.max_reference_cases,
                           reference_batch_size=a.reference_batch_size,
                           glossary_corpus_policy=a.glossary_corpus_policy)
    elif a.action == 'verify-glossary':
        if not a.glossary_dir: p.error('--glossary-dir is required')
        result = verify_glossary(a.glossary_dir)
    elif a.action == 'verify':
        if not a.release: p.error('--release is required')
        generation, receipt = verify_release(a.release)
        result = {'verified': True, 'generation': str(generation), 'review_status': receipt['review_status']}
    elif a.action == 'publish-shared':
        if not a.release or not a.shared_root:
            p.error('publish-shared requires --release and --shared-root')
        result = publish_shared_generation(a.release, a.shared_root)
    else:
        if not a.active_data_root or not a.expected_current: p.error('--active-data-root and --expected-current are required')
        result = change_pointer(a.active_data_root, release=a.release if a.action == 'activate' else None,
                                rollback=a.receipt if a.action == 'rollback' else None,
                                expected_current=a.expected_current, confirm=a.confirm_main)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 3 if (a.action in {'merge', 'prepare', 'review', 'index', 'build'} and
                 not result.get('stage_completed', result['completed'])) else 0
