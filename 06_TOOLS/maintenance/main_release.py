#!/usr/bin/env python3
"""Put a code change on top of the selected local MAIN, test it, and select it as the next MAIN.

One tool for what every audit folder used to rebuild by hand (stage.py,
apply_fix.py, pin_code.py, pytest_contracts.py, compare.py,
prepare_release.py, activate.py, entry_check.py).  All files of one change go
into one new directory OUT (normally 09_ARTIFACTS/AUDITS/<date-name>); the
steps record their results in OUT/main-release.json and each step refuses to
run when an earlier step did not pass or when the selected MAIN changed in the
meantime (another session selected a new MAIN: stage again on top of it).

  stage    --out OUT --product PATH[=SOURCE] ... [--remove PATH] [--allow-sql-change]
           [--navigation-source TEXT]
      Copy the selected MAIN's exact inventory to OUT/staged, put in only the
      listed product files (from the working tree, or from SOURCE when the
      working-tree file also holds other sessions' unfinished edits), then
      refresh the derived files: Oracle query plan metadata, navigation
      compatibility registry (when a navigation compiler file changed), engine
      pins and PIPELINE.json.  The executable SQL must stay identical unless
      --allow-sql-change.  OUT/stage-diff.patch shows every product change.
  test     --out OUT --files-from LIST [FILE ...]
      Run the tests on OUT/staged (run_tests.py --code-root, parallel), take the
      selected MAIN's results for the same files from the stored baseline and
      run only the files that have none.  Every test whose outcome differs is
      rerun alone on both trees; only a difference that remains counts.
      Passes when no test newly fails.  Already failing tests are listed, not fixed.
  prepare  --out OUT --release-id ID --reason TEXT --authorization-text TEXT
           [--scope TEXT] [--limit TEXT ...] [--evidence NAME=PATH ...]
      Write the integration declaration, authorization and validation, then
      run the release preparation (rag_main_promotion.py prepare).  MAIN is unchanged.
  activate --out OUT [--extra-check SCRIPT ...] [--inference-status TEXT]
      Select the prepared release as MAIN, move the local Gold connector to the
      same engine, and run the entry checks (real root service resolver, Gold
      connector, mappings) plus any --extra-check scripts (run with
      MAIN_RELEASE_OUT=OUT; non-zero exit fails).  Any failure rolls back MAIN
      and the Gold binding.
  rollback --out OUT       Undo this OUT's activation (only while it is still the selected MAIN).
  status   --out OUT       Show the recorded steps.

The stored baseline (baseline_results.py) means the next change on top of this
one is compared without rerunning this MAIN: its staged run is the baseline.
Change-specific checks (a real local Oracle service run, a scenario
reproduction) are still the caller's: run them on OUT/staged before prepare
and pass their result files with --evidence.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import baseline_results  # noqa: E402

PYTHON = str(ROOT / '.venv' / 'bin' / 'python') if (ROOT / '.venv' / 'bin' / 'python').exists() else sys.executable
ACTIVE = ROOT / '01_DATA' / 'ACTIVE' / 'local' / 'ACTIVE_RELEASE.json'
GOLD_BINDING = ROOT / '08_DEPLOYMENT' / 'LOCAL' / 'gold_connection_engine_r12' / 'binding.json'
NAVIGATION_FILES = ('02_BACKEND/semantic_runtime/navigation_match.py',
                    '02_BACKEND/semantic_runtime/structure_navigation.py',
                    '02_BACKEND/semantic_runtime/inherited_navigation.py')
PLANS = '02_BACKEND/semantic_runtime/oracle_query_plans.py'
NAVIGATION_REGISTRY = '00_SYSTEM/ORACLE/navigation_compatibility.json'


def derived(path: str) -> bool:
    """Files the stage step regenerates; every other change must be a declared product."""
    return (path in ('00_SYSTEM/PIPELINE.json', PLANS, NAVIGATION_REGISTRY)
            or (path.startswith('02_BACKEND/ENGINES/') and path.endswith('.json')))


def sha(path: Path) -> str:
    return baseline_results.sha_file(path)


def read(path: Path):
    return json.loads(Path(path).read_text())


def put(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def rel(path: Path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def fail(message: str):
    raise SystemExit('main_release: ' + message)


class State:
    def __init__(self, out: Path):
        self.out = out.resolve()
        self.path = self.out / 'main-release.json'
        self.value = read(self.path) if self.path.exists() else {'schema_version': 'main-release-tool-v1', 'attempts': []}

    def save(self) -> None:
        temporary = self.path.with_name('.main-release.json.tmp')
        put(temporary, self.value)
        os.replace(temporary, self.path)

    def step(self, name: str) -> dict:
        value = self.value.get(name)
        if not value or value.get('status') != 'PASSED':
            fail(f'step "{name}" has not passed in {rel(self.out)}')
        return value


def active_now() -> tuple[dict, str, dict]:
    pointer = read(ACTIVE)
    manifest = read(ROOT / pointer['manifest_path'])
    return pointer, sha(ACTIVE), manifest


def require_same_main(stage: dict) -> tuple[dict, dict]:
    pointer, pointer_sha, manifest = active_now()
    if pointer_sha != stage['active_pointer_sha256']:
        fail(f"the selected MAIN changed after stage ({stage['base_release_id']} gen {stage['base_generation']} -> "
             f"{pointer['release_id']} gen {pointer['generation']}); stage again on top of the new MAIN")
    return pointer, manifest


def run(command: list, log: Path | None = None, timeout: float = 3600, env: dict | None = None) -> subprocess.CompletedProcess:
    if log is None:
        return subprocess.run([str(part) for part in command], cwd=ROOT, check=True, timeout=timeout, env=env)
    with log.open('w') as handle:
        return subprocess.run([str(part) for part in command], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                              check=True, timeout=timeout, env=env)


def text_diff(name: str, before: Path | None, after: Path | None) -> tuple[str, int, int]:
    def lines(path):
        if path is None or not path.exists():
            return []
        try:
            return path.read_text().splitlines(keepends=True)
        except UnicodeDecodeError:
            return ['<binary %s>\n' % sha(path)]
    diff = list(difflib.unified_diff(lines(before), lines(after), 'MAIN/' + name, 'staged/' + name))
    added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
    removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
    return ''.join(diff), added, removed


# ---------------------------------------------------------------- stage
def constants(path: Path) -> dict:
    return {target.id: ast.literal_eval(node.value) for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name)}


def pin(code: Path, report: Path, allow_sql_change: bool) -> dict:
    """Runs in its own process (see `_pin`): regenerate plan metadata, engine pins, PIPELINE."""
    import importlib
    import importlib.util
    old = constants(code / PLANS)['PLANS']
    # The builder puts the working tree's 02_BACKEND first when it is loaded; import the
    # SQL translation modules from the staged tree before that so they come from there.
    sys.path.insert(0, str(code / '02_BACKEND'))
    for name in ('semantic_runtime.oracle_query_shape', 'semantic_runtime.oracle_sql_tokens', 'semantic_runtime.oracle_dp_io'):
        importlib.import_module(name)
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location('prepare_queries', HERE / 'prepare_oracle_queries.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    original = builder.source_queries
    builder.ROOT = code
    builder.source_queries = lambda: original(code)
    sys.argv = ['prepare_queries', '--report', str(report)]
    builder.main()
    outside = sorted(name for name, module in sys.modules.items() if name.startswith('semantic_runtime')
                     and getattr(module, '__file__', None) and not Path(module.__file__).resolve().is_relative_to(code))
    if outside:
        raise SystemExit(f'plan builder imported product modules from outside the staged tree: {outside}')
    new = constants(code / PLANS)['PLANS']
    executable = lambda row: {key: value for key, value in row.items() if key != 'sources'}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(key for key in set(old) & set(new) if executable(old[key]) != executable(new[key]))
    if (added or removed or changed) and not allow_sql_change:
        raise SystemExit(f'executable SQL changed (added {len(added)}, removed {len(removed)}, changed {len(changed)}); '
                         'a SQL literal in serving code becomes an Oracle plan. Remove it, or pass --allow-sql-change '
                         'when the new SQL is intended. This staged tree is now modified: stage again with a new --name.')
    for engine in sorted((code / '02_BACKEND' / 'ENGINES').rglob('*.json')):
        value = read(engine)
        for name in value.get('files', {}):
            value['files'][name] = sha(code / name)
        put(engine, value)
    pipeline = code / '00_SYSTEM' / 'PIPELINE.json'
    value = read(pipeline)
    for row in value['engines'].values():
        row['sha256'] = sha(code / row['manifest'])
    # Registered workflows follow their manifests: a changed workflow file means a changed
    # manifest (file hashes, version), and PIPELINE must bind that exact manifest.
    for row in value.get('workflows', {}).get('registered', []):
        manifest = read(code / row['manifest'])
        if manifest['workflow_id'] != row['id']:
            raise SystemExit(f"workflow manifest {row['manifest']} is for {manifest['workflow_id']}, not {row['id']}")
        row['version'], row['sha256'] = manifest['version'], sha(code / row['manifest'])
    put(pipeline, value)
    sys.path[:0] = [str(ROOT / '06_TOOLS' / 'COMMANDS'), str(code / '02_BACKEND')]
    from genos_codespace_engine_preflight import check
    engines, count, errors = check(code)
    if errors:
        raise SystemExit(f'engine preflight failed after pinning: {errors}')
    return {'plans_before': len(old), 'plans_after': len(new), 'plans_added': added, 'plans_removed': removed,
            'plans_changed': changed, 'executable_sql_identical': not (added or removed or changed),
            'engines': engines, 'engine_files': count}


def cmd_pin(args) -> None:
    result = pin(args.code.resolve(), args.report.resolve(), args.allow_sql_change)
    print(json.dumps(result))


def cmd_stage(args) -> None:
    state = State(args.out)
    state.out.mkdir(parents=True, exist_ok=True)
    pointer, pointer_sha, manifest = active_now()
    base_code = ROOT / manifest['code_root']
    code = state.out / args.name
    if code.exists():
        fail(f'{rel(code)} exists; a failed or earlier stage is kept as evidence, use another --name')
    products, removals = {}, list(args.remove)
    for item in args.product:
        name, _, source = item.partition('=')
        name = name.strip().strip('/')
        source_path = (ROOT / name) if not source else Path(source) if Path(source).is_absolute() else ROOT / source
        if not source_path.is_file():
            fail(f'product source missing: {source_path}')
        if derived(name):
            fail(f'{name} is regenerated by stage; do not pass it as a product')
        products[name] = source_path.resolve()
    if not products and not removals:
        fail('nothing to stage: give --product (or --remove)')
    attempt = {'name': args.name, 'started_at': now(), 'status': 'RUNNING'}
    state.value['attempts'].append(attempt)
    state.save()
    try:
        stage_tree(args, state, attempt, pointer, pointer_sha, manifest, base_code, code, products, removals)
    except BaseException as error:
        if attempt['status'] == 'RUNNING':
            attempt.update(status='FAILED', reason=str(error)[:500], finished_at=now())
            state.save()
        raise


def stage_tree(args, state, attempt, pointer, pointer_sha, manifest, base_code, code, products, removals) -> None:
    code.mkdir()
    for name, expected in manifest['files'].items():
        target = code / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base_code / name, target)
        if sha(target) != expected:
            fail(f'selected MAIN release file differs from its manifest: {name}')
    diffs, summary = [], []
    for name, source in products.items():
        before = base_code / name if name in manifest['files'] else None
        target = code / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        text, added, removed = text_diff(name, before, target)
        diffs.append(text)
        summary.append({'path': name, 'source': rel(source), 'from_working_tree': source == (ROOT / name).resolve(),
                        'sha256': sha(target), 'base_sha256': manifest['files'].get(name), 'new_file': before is None,
                        'lines_added': added, 'lines_removed': removed})
    for name in removals:
        if name not in manifest['files']:
            fail(f'--remove {name}: not in the selected MAIN')
        text, added, removed = text_diff(name, base_code / name, None)
        diffs.append(text)
        (code / name).unlink()
        summary.append({'path': name, 'removed': True, 'lines_removed': removed})
    (state.out / f'{args.name}-diff.patch').write_text(''.join(diffs))
    unchanged = [row['path'] for row in summary if row.get('base_sha256') == row.get('sha256')]
    if unchanged:
        fail(f'products identical to the selected MAIN: {unchanged}')

    if args.register_workflow:
        pipeline = code / '00_SYSTEM' / 'PIPELINE.json'
        value = read(pipeline)
        registered = value['workflows']['registered']
        for name in args.register_workflow:
            if name not in products:
                fail(f'--register-workflow {name}: the manifest must be a declared product')
            workflow = read(code / name)
            if any(row['id'] == workflow['workflow_id'] for row in registered):
                fail(f"--register-workflow {name}: {workflow['workflow_id']} is already registered")
            registered.append({'id': workflow['workflow_id'], 'version': workflow['version'], 'manifest': name, 'sha256': sha(code / name)})
        for entry in args.workflow_entrypoint:
            if entry not in value['workflows']['entrypoints']:
                value['workflows']['entrypoints'].append(entry)
        put(pipeline, value)
        # A release holds only engine-pinned files: pin the new workflow package (and any --engine-pin
        # product it imports) in every engine that already pins the workflow runtime. Hashes come from pin().
        pinned = sorted({str(path.relative_to(code)) for name in args.register_workflow
                         for path in (code / name).parent.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
                        | set(args.engine_pin))
        for name in args.engine_pin:
            if name not in products:
                fail(f'--engine-pin {name}: must be a declared product')
        engines = [engine for engine in sorted((code / '02_BACKEND' / 'ENGINES').rglob('*.json'))
                   if '02_BACKEND/workflow/registry.py' in read(engine).get('files', {})]
        if not engines:
            fail('--register-workflow: no engine pins the workflow runtime (02_BACKEND/workflow/registry.py)')
        for engine in engines:
            value = read(engine)
            value['files'].update({name: 'pending' for name in pinned if name not in value['files']})
            put(engine, value)
    navigation = sorted(set(products) & set(NAVIGATION_FILES))
    if navigation:
        if not args.navigation_source:
            fail(f'{navigation} changed: pass --navigation-source "<why>" to register the new navigation compiler '
                 'version (06_TOOLS/maintenance/navigation_compatibility.py register); a new derivation is refused there')
        run([PYTHON, HERE / 'navigation_compatibility.py', 'register', '--code-root', code, '--source', args.navigation_source],
            state.out / f'{args.name}-navigation.log', timeout=7200)
    probe = subprocess.run([PYTHON, str(Path(__file__).resolve()), '_pin', '--code', str(code),
                            '--report', str(state.out / f'{args.name}-sql.json'),
                            *(['--allow-sql-change'] if args.allow_sql_change else [])],
                           cwd=ROOT, capture_output=True, text=True, timeout=1800)
    (state.out / f'{args.name}-pin.log').write_text(probe.stdout + probe.stderr)
    if probe.returncode:
        attempt.update(status='FAILED', reason='pin', finished_at=now())
        state.save()
        fail(f'pin failed, see {rel(state.out / (args.name + "-pin.log"))}:\n' + probe.stderr.strip()[-1500:])
    pinned = json.loads(probe.stdout.strip().splitlines()[-1])

    files = baseline_results.inventory(code)
    changed = sorted(name for name in manifest['files'].keys() | files.keys() if manifest['files'].get(name) != files.get(name))
    unexpected = [name for name in changed if name not in products and name not in removals and not derived(name)]
    if unexpected:
        attempt.update(status='FAILED', reason='unexpected changes', finished_at=now())
        state.save()
        fail(f'unexpected changes in the staged tree: {unexpected}')
    stage = {'status': 'PASSED', 'name': args.name, 'code_root': rel(code), 'staged_at': now(),
             'base_release_id': pointer['release_id'], 'base_generation': pointer['generation'],
             'base_code_root': manifest['code_root'], 'base_manifest_path': pointer['manifest_path'],
             'base_manifest_sha256': pointer['release_manifest_sha256'], 'active_pointer': pointer,
             'active_pointer_sha256': pointer_sha, 'base_inventory_sha256': baseline_results.inventory_sha(manifest['files']),
             'data_path': manifest['data_path'], 'data_manifest_sha256': sha(ROOT / manifest['data_path'] / 'manifest.json'),
             'files': files, 'inventory_sha256': baseline_results.inventory_sha(files),
             'changed_files': changed, 'products': summary, 'navigation_registered': navigation, 'sql': pinned}
    attempt.update(status='PASSED', finished_at=now())
    state.value.update(stage=stage)
    for later in ('test', 'prepare', 'activate'):
        state.value.pop(later, None)
    state.save()
    # Same file names the hand-made audits used, for readers of older folders.
    put(state.out / 'baseline.json', {'active': pointer, 'release': {**manifest, 'data_manifest_sha256': stage['data_manifest_sha256']}})
    print(f"staged {len(files)} files on {pointer['release_id']} (gen {pointer['generation']}): {len(changed)} changed "
          f"({len(summary)} product, {len(changed) - len(summary)} derived); SQL plans {pinned['plans_before']} -> "
          f"{pinned['plans_after']}, engines {pinned['engines']}")
    for row in summary:
        mark = 'removed' if row.get('removed') else ('new' if row.get('new_file') else f"+{row['lines_added']} -{row['lines_removed']}")
        print(f"  {row['path']}: {mark}" + ('' if row.get('removed') or row['from_working_tree'] else f" (from {row['source']})"))
    print(f"diff: {rel(state.out / (args.name + '-diff.patch'))}")


# ---------------------------------------------------------------- test
def run_suite(code: Path, files: list[str], output: Path, extra: list[str] = (), log: Path | None = None) -> dict:
    listing = output.with_suffix('.files.txt')
    listing.write_text('\n'.join(files) + '\n')
    command = [PYTHON, HERE / 'run_tests.py', '--code-root', code, '--files-from', listing, '--output', output, *extra]
    with (log or output.with_suffix('.log')).open('w') as handle:
        subprocess.run([str(part) for part in command], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, timeout=7200)
    result_path = output / 'result.json'
    if not result_path.exists():
        fail(f'test run produced no result: {rel(output.with_suffix(".log"))}')
    return read(result_path)


def outcomes(tests: list[dict]) -> dict[str, str]:
    return {test['nodeid']: ('failed' if test['outcome'] == 'error' else test['outcome']) for test in tests}


def classify(candidate: dict[str, str], baseline: dict[str, str]) -> dict[str, list[str]]:
    new_failures, fixed, same_failures, missing, new_tests = [], [], [], [], []
    for nodeid in sorted(candidate.keys() | baseline.keys()):
        after, before = candidate.get(nodeid), baseline.get(nodeid)
        if after is None:
            missing.append(nodeid)
        elif after == 'failed' and before == 'failed':
            same_failures.append(nodeid)
        elif after == 'failed':
            new_failures.append(nodeid)
        elif after == 'passed' and before == 'failed':
            fixed.append(nodeid)
        if before is None and after is not None:
            new_tests.append(nodeid)
    return {'new_failures': new_failures, 'fixed': fixed, 'same_failures': same_failures,
            'missing_in_candidate': missing, 'new_tests': new_tests}


def cmd_test(args) -> None:
    state = State(args.out)
    stage = state.step('stage')
    require_same_main(stage)
    files = list(args.files)
    for listing in args.files_from:
        files += [line.strip() for line in listing.read_text().splitlines() if line.strip() and not line.startswith('#')]
    files = list(dict.fromkeys(files))
    if not files:
        fail('no test files')
    code = (ROOT / stage['code_root']).resolve()
    base_code = (ROOT / stage['base_code_root']).resolve()
    if baseline_results.inventory_sha(baseline_results.inventory(code)) != stage['inventory_sha256']:
        fail('the staged tree changed after stage; stage again with a new --name')
    base_inventory = baseline_results.inventory_sha(baseline_results.inventory(base_code))
    if base_inventory != stage['base_inventory_sha256']:
        fail(f"the selected MAIN code tree {stage['base_code_root']} no longer matches its manifest")
    runs = state.out / 'tests'
    runs.mkdir(exist_ok=True)
    label = datetime.now().strftime('%H%M%S')

    print(f'candidate: {len(files)} files on {stage["code_root"]}', flush=True)
    candidate = run_suite(code, files, runs / f'{label}-candidate')
    baseline, cached, missing = {}, [], []
    if not args.rerun_baseline:
        for name in files:
            entry = baseline_results.load(base_inventory, name)
            if entry is None:
                missing.append(name)
            else:
                cached.append(name)
                baseline.update(outcomes(entry['tests']))
    else:
        missing = list(files)
    print(f'baseline {stage["base_release_id"]}: {len(cached)} files from the stored baseline, running {len(missing)}', flush=True)
    base_run = None
    if missing:
        base_run = run_suite(base_code, missing, runs / f'{label}-baseline')
        baseline.update(outcomes(base_run['tests']))
    first = classify(outcomes(candidate['tests']), baseline)

    # Order, stale cache or flakiness: rerun every differing file alone on both trees.
    suspects = sorted({nodeid.split('::')[0] for key in ('new_failures', 'fixed', 'missing_in_candidate')
                       for nodeid in first[key]})
    confirm = {}
    if suspects:
        print(f'confirming {len(suspects)} files alone on both trees', flush=True)
        alone = ['--batch-seconds', '0.001', '--no-baseline-save']
        after = outcomes(run_suite(code, suspects, runs / f'{label}-confirm-candidate', alone)['tests'])
        before = outcomes(run_suite(base_code, suspects, runs / f'{label}-confirm-baseline', alone)['tests'])
        confirm = classify(after, before)
    confirmed = set(confirm.get('new_failures', [])) if suspects else set()
    still_missing = set(confirm.get('missing_in_candidate', [])) if suspects else set()
    result = {
        'files': files, 'candidate_counts': candidate['counts'], 'candidate_wall_seconds': candidate['wall_seconds'],
        'baseline_files_cached': cached, 'baseline_files_run': missing,
        'baseline_wall_seconds': base_run['wall_seconds'] if base_run else 0,
        'first_pass': {key: len(value) for key, value in first.items()},
        'new_failures': sorted(nodeid for nodeid in first['new_failures'] if nodeid in confirmed),
        'not_reproduced_alone': sorted(nodeid for nodeid in first['new_failures'] if nodeid not in confirmed),
        'fixed': sorted(nodeid for nodeid in first['fixed'] if nodeid in set(confirm.get('fixed', []))),
        'same_failures': first['same_failures'],
        'missing_in_candidate': sorted(nodeid for nodeid in first['missing_in_candidate'] if nodeid in still_missing),
        'new_tests': first['new_tests'],
        'candidate_incomplete_batches': candidate['incomplete_batches'],
        'candidate_code_unchanged': candidate.get('code_unchanged'),
        'isolation_violations': candidate.get('isolation_violations'),
        'same_bytes_outside_code_root': candidate.get('same_bytes_outside_code_root'),
        'runs': rel(runs),
    }
    problems = []
    if result['new_failures']:
        problems.append(f"{len(result['new_failures'])} new failures")
    if result['missing_in_candidate']:
        problems.append(f"{len(result['missing_in_candidate'])} tests missing in the candidate")
    if candidate['incomplete_batches']:
        problems.append(f"{len(candidate['incomplete_batches'])} incomplete candidate batches")
    if not candidate.get('code_unchanged') or candidate.get('isolation_violations'):
        problems.append('code tree changed or isolation violated')
    result['status'] = 'FAILED' if problems else 'PASSED'
    result['problems'] = problems
    result['inventory_sha256'] = stage['inventory_sha256']
    put(state.out / 'regression-compare.json', result)
    state.value['test'] = {**{key: value for key, value in result.items() if key not in ('same_failures', 'new_tests')},
                           'same_failures': len(result['same_failures']), 'new_tests': len(result['new_tests']),
                           'record': rel(state.out / 'regression-compare.json'),
                           'record_sha256': sha(state.out / 'regression-compare.json'), 'tested_at': now()}
    for later in ('prepare', 'activate'):
        state.value.pop(later, None)
    state.save()
    counts = candidate['counts']
    print(f"candidate {counts.get('passed', 0)} passed / {counts.get('failed', 0) + counts.get('error', 0)} failed "
          f"in {candidate['wall_seconds']}s; baseline {'cached' if not missing else str(result['baseline_wall_seconds']) + 's'}")
    print(f"new failures {len(result['new_failures'])}, fixed {len(result['fixed'])}, already failing "
          f"{len(result['same_failures'])}, not reproduced alone {len(result['not_reproduced_alone'])}, "
          f"new tests {len(result['new_tests'])}")
    for nodeid in result['new_failures']:
        print('  NEW FAILURE ' + nodeid)
    for nodeid in result['missing_in_candidate']:
        print('  MISSING ' + nodeid)
    print(f"{result['status']}: {rel(state.out / 'regression-compare.json')}" + (f" ({'; '.join(problems)})" if problems else ''))
    raise SystemExit(0 if not problems else 1)


# ---------------------------------------------------------------- prepare
def check_products(stage: dict) -> dict:
    """Working-tree product files must still be the staged bytes (the working code keeps the change)."""
    drifted = [row['path'] for row in stage['products'] if not row.get('removed') and row['from_working_tree']
               and (not (ROOT / row['path']).exists() or sha(ROOT / row['path']) != row['sha256'])]
    if drifted:
        fail(f'working-tree product files changed after stage: {drifted}; stage again with a new --name')
    return {row['path']: row['sha256'] for row in stage['products'] if not row.get('removed')}


def cmd_prepare(args) -> None:
    state = State(args.out)
    stage, test = state.step('stage'), state.step('test')
    pointer, manifest = require_same_main(stage)
    code = ROOT / stage['code_root']
    files = baseline_results.inventory(code)
    if baseline_results.inventory_sha(files) != stage['inventory_sha256'] or test['inventory_sha256'] != stage['inventory_sha256']:
        fail('the staged tree differs from what was tested')
    if sha(ROOT / test['record']) != test['record_sha256']:
        fail('the test record changed after test')
    products = check_products(stage)
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    from semantic_runtime.release_integration import draft
    integration = draft(ROOT, pointer, files)
    per_file = dict(item.split('=', 1) for item in args.file_reason)
    for row in integration['changes']:
        name = row['path']
        if name in per_file:
            row['reason'] = per_file[name]
        elif derived(name):
            row['reason'] = 'Derived from the product change (engine pin, PIPELINE hash, Oracle plan metadata or ' \
                            'navigation registry), regenerated by main_release.py stage: ' + args.reason
        elif name in products or name in [row['path'] for row in stage['products']]:
            row['reason'] = args.reason
        else:
            fail(f'undeclared change {name}')
    evidence = {}
    for item in args.evidence:
        name, _, path = item.partition('=')
        path = Path(path) if Path(path).is_absolute() else ROOT / path
        evidence[name] = {'path': rel(path), 'sha256': sha(path)}
    put(state.out / 'integration.json', integration)
    authorization = {
        'authorized_by': 'user', 'authorization_text': args.authorization_text,
        'scope': args.scope or (f"{stage['base_release_id']} + " + ', '.join(row['path'] for row in stage['products'])
                                + ' + derived pins'),
        'quality_gate_override': True, 'deployment_basis': 'USER_DIRECTED_CUTOVER', 'quality_certified': False,
        'rollback_pipeline': {'path': stage['base_code_root'] + '/00_SYSTEM/PIPELINE.json',
                              'sha256': manifest['files']['00_SYSTEM/PIPELINE.json']},
        'limits': args.limit or ['Contract tests on the staged tree; no field GENOS, ORDS or real model run.']}
    put(state.out / 'authorization.json', authorization)
    validation = {
        'structural_checks_passed': True, 'integration': integration,
        'contract_checks': test['candidate_counts'].get('passed', 0),
        'regression_compare': {'path': test['record'], 'sha256': test['record_sha256'],
                               'new_failures': len(test['new_failures']), 'already_failing': test['same_failures']},
        'staged_files': len(files), 'staged_inventory_sha256': stage['inventory_sha256'], 'sql': stage['sql'],
        'evidence': evidence, 'quality_certified': False, 'external_model_calls': args.model_calls,
        'tool': 'main_release.py'}
    put(state.out / 'validation.json', validation)
    release = ROOT / '08_DEPLOYMENT' / 'RELEASES' / args.release_id / 'release.json'
    if release.parent.exists():
        fail(f'{rel(release.parent)} exists; choose another --release-id')
    run([PYTHON, ROOT / '06_TOOLS' / 'run_tool.py', 'rag_main_promotion.py', 'prepare', '--code-root', code,
         '--generation', ROOT / stage['data_path'], '--release-id', args.release_id,
         '--authorization', state.out / 'authorization.json', '--validation', state.out / 'validation.json'],
        state.out / 'prepare.log', timeout=1800)
    prepared = read(release)
    if prepared['files'] != files:
        only = sorted(set(files) ^ set(prepared['files']))
        fail(f'the prepared release does not hold exactly the staged files (difference {only[:10]}); a product outside '
             'the copied release layout is not served')
    if any(sha(ROOT / prepared['code_root'] / name) != value for name, value in files.items()):
        fail('prepared release bytes differ from the staged tree')
    put(state.out / 'release-prepared.json', {'manifest': rel(release), 'sha256': sha(release), 'code_root': prepared['code_root']})
    state.value['prepare'] = {'status': 'PASSED', 'release_id': args.release_id, 'manifest': rel(release),
                              'manifest_sha256': sha(release), 'code_root': prepared['code_root'],
                              'changes': len(integration['changes']), 'prepared_at': now()}
    state.value.pop('activate', None)
    state.save()
    print(f"prepared {args.release_id}: {len(files)} files, {len(integration['changes'])} changes; MAIN unchanged")


# ---------------------------------------------------------------- activate / entry check / rollback
def replace_file(source: Path, target: Path) -> None:
    temporary = target.with_name('.' + target.name + '.main-release')
    temporary.write_bytes(source.read_bytes())
    os.replace(temporary, target)


def entry_checks(state: State) -> dict:
    """Generic checks after selection: the real root service resolves the new release, nothing else moved."""
    import importlib
    import importlib.util
    stage, prepare = state.step('stage'), state.step('prepare')
    os.environ.update(AD_WORKER_ENABLED='0', GENOS_AUTO_WARMUP='0', GENOS_RESIDENT_DATA='off',
                      GENOS_RUNTIME_DIR=str(state.out / 'entry-runtime'))
    for key in ('DP', 'GENOS_GENERATION', 'GENOS_DATA_ROOT'):
        os.environ.pop(key, None)
    sys.path[:0] = [str(ROOT), str(ROOT / '02_BACKEND')]
    import service  # noqa: F401
    actual = importlib.import_module('service.service')
    code, generation, binding = actual._resolve_binding()
    active = read(ACTIVE)
    release = read(ROOT / active['manifest_path'])
    rollback = ROOT / active['manifest_path'].replace('release.json', 'rollback/ACTIVE_RELEASE.json')
    checks = {
        'real_root_service': Path(actual.__file__).resolve() == ROOT / 'service.py',
        'next_main': active['generation'] == stage['base_generation'] + 1,
        'release_id': active['release_id'] == prepare['release_id'],
        'manifest_unchanged': sha(ROOT / active['manifest_path']) == prepare['manifest_sha256'],
        'resolved_code': code == ROOT / release['code_root'],
        'local_release_mode': binding.get('mode') == 'local-release',
        'source_generation_unchanged': generation == ROOT / stage['data_path'],
        'source_manifest_unchanged': sha(generation / 'manifest.json') == stage['data_manifest_sha256'],
        'release_files_are_staged': release['files'] == stage['files'],
        'working_products_match_selected': all(sha(ROOT / row['path']) == release['files'][row['path']]
                                               for row in stage['products'] if not row.get('removed') and row['from_working_tree']),
        'rollback_previous': rollback.exists() and sha(rollback) == release['previous_active_sha256']
                             and read(rollback) == stage['active_pointer'],
    }
    probe = subprocess.run([PYTHON, '-I', '-c', """import json,sys
