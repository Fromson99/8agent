"""Independent meaning-review worker and OFF/ON RAG generations from one prepared scope.

Delegates extraction, meaning review, links, indexing and reference resolution to
the existing pipeline. No changes to its compiler bytes, plan, RAW or CURRENT.
"""
import argparse
from contextlib import closing, contextmanager
import fcntl
import inspect
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import threading
import time
import traceback

from semantic_runtime.contracts import sha, write
from lawrag.pipeline import document_release as release, glossary_review, glossary_assembly
from lawrag.pipeline import reference_resolution, genos_stages


VERSION = 'genos-meaning-variants-v1'
FAILURE_STREAK_LIMIT = 10


def log(message):
    print(time.strftime('[%Y-%m-%d %H:%M:%S] ') + message, flush=True)


def dump_error():
    from semantic_runtime.genos_backend import safe
    print(safe(traceback.format_exc()), file=sys.stderr, flush=True)


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def immutable(path, value):
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError('Immutable receipt differs: ' + str(path))
    else:
        write(path, value)


def prepared(data, run):
    from lawrag.pipeline.genos_status import validate_run_id
    validate_run_id(run)
    required = [(release, name) for name in ('build_generation', 'verify_assets', 'verify_glossary',
                                             '_copy_reference_audit', '_verify_navigation_audit')]
    required += [(reference_resolution, name) for name in ('advance', 'apply')]
    missing = [module.__name__ + '.' + name for module, name in required if not callable(getattr(module, name, None))]
    if missing:
        raise ValueError('Field release wiring missing; no silent core patch: ' + ', '.join(missing))
    parent = genos_stages.plain_path(Path(data).resolve() / 'TERM_RELEASES' / run)
    plan_path = parent / 'plan.json'
    plan = json.loads(plan_path.read_text())
    source, draft = parent / 'sources/store.sqlite', parent / 'glossary-draft'
    selection_path = parent / 'sources/selection.json'
    selection = json.loads(selection_path.read_text())
    report = glossary_assembly.inspect(draft)
    if (sha(source) != selection['store_sha256']
            or report['document_update']['identity']['source_sha256'] != sha(source)
            or report['document_update']['identity']['parent_dictionary_sha256'] != plan['glossary_sha256']):
        raise ValueError('Prepared source/draft binding mismatch')
    if selection['identity']['exclude_document_ids'] != plan['exclude']:
        raise ValueError('Prepared exclusion scope mismatch')
    profile = Path(plan.get('reference_model', {}).get('profile', ''))
    if not profile.is_file() or sha(profile) != plan['reference_model']['sha256']:
        raise ValueError('Explicit prepared reference model profile is required')
    model = json.loads(profile.read_text()).get('model_binding', {})
    if model.get('provider') != 'genos' or model.get('trust_zone') != 'internal':
        raise ValueError('Field variant requires the pinned internal GENOS reference model; no external fallback')
    with closing(glossary_review.v1.read_db(parent / 'review/review.sqlite')) as db:
        review_identity = json.loads(db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0])
    if review_identity['glossary_sha256'] != report['dictionary_sha256']:
        raise ValueError('Prepared meaning review identity mismatch')
    with closing(glossary_review.v1.read_db(source)) as db:
        if sorted(r[0] for r in db.execute('SELECT document_id FROM document')) != sorted(selection['document_ids']):
            raise ValueError('Prepared document scope mismatch')
    pins = {**plan['pins'], **{p['path']: p['sha256'] for p in selection['identity']['sources']},
            str(plan_path): sha(plan_path), str(source): sha(source),
            str(selection_path): sha(selection_path), str(draft / 'report.json'): sha(draft / 'report.json'),
            str(draft / 'dictionary.sqlite'): report['dictionary_sha256'], str(profile): sha(profile)}
    verify_pins(pins)
    return {'parent': parent, 'source': source, 'draft': draft, 'profile': profile,
            'selection': selection, 'pins': pins}


def verify_pins(pins):
    for path, expected in pins.items():
        if sha(genos_stages.plain_path(path)) != expected:
            raise ValueError('Pinned input changed: ' + path)