sys.dont_write_bytecode=True
out={}
for root in sys.argv[1:]:
    for name in [n for n in list(sys.modules) if n.startswith('semantic_runtime')]: del sys.modules[name]
    sys.path.insert(0,root)
    import semantic_runtime.oracle_development_mapping as d, semantic_runtime.oracle_gold_mapping as g
    m=d.DevelopmentMapping.load()
    out[root]={'file':d.__file__,'agents':dict(m.agent_tables),'doc_ver':m.physical_table('DOC_VER'),
      'ontology':[m.physical_table(k) for k in ('ONTL_POST','ONTL_HEAD','ONTL_ANC')],
      'gold':g.GoldMapping.load(owner='APP_GOLD').target_sha256}
    sys.path.remove(root)
print(json.dumps(out,default=str))""", str(code / '02_BACKEND'), str(ROOT / stage['base_code_root'] / '02_BACKEND')],
                           capture_output=True, text=True, timeout=120)
    if probe.returncode:
        checks['mappings_load'] = False
        mappings = {'error': probe.stderr.strip()[-1500:]}
        print('mapping probe failed: ' + mappings['error'][-500:], file=sys.stderr)
    else:
        loaded = json.loads(probe.stdout.strip().splitlines()[-1])
        new, old = loaded[str(code / '02_BACKEND')], loaded[str(ROOT / stage['base_code_root'] / '02_BACKEND')]
        mapping_products = any('oracle_' in row['path'] and 'mapping' in row['path'] or row['path'].startswith('00_SYSTEM/ORACLE/')
                               for row in stage['products'])
        checks['mappings_from_selected_code'] = Path(new['file']).resolve().is_relative_to(code)
        if not mapping_products:
            checks['mappings_same_as_previous_main'] = all(new[key] == old[key] for key in ('agents', 'doc_ver', 'ontology', 'gold'))
        mappings = {'selected': new, 'previous': old, 'mapping_files_changed': mapping_products}
    registries = [ROOT / root / NAVIGATION_REGISTRY for root in (release['code_root'], stage['base_code_root'])]
    if all(path.exists() for path in registries):
        def versions(path):
            return {json.dumps(version['modules'], sort_keys=True) for group in read(path)['groups'] for version in group['versions']}
        # Oracle rows published with any earlier compiler version must still be accepted.
        checks['navigation_versions_kept'] = versions(registries[1]) <= versions(registries[0])
    errors = {}
    if GOLD_BINDING.exists():
        try:
            spec = importlib.util.spec_from_file_location('main_release_gold_entry', GOLD_BINDING.parent / 'connect.py')
            connector = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(connector)
            gold = connector.engine_binding()
        except Exception as error:  # recorded as a failed check, then the caller rolls back
            checks['gold_connector_loads'] = False
            errors['gold_connector'] = repr(error)[:1000]
        else:
            checks.update(gold_same_engine=gold['engine_files'] == release['files'],
                          gold_same_manifest=gold['engine_manifest_sha256'] == sha(ROOT / active['manifest_path']),
                          gold_data_unchanged=gold['data_path'] == stage['data_path'])
    return {'passed': all(checks.values()), 'checks': checks, 'errors': errors, 'binding': binding, 'mappings': mappings,
            'model_calls': 0, 'oracle_calls': 0, 'checked_at': now()}


def cmd_entry_check(args) -> None:
    state = State(args.out)
    result = entry_checks(state)
    put(state.out / 'entry-check.json', result)
    failed = [name for name, ok in result['checks'].items() if not ok]
    print(f"entry checks {len(result['checks']) - len(failed)}/{len(result['checks'])}" + (f' FAILED {failed}' if failed else ''))
    for name, error in result['errors'].items():
        print(f'  {name}: {error}')
    raise SystemExit(0 if not failed else 1)


def rollback_now(state: State, release_id: str, gold_backup: Path | None, gold_prepared: dict | None) -> None:
    if read(ACTIVE).get('release_id') == release_id:
        run([PYTHON, ROOT / '06_TOOLS' / 'run_tool.py', 'rag_main_promotion.py', 'rollback', '--confirm-main'],
            state.out / f'rollback-{datetime.now().strftime("%H%M%S")}.log', timeout=600)
    if gold_backup and gold_backup.exists() and gold_prepared is not None and GOLD_BINDING.exists() \
            and read(GOLD_BINDING) == gold_prepared:
        replace_file(gold_backup, GOLD_BINDING)


def cmd_activate(args) -> None:
    state = State(args.out)
    stage, test, prepare = state.step('stage'), state.step('test'), state.step('prepare')
    pointer, _ = require_same_main(stage)
    release_path = ROOT / prepare['manifest']
    if sha(release_path) != prepare['manifest_sha256']:
        fail('the prepared release manifest changed')
    release = read(release_path)
    if release['files'] != stage['files'] or test['inventory_sha256'] != stage['inventory_sha256']:
        fail('the prepared release is not the tested staged tree')
    if any(sha(ROOT / release['code_root'] / name) != value for name, value in release['files'].items()):
        fail('prepared release bytes changed')
    check_products(stage)
    gold_backup = gold_prepared = None
    if GOLD_BINDING.exists():
        old = read(GOLD_BINDING)
        if old.get('engine_release_id') != stage['base_release_id']:
            fail(f"the local Gold binding uses {old.get('engine_release_id')}, not the selected MAIN {stage['base_release_id']}")
        gold_backup = state.out / 'gold-before.json'
        gold_backup.write_bytes(GOLD_BINDING.read_bytes())
        gold_prepared = {**old, 'engine_root': release['code_root'], 'engine_files': release['files'],
                         'engine_release_id': release['release_id'], 'engine_manifest_sha256': sha(release_path),
                         'inference_status': args.inference_status,
                         'main_authorization': {'release_id': release['release_id'],
                                                'authorization_sha256': release['authorization_sha256'],
                                                'validation_sha256': release['validation_sha256']}}
        gold_prepared.pop('engine_candidate_revision', None)
        put(state.out / 'gold-prepared.json', gold_prepared)
    try:
        run([PYTHON, ROOT / '06_TOOLS' / 'run_tool.py', 'rag_main_promotion.py', 'apply', '--manifest', release_path,
             '--confirm-main'], state.out / 'apply.log', timeout=1800)
        if gold_prepared is not None:
            if sha(GOLD_BINDING) != sha(gold_backup):
                raise RuntimeError('the local Gold binding changed during activation')
            replace_file(state.out / 'gold-prepared.json', GOLD_BINDING)
        run([PYTHON, Path(__file__).resolve(), 'entry-check', '--out', state.out], state.out / 'entry-check.log', timeout=600)
        for script in args.extra_check:
            run([PYTHON, script], state.out / f'extra-check-{Path(script).stem}.log', timeout=1800,
                env={**os.environ, 'MAIN_RELEASE_OUT': str(state.out)})
    except BaseException as error:
        rollback_now(state, release['release_id'], gold_backup, gold_prepared)
        state.value['activate'] = {'status': 'ROLLED_BACK', 'error': repr(error)[:1000], 'at': now()}
        state.save()
        fail(f'activation failed and was rolled back: {error!r}; logs in {rel(state.out)}')
    active = read(ACTIVE)
    activation = {'active': active, 'checks': read(state.out / 'entry-check.json'), 'files': len(release['files']),
                  'changed': prepare['changes'],
                  'rollback_gold': rel(gold_backup) if gold_backup else None, 'genos_deployed': False,
                  'external_model_calls': 0}
    put(state.out / 'activation.json', activation)
    state.value['activate'] = {'status': 'PASSED', 'release_id': release['release_id'], 'generation': active['generation'],
                               'active_pointer_sha256': sha(ACTIVE), 'extra_checks': list(map(str, args.extra_check)),
                               'activated_at': now()}
    state.save()
    checks = activation['checks']['checks']
    print(f"MAIN {active['generation']} = {release['release_id']}; entry checks {sum(checks.values())}/{len(checks)}; "
          f"previous {pointer['release_id']} kept for rollback")


def cmd_rollback(args) -> None:
    state = State(args.out)
    activate = state.value.get('activate') or {}
    release_id = (state.value.get('prepare') or {}).get('release_id')
    if activate.get('status') != 'PASSED' or not release_id:
        fail('this OUT has no passed activation')
    if read(ACTIVE).get('release_id') != release_id:
        fail(f"{release_id} is not the selected MAIN any more; nothing rolled back")
    gold_prepared = read(state.out / 'gold-prepared.json') if (state.out / 'gold-prepared.json').exists() else None
    rollback_now(state, release_id, state.out / 'gold-before.json', gold_prepared)
    state.value['activate'] = {**activate, 'status': 'ROLLED_BACK', 'rolled_back_at': now()}
    state.save()
    print(f"rolled back {release_id}; MAIN is {read(ACTIVE)['release_id']} gen {read(ACTIVE)['generation']}")


def cmd_status(args) -> None:
    state = State(args.out)
    for name in ('stage', 'test', 'prepare', 'activate'):
        value = state.value.get(name) or {}
        detail = {'stage': lambda v: f"{v.get('base_release_id')} + {len(v.get('products', []))} products",
                  'test': lambda v: f"new failures {len(v.get('new_failures', []))}, already failing {v.get('same_failures')}",
                  'prepare': lambda v: v.get('release_id'),
                  'activate': lambda v: f"gen {v.get('generation')}"}[name](value) if value else ''
        print(f"{name:9s} {value.get('status', '-'):12s} {detail}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    stage = sub.add_parser('stage')
    stage.add_argument('--out', type=Path, required=True)
    stage.add_argument('--name', default='staged')
    stage.add_argument('--product', action='append', default=[], help='PATH or PATH=SOURCE (repeatable)')
    stage.add_argument('--remove', action='append', default=[])
    stage.add_argument('--allow-sql-change', action='store_true')
    stage.add_argument('--navigation-source', help='reason recorded when a navigation compiler file changed')
    stage.add_argument('--register-workflow', action='append', default=[],
                       help='workflow manifest (a declared product) to add to PIPELINE workflows.registered')
    stage.add_argument('--workflow-entrypoint', action='append', default=[],
                       help='entry point label added to PIPELINE workflows.entrypoints (with --register-workflow)')
    stage.add_argument('--engine-pin', action='append', default=[],
                       help='new product file to pin in the engines with --register-workflow (a module the new workflow imports)')
    test = sub.add_parser('test')
    test.add_argument('--out', type=Path, required=True)
    test.add_argument('--files-from', type=Path, action='append', default=[])
    test.add_argument('files', nargs='*')
    test.add_argument('--rerun-baseline', action='store_true', help='ignore the stored baseline of the selected MAIN')
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--out', type=Path, required=True)
    prepare.add_argument('--release-id', required=True)
    prepare.add_argument('--reason', required=True)
    prepare.add_argument('--authorization-text', required=True)
    prepare.add_argument('--scope')
    prepare.add_argument('--limit', action='append', default=[])
    prepare.add_argument('--file-reason', action='append', default=[], help='PATH=TEXT')
    prepare.add_argument('--evidence', action='append', default=[], help='NAME=PATH of a change-specific result')
    prepare.add_argument('--model-calls', type=int, default=0)
    activate = sub.add_parser('activate')
    activate.add_argument('--out', type=Path, required=True)
    activate.add_argument('--extra-check', type=Path, action='append', default=[])
    activate.add_argument('--inference-status', default='USER_DIRECTED_NOT_QUALITY_CERTIFIED')
    for name in ('entry-check', 'rollback', 'status'):
        sub.add_parser(name).add_argument('--out', type=Path, required=True)
    hidden = sub.add_parser('_pin')
    hidden.add_argument('--code', type=Path, required=True)
    hidden.add_argument('--report', type=Path, required=True)
    hidden.add_argument('--allow-sql-change', action='store_true')
    args = parser.parse_args()
    {'stage': cmd_stage, 'test': cmd_test, 'prepare': cmd_prepare, 'activate': cmd_activate,
     'entry-check': cmd_entry_check, 'rollback': cmd_rollback, 'status': cmd_status, '_pin': cmd_pin}[args.command](args)


if __name__ == '__main__':
    main()