def code_pins():
    tool = Path(os.environ.get('GENOS_VARIANTS_TOOL_PATH', __file__)).resolve(strict=True)
    files = [tool, Path(release.__file__), Path(reference_resolution.__file__),
             Path(glossary_review.__file__), Path(release.build_generation.__code__.co_filename)]
    return {str(p): sha(p) for p in files}


@contextmanager
def phase(label):
    """One active-phase heartbeat; never invent a total or suppress exceptions."""
    started = time.monotonic()
    stop = threading.Event()
    log(label + ' START')
    def heartbeat():
        while not stop.wait(30):
            log(f'{label} RUNNING elapsed={time.monotonic()-started:.1f}s; remaining not measured')
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        yield
    except BaseException:
        log(label + ' FAILED/INTERRUPTED; original exception is propagated')
        raise
    else:
        log(f'{label} DONE elapsed={time.monotonic()-started:.1f}s')
    finally:
        stop.set()
        thread.join(timeout=1)


@contextmanager
def generation_logging():
    """Runtime-only function logging also works with the older field builder."""
    from lawrag.pipeline import term_generation, term_serving_bundle
    targets = [(term_generation.glossary_linking, 'project', 'document-term links'),
               (term_generation, 'publish', 'source generation'),
               (term_serving_bundle, 'prepare_assets', 'glossary serving assets'),
               (term_generation, 'compile_index', 'navigation and explicit-reference candidates'),
               (term_generation.fulltext, 'build', 'fulltext index')]
    saved = []
    try:
        for module, name, label in targets:
            original = getattr(module, name)
            def wrapper(*args, _original=original, _label=label, **kwargs):
                with phase(_label):
                    return _original(*args, **kwargs)
            # The native builder fingerprints dependency files through co_filename.
            # Keep that original file binding; this logging tool is pinned separately.
            wrapper.__code__ = wrapper.__code__.replace(co_filename=original.__code__.co_filename)
            saved.append((module, name, original))
            setattr(module, name, wrapper)
        yield
    finally:
        for module, name, original in reversed(saved):
            setattr(module, name, original)


def review_worker(context, *, batch=100, provider=None):
    """Keep completed work; recover only interrupted running jobs under exclusive locks.

    Failed jobs are not automatically retried forever. The normal completion may
    be PARTIAL and that status is retained in the ON variant's audit.
    """
    parent = context['parent']
    state, output = parent / 'review', parent / 'glossary-reviewed'
    with locked(parent / '.lock'), locked(parent / '.meaning-worker.lock'):
        verify_pins(context['pins'])
        with glossary_review.locked(state), closing(glossary_review.ledger(state / 'review.sqlite')) as db:
            running = [r[0] for r in db.execute("SELECT id FROM job WHERE status='running'")]
            if running:
                log(f'Recover interrupted jobs={len(running)}; completed and failed jobs preserved')
                db.execute("UPDATE attempt SET status='interrupted',error='worker recovered interrupted attempt' WHERE status='running'")
                db.execute("UPDATE job SET status='pending' WHERE status='running'")
                db.commit()
        # Record original exception details without editing the pinned review implementation.
        original_validate = glossary_review.validate
        initial = glossary_review.inspect(state)
        initial_pending = initial['jobs'].get('pending', 0)
        processed, failure_streak, durations = [0], [0], []
        def progress(job_id):
            remaining = max(0, initial_pending - processed[0])
            eta = ('unknown' if not durations else f'{remaining*sum(durations)/len(durations)/3600:.1f}h approximate')
            log(f'MEANING job={job_id} settled_this_worker={processed[0]} remaining~{remaining} ETA={eta}')
        def validate(*args, **kwargs):
            try:
                result = original_validate(*args, **kwargs)
            except Exception:
                failure_streak[0] += 1
                log('Meaning response validation failed; original traceback follows')
                dump_error()
                raise
            finally:
                processed[0] += 1
            failure_streak[0] = 0
            return result
        glossary_review.validate = validate
        class VisibleProvider:
            def __init__(self, delegate): self.delegate = delegate
            def prepare(self): return self.delegate.prepare()
            def call(self, *args, **kwargs):
                if failure_streak[0] >= FAILURE_STREAK_LIMIT:
                    # Native run catches Exception to retain a failed job. An explicit
                    # interrupt exits that loop; the not-sent reserved job is recovered
                    # on the next worker start, just like a user interrupt.
                    raise KeyboardInterrupt(f'Meaning worker paused after {failure_streak[0]} consecutive failures; '
                                            'inspect original errors before resuming; remaining queue preserved')
                progress(args[2]['job_id'])
                started = time.monotonic()
                try:
                    result = self.delegate.call(*args, **kwargs)
                    log(f'Meaning API returned elapsed={time.monotonic()-started:.1f}s; validation follows')
                    return result
                except Exception:
                    processed[0] += 1
                    failure_streak[0] += 1
                    log('Meaning API failed; original traceback follows')
                    dump_error()
                    raise
                finally:
                    durations.append(time.monotonic()-started)
                    durations[:] = durations[-100:]
        visible_provider = None
        try:
            previous = None
            while True:
                status = glossary_review.inspect(state)
                jobs = status['jobs']
                pending = jobs.get('pending', 0) + jobs.get('running', 0)
                log(f"MEANING complete={jobs.get('complete',0)}/{status['total_jobs']} pending={pending} failed={jobs.get('failed',0)}")
                if pending == 0:
                    break
                if previous == jobs:
                    raise ValueError('Meaning worker made no progress; stopped without discarding jobs')
                previous = dict(jobs)
                if visible_provider is None:
                    visible_provider = VisibleProvider(provider or glossary_review.provider_for(state))
                glossary_review.run(state, max_jobs=batch, provider=visible_provider, continue_on_error=True)
                verify_pins(context['pins'])
            with phase('compile reviewed glossary proposals'):
                result = glossary_review.complete(context['draft'], state, output, max_jobs=batch, provider=provider)
            if not result['completed']:
                raise ValueError('Meaning completion did not finish')
            log('MEANING finished review_status=' + result['review_status'] + '; not canonical approval')
            if result['review_status'] != 'COMPLETE':
                log('WARNING: ON remains a reviewed proposal/partial result, not validated semantic quality')
            return result
        finally:
            glossary_review.validate = original_validate


def build_variant(context, mode, *, max_reference_cases=10000, batch_size=8):
    if mode not in ('off', 'on'):
        raise ValueError('Unknown meaning variant')
    parent = context['parent']
    glossary = context['draft'] if mode == 'off' else parent / 'glossary-reviewed'
    meaning_status = 'SKIPPED'
    extra_pins = {}
    if mode == 'on':
        from semantic_runtime.term_links import LinkProjector
        consume = getattr(LinkProjector, '_review_relations', None)
        if not callable(consume) or 'sense_assertion' not in inspect.getsource(consume):
            raise ValueError('Field term-links compiler cannot consume v3 proposals; no silent patch')
        verified = release.verify_glossary(glossary)
        meaning_status = verified['review_status']
        extra_pins = {str(parent / 'review/completion.json'): sha(parent / 'review/completion.json'),
                      str(parent / 'review/review.sqlite'): sha(parent / 'review/review.sqlite'),
                      str(glossary / 'report.json'): sha(glossary / 'report.json'),
                      str(glossary / 'dictionary.sqlite'): sha(glossary / 'dictionary.sqlite')}
    output = parent / 'meaning-variants' / mode
    pins = {**context['pins'], **extra_pins, **code_pins()}
    identity = {'schema_version': VERSION, 'meaning_mode': mode, 'meaning_review_status': meaning_status,
                'reference_llm': True, 'pins': pins, 'reference_batch_size': batch_size,
                'max_reference_cases': max_reference_cases, 'activated': False}
    with locked(output / '.lock'):
        immutable(output / 'plan.json', identity)
        if (output / 'release.json').exists():
            return verify_variant(output)
        scope = {'document_version_ids': context['selection']['document_ids'],
                 'source_selection_sha256': sha(parent / 'sources/selection.json')}
        log(f'VARIANT {mode}: document-term linking and baseline index; meaning={meaning_status}')
        with generation_logging():
            baseline = release.build_generation(context['source'], glossary, output / 'baseline', serving=True, scope=scope)
        state = output / 'reference-review'
        previous = None
        while True:
            with phase('explicit-reference LLM ' + mode):
                status = reference_resolution.advance(output / 'baseline/generation', state, context['profile'],
                                                      execute=True, max_cases=max_reference_cases, batch_size=batch_size)
            log('REFERENCE ' + mode + ' ' + json.dumps(status['cases'], ensure_ascii=False))
            if status['completed']:
                break
            if previous == status['cases']:
                raise ValueError('Reference review blocked; failed/unknown states retained, no infinite retry')
            previous = dict(status['cases'])
        serving = output / 'serving'
        serving.mkdir(exist_ok=True)
        if (serving / 'generation').exists() and not (serving / 'result.json').exists():
            raise ValueError('Interrupted reference apply requires inspection; preserved existing output')
        if not (serving / 'result.json').exists():
            applied = reference_resolution.apply(state, output / 'baseline/generation', serving / 'generation')
            audit = release._copy_reference_audit(output / 'baseline', serving)
            manifest = json.loads((serving / 'generation/manifest.json').read_text())
            result = {**{k: v for k, v in baseline.items() if k != 'llm_calls'},
                      'baseline_index_llm_calls': 0, 'reference_model_attempts': status.get('attempts', {}),
                      'meaning_mode': mode, 'manifest_sha256': sha(serving / 'generation/manifest.json'),
                      'navigation': manifest['navigation'], 'reference_resolution': applied}
            if audit:
                result['navigation_audit'] = audit
            write(serving / 'result.json', result)
        release._verify_navigation_audit(serving)
        validation = release.verify_assets(serving / 'generation')
        verify_pins(pins)
        receipt = {'schema_version': VERSION, 'completed': True, 'meaning_mode': mode,
                   'meaning_review_status': meaning_status, 'reference_llm': True,
                   'activated': False, 'canonical_approval': False, 'quality_certified': False,
                   'generation': 'serving/generation', 'document_count': len(scope['document_version_ids']),
                   'manifest_sha256': validation['manifest_sha256'], 'plan_sha256': sha(output / 'plan.json'),
                   'reference_state_sha256': sha(state / 'review.sqlite'),
                   'reference_completion': status,
                   'reference_model_attempts': status.get('attempts', {}),
                   'result_sha256': sha(serving / 'result.json'),
                   'apply_sha256': sha(serving / 'generation/navigation/reference-resolution-apply.json')}
        immutable(output / 'release.json', receipt)
        return verify_variant(output)


def verify_variant(output):
    output = Path(output).resolve()
    receipt = json.loads((output / 'release.json').read_text())
    plan = json.loads((output / 'plan.json').read_text())
    if (receipt['schema_version'] != VERSION or not receipt['completed']
            or receipt['meaning_mode'] != plan['meaning_mode'] or not receipt['reference_llm']
            or receipt['meaning_review_status'] != plan['meaning_review_status']
            or receipt['activated'] or receipt['canonical_approval'] or receipt['quality_certified']
            or receipt['generation'] != 'serving/generation'
            or sha(output / 'plan.json') != receipt['plan_sha256']
            or sha(output / 'serving/result.json') != receipt['result_sha256']
            or sha(output / 'reference-review/review.sqlite') != receipt['reference_state_sha256']):
        raise ValueError('Variant release receipt mismatch')
    verify_pins(plan['pins'])
    generation = output / receipt['generation']
    if release.verify_assets(generation)['manifest_sha256'] != receipt['manifest_sha256']:
        raise ValueError('Variant assets changed')
    apply = generation / 'navigation/reference-resolution-apply.json'
    if sha(apply) != receipt['apply_sha256'] or json.loads(apply.read_text())['review_state_sha256'] != receipt['reference_state_sha256']:
        raise ValueError('Variant reference overlay drift')
    release._verify_navigation_audit(output / 'serving')
    return {**receipt, 'generation_path': str(generation), 'release_path': str(output)}


def publish(output, shared_root):
    """Publish to a new explicit shared folder, returning startup settings only."""
    receipt = verify_variant(output)
    source = Path(receipt['generation_path'])
    root = genos_stages.plain_path(shared_root).resolve(strict=True)
    target = root / (Path(output).parents[1].name + '-meaning-' + receipt['meaning_mode'])
    files = genos_stages.files_hashes(source)
    binding = {'schema_version': VERSION, 'variant_receipt_sha256': sha(Path(output) / 'release.json'),
               'meaning_mode': receipt['meaning_mode'], 'meaning_review_status': receipt['meaning_review_status'],
               'manifest_sha256': receipt['manifest_sha256'], 'files': files, 'activated': False}
    selector = {'GENOS_GENERATION': str(target / 'generation'), 'meaning_mode': receipt['meaning_mode'],
                'reference_llm': True, 'activated': False}
    if target.exists():
        if (json.loads((target / 'share-receipt.json').read_text()) != binding
                or json.loads((target / 'rag-selection.json').read_text()) != selector
                or genos_stages.files_hashes(target / 'generation') != files):
            raise ValueError('Shared variant differs; previous publication preserved')
    else:
        temporary = Path(tempfile.mkdtemp(prefix='.meaning-share-', dir=root))
        try:
            shutil.copytree(source, temporary / 'generation')
            if genos_stages.files_hashes(temporary / 'generation') != files:
                raise ValueError('Shared copy bytes differ')
            release.verify_assets(temporary / 'generation')
            write(temporary / 'share-receipt.json', binding)
            write(temporary / 'rag-selection.json', selector)
            os.rename(temporary, target)
        except BaseException:
            shutil.rmtree(temporary)
            raise
    log('RAG startup selection: GENOS_GENERATION=' + str(target / 'generation'))
    log('No CURRENT, serving revision or workflow was changed; use separate serving settings for each variant.')
    return {'published': True, 'activated': False, 'path': str(target)}


def main(argv=None):
    # nohup jobs must still allow a deliberate graceful interrupt and ledger close.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['baseline', 'review', 'reviewed', 'status', 'verify'])
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--run-id', default='financial-risk-success-20261001-r3')
    parser.add_argument('--batch', type=int, default=100)
    parser.add_argument('--shared-root', type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.batch <= 1000:
        parser.error('--batch must be 1..1000')
    from lawrag.core.llm import load_env
    load_env()  # Existing env wins; never print credentials or change the model profile.
    context = prepared(args.data_root, args.run_id)
    log('Prepared scope documents=' + str(len(context['selection']['document_ids'])))
    if args.action == 'status':
        log(json.dumps(glossary_review.inspect(context['parent'] / 'review'), ensure_ascii=False))
        with closing(glossary_review.v1.read_db(context['parent'] / 'review/review.sqlite')) as db:
            failed = [dict(row) for row in db.execute("SELECT id,error FROM job WHERE status='failed' ORDER BY id LIMIT 10")]
        log('FAILED first10=' + json.dumps(failed, ensure_ascii=False) + '; full details in worker log and review/calls')
        for mode in ('off', 'on'):
            path = context['parent'] / 'meaning-variants' / mode
            log(mode + ': ' + ('release exists; use verify' if (path / 'release.json').exists() else 'not ready'))
        return 0
    if args.action == 'verify':
        missing = []
        for mode in ('off', 'on'):
            output = context['parent'] / 'meaning-variants' / mode
            if not (output / 'release.json').exists():
                missing.append(mode)
                log(mode + ' NOT READY; no completed release receipt')
            else:
                print(json.dumps(verify_variant(output), ensure_ascii=False))
        return 3 if missing else 0
    if args.action == 'review':
        review_worker(context, batch=args.batch)
        # ON is produced only after the original review has no pending/running jobs.
        mode = 'on'
    else:
        mode = 'off' if args.action == 'baseline' else 'on'
    result = build_variant(context, mode)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if args.shared_root:
        publish(Path(result['release_path']), args.shared_root)
    return 0


if __name__ == '__main__':
    try:
        exit_code = main()
    except BaseException as error:
        dump_error()
        exit_code = 130 if isinstance(error, KeyboardInterrupt) else 1
    log('FINISHED status=' + str(exit_code) + '; no activation')
    raise SystemExit(exit_code)
