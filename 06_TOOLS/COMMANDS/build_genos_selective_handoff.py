"""Build compatible replacements without modifying earlier mail attachments."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / '08_DEPLOYMENT/GENOS/patches'
OUT = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-selective-compatible-r1'
CORE_PATH = ROOT / '06_TOOLS/OFFLINE/genos_selective_patch.py'
definition = importlib.util.spec_from_file_location('selective_core', CORE_PATH)
core = importlib.util.module_from_spec(definition)
definition.loader.exec_module(core)
definition = importlib.util.spec_from_file_location('decision_transform', ROOT / '06_TOOLS/OFFLINE/genos_decision_transform.py')
decision = importlib.util.module_from_spec(definition)
definition.loader.exec_module(decision)
FROZEN_BASE = ROOT / '08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-20260929-r1/code'
FROZEN_NEW = ROOT / '08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-repair-20260929-r1/code'
PACKAGES = {
    'answer-stream': 'answer_stream_20260929_r1',
    'prompt-compaction': 'prompt_compaction_20260928_r1',
    'chat-flow': 'chat_flow_20260928_r2',
    'request-unlimited': 'request_unlimited_20260928_r1',
    'latency': 'latency_20260928_r2',
    'relation-wait': 'relation_wait_20260928_r1',
    'final-review-off': 'final_review_disabled_20260928_r1',
    'proposal-retry': 'proposal_retry_20260928_r1',
    'sse-startup': 'sse_startup_20260928_r1',
    'response-overhead': 'response_overhead_20260928_r3',
    'team-logs': 'team_request_logs_20260928_r3',
    'thinking-log': 'thinking_log_20260928_r3',
    'fulltext-diagnostics': 'fulltext_diagnostics_20260928_r1',
    'fulltext-location': 'fulltext_location_20260929_r2',
    'request-prepare': 'request_prepare_20260929_r1',
}
DELEGATE = {'response-overhead', 'team-logs', 'thinking-log', 'fulltext-diagnostics',
            'fulltext-location', 'request-prepare'}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bundle = OUT / 'bundle'
    bundle.mkdir(exist_ok=True)
    assets = {}

    def put(name, raw):
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        assets[name] = core.sha(raw)
        return name

    def blob(raw):
        return put('blobs/' + core.sha(raw), raw)

    put('apply.py', CORE_PATH.read_bytes())
    put('decision_transform.py', (ROOT / '06_TOOLS/OFFLINE/genos_decision_transform.py').read_bytes())
    files = {}
    bounded = '02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py'
    gateway = '02_BACKEND/semantic_runtime/legal_agent/gateway.py'
    progress = '02_BACKEND/semantic_runtime/progress.py'
    photo = {
        bounded: (PATCHES / 'prompt_compaction_20260928_r1/payload' / bounded).read_bytes(),
        gateway: (PATCHES / 'answer_stream_20260929_r1/payload' / gateway).read_bytes(),
        progress: (PATCHES / 'chat_flow_20260928_r2/payload' / progress).read_bytes(),
    }
    targets = {
        bounded: ['_Protocol.__init__', '_Protocol.validate', 'BoundedSourceSession.structured',
                  'BoundedSourceSession.prepare_question_plan', 'BoundedSourceSession.plan_request_search',
                  'BoundedSourceSession.catalogue_observation'],
        gateway: ['ModelGateway.generate'],
        progress: ['_EVENTS', 'ProgressCapture.emit'],
    }
    for name, qualified_names in targets.items():
        nodes = []
        for qualified in qualified_names:
            variants = []
            for label, before in [('photo', photo[name]), ('integrated', (FROZEN_BASE / name).read_bytes())]:
                before_node = decision.node_for(before, qualified)
                if before_node is None:
                    continue
                after = (FROZEN_NEW / name).read_bytes()
                if name == bounded and qualified == 'BoundedSourceSession.structured':
                    # The photographed checkout uses the older multi-case query
                    # schema. Validate it inside the same repairable call too.
                    marker = "        if phase in ('source-triage', 'source-omission-review'):"
                    hook = """        if phase == 'source-query-plan' and 'cases' in data and validator is None:
            validator = lambda value: source_query_planning.validate(value, data['cases'], data['law_names'])
"""
                    after = after.replace(marker.encode(), (hook + marker).encode(), 1)
                if name == progress:
                    # Apply only the repair display delta; retain the site's
                    # earlier event/journal handling byte for byte.
                    after = before.replace(b'    "model.attempt.accepted":',
                        '    "model.output.invalid": ("repair", "모델 응답 형식을 확인 중"),\n    "model.attempt.accepted":'.encode(), 1)
                    marker = b'        kind, label = mapped\n'
                    hook = '''        if name == "model.output.invalid":
            label = ("모델 응답의 형식·판단 오류를 수정하도록 재요청 중"
                     if fields.get("repair_scheduled") is True
                     else "모델 응답의 형식·판단 오류 수정 횟수를 소진함")
'''.encode()
                    after = after.replace(marker, marker + hook, 1)
                after_node = decision.node_for(after, qualified)
                key = str(len(assets))
                template = decision.snippet(after, after_node)[2]
                if '.' in qualified:
                    template = ('class ' + qualified.split('.')[0] + ':\n').encode() + template
                asset_name = put('decision/' + key + '.py', template)
                variants.append({'before_ast': decision.signature(before_node),
                                 'after_ast': decision.signature(after_node), 'after': asset_name})
                # Preserve already installed R1 repair functions too. The new
                # legacy-schema hook remains necessary only on the old path.
                old_repair = decision.node_for((FROZEN_NEW / name).read_bytes(), qualified)
                if old_repair and (name != progress or label == 'integrated') and decision.signature(old_repair) != decision.signature(after_node):
                    variants.append({'before_ast': decision.signature(old_repair),
                                     'after_ast': decision.signature(after_node), 'after': asset_name})
            nodes.append({'qualified': qualified, 'variants': variants,
                          'optional': qualified in ('BoundedSourceSession.plan_request_search',
                                                    'BoundedSourceSession.catalogue_observation')})
        files[name] = {'nodes': nodes}
    requirements = [
        {'path': '02_BACKEND/semantic_runtime/legal_agent/source_selection.py', 'token': 'def checked_choices('},
        {'path': '02_BACKEND/semantic_runtime/legal_agent/source_query_planning.py', 'token': 'def validate('},
        {'path': '02_BACKEND/semantic_runtime/legal_agent/question_obligations.py', 'token': 'def prepare_plan('},
        {'path': '02_BACKEND/semantic_runtime/legal_agent/obligation_protocol.py', 'token': 'def meaningful('},
        {'path': '02_BACKEND/semantic_runtime/legal_agent/errors.py', 'token': 'class StaleProposal('},
    ]
    features = {'decision-repair': {'strategy': 'decision', 'transformer': 'decision_transform.py',
        'files': files, 'requirements': requirements, 'assets': dict(assets),
        'source_patch': 'model-decision-repair-20260929-r2', 'workflow_change': False}}
    repaired_photo = {name: decision.transform(raw, files[name], bundle) for name, raw in photo.items()}
    # Exact preserved preimages are located by digest, never by date or filename.
    specs = {key: json.loads((PATCHES / folder / 'PATCH_MANIFEST.json').read_bytes())
             for key, folder in PACKAGES.items()}
    wanted = set()
    for key, spec in specs.items():
        if key not in DELEGATE:
            wanted.update(Path(name).name for name in spec['files'])
    cache = {}
    for root_name in ('08_DEPLOYMENT', '09_ARTIFACTS/AUDITS', '90_RUNTIME/diagnostics'):
        for path in (ROOT / root_name).rglob('*'):
            if path.name in wanted and path.is_file() and not path.is_symlink():
                raw = path.read_bytes()
                cache.setdefault(core.sha(raw), (raw, str(path.relative_to(ROOT))))
    for root_name in ('08_DEPLOYMENT/GENOS/patches', '09_ARTIFACTS/HANDOFFS'):
        for path in (ROOT / root_name).rglob('*.zip'):
            if path.parent == OUT:
                continue
            with zipfile.ZipFile(path) as zipped:
                for name in zipped.namelist():
                    if Path(name).name in wanted:
                        raw = zipped.read(name)
                        cache.setdefault(core.sha(raw), (raw, str(path.relative_to(ROOT)) + ':' + name))

    def preserved(expected, name):
        if expected is None:
            return None
        if expected not in cache:
            result = subprocess.run(['git', 'show', 'HEAD:' + name], cwd=ROOT, capture_output=True)
            if result.returncode == 0 and core.sha(result.stdout) == expected:
                cache[expected] = (result.stdout, 'HEAD:' + name)
        if expected not in cache:
            # This earlier builder retained an explicit inverse recipe instead
            # of files. Evaluate only its read-only preimage statements against
            # its immutable payload, then require the recorded baseline digest.
            package = PATCHES / 'final_review_disabled_20260928_r1'
            source = ast.parse((package / 'build.py').read_bytes())
            function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'build')
            statements = []
            for statement in function.body:
                if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'spec' for t in statement.targets):
                    break
                statements.append(statement)
            inverse = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'undo')
            scope = {'ROOT': package / 'payload', 'sha': core.sha}
            exec(compile(ast.Module(body=[inverse, *statements], type_ignores=[]), '<preserved-inverse-recipe>', 'exec'), scope)
            for file, raw in scope['bases'].items():
                recorded = specs['final-review-off']['files'][file]['base_sha256']
                if core.sha(raw) != recorded:
                    raise ValueError('inverse recipe differs from recorded baseline: ' + file)
                cache[recorded] = (raw, 'immutable final-review inverse recipe')
        if expected not in cache:
            raise ValueError('no preserved patch baseline: ' + name + ' ' + expected)
        return cache[expected][0]

    for key, folder in PACKAGES.items():
        start_assets = set(assets)
        package = PATCHES / folder
        spec = specs[key]
        if key in DELEGATE:
            needed = {'apply.py', 'PATCH_MANIFEST.json', *spec.get('assets', {})}
            for row in spec['files'].values():
                needed.update(row.get('assets', {}))
            for path in package.rglob('*'):
                relative = path.relative_to(package)
                if path.is_file() and path.suffix in ('.py', '.json', '.txt') and '__pycache__' not in path.parts and (
                        relative.as_posix() in needed or relative.parts[0] in ('payload', 'variants', 'functions')):
                    put('packages/' + key + '/' + path.relative_to(package).as_posix(), path.read_bytes())
            feature = {'strategy': 'delegate', 'directory': 'packages/' + key}
        else:
            feature = {'strategy': 'merge', 'files': {}}
            for name, row in spec['files'].items():
                options = []
                entries = [row]
                variants = row.get('variants', [])
                if isinstance(variants, dict):
                    entries += [{'base_sha256': h, **v, 'payload_path': v['path']} for h, v in variants.items()]
                else:
                    entries += variants
                # supported_base hashes in old installers were whole-file
                # replacement allowances. Use a real delta for each baseline.
                for entry in entries:
                    after = (package / entry.get('payload_path', 'payload/' + name)).read_bytes()
                    if core.sha(after) != entry['new_sha256']:
                        raise ValueError('source payload mismatch: ' + name)
                    bases = [entry['base_sha256'], *entry.get('supported_base_sha256', [])]
                    for expected in dict.fromkeys(bases):
                        before = preserved(expected, name)
                        options.append({'before': blob(before) if before is not None else None,
                                        'before_sha256': expected, 'after': blob(after),
                                        'after_sha256': entry['new_sha256']})
                feature['files'][name] = {'options': options}
        feature['assets'] = {n: assets[n] for n in set(assets) - start_assets}
        feature['source_patch'] = spec['patch']
        feature['workflow_change'] = key in {'answer-stream', 'chat-flow'}
        if key == 'answer-stream':
            feature['new_pins'] = {gateway: ['02_BACKEND/semantic_runtime/legal_agent/answer_stream.py']}
        elif key == 'team-logs':
            feature['new_pins'] = {'02_BACKEND/semantic_runtime/request_report.py': list(spec['files']),
                                   gateway: list(spec['files'])}
        # These two immutable MAIN releases already incorporated these older
        # mail changes. Preserve their exact published bytes, including later
        # navigation/fulltext/async-report changes. This is a digest inventory,
        # never an arbitrary "newer file" acceptance or forced replacement.
        feature['preserve_sha256'] = {}
        feature['preserve_sources'] = {}
        for name in spec['files']:
            hashes = set()
            sources = []
            for source_root in (FROZEN_BASE, FROZEN_NEW):
                source_path = source_root / name
                if source_path.exists():
                    release = json.loads((source_root.parent / 'release.json').read_bytes())
                    digest = core.sha(source_path.read_bytes())
                    if release['files'].get(name) != digest:
                        raise ValueError('immutable release source differs from its inventory: ' + name)
                    hashes.add(digest)
                    sources.append(str(source_path.relative_to(ROOT)))
            if name in photo:
                hashes.add(core.sha(photo[name]))
                hashes.add(core.sha(repaired_photo[name]))
                sources.append('photographed source plus verified R2 approved-function projection')
            if name in ('08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py', '08_DEPLOYMENT/GENOS/stream_app.py') and key in ('chat-flow', 'sse-startup'):
                downstream = PATCHES / 'answer_stream_20260929_r1/payload' / name
                digest = core.sha(downstream.read_bytes())
                if specs['answer-stream']['files'][name]['new_sha256'] != digest:
                    raise ValueError('answer-stream downstream inventory differs')
                hashes.add(digest)
                sources.append(str(downstream.relative_to(ROOT)))
            feature['preserve_sha256'][name] = sorted(hashes)
            feature['preserve_sources'][name] = sources
        # The full-code mail excludes separate SSE entry modules. An absent
        # optional entry file can be created from the selected, verified payload.
        if key not in DELEGATE:
            for name in ('08_DEPLOYMENT/GENOS/stream_app.py', '08_DEPLOYMENT/GENOS/start_sse.py'):
                if name in feature['files']:
                    first = feature['files'][name]['options'][0]
                    feature['files'][name]['options'].append({**first, 'before': None, 'before_sha256': None})
        features[key] = feature
    manifest = {'format': '8agent-selective-mail/1', 'bundle': core.BUNDLE_ID, 'features': features,
                'photo_sha256': {n: core.sha(raw) for n, raw in photo.items()},
                'generation_modified': False, 'onsite_verified': False,
                'excluded': ['full-code replacement', 'PeCab data rebuild', 'reference-main data generation']}
    put('SELECTIVE_MANIFEST.json', core.dump(manifest))
    archive = OUT / 'GENOS_SELECTIVE_20260929_R1.zip'
    rows = []
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for name in sorted(assets):
            raw = (bundle / name).read_bytes()
            rows.append({'path': name, 'bytes': len(raw), 'sha256': core.sha(raw)})
            zipped.writestr(name, raw)
        zipped.writestr('CODE_MANIFEST.json', core.dump({'format': '8agent-code/1', 'patch': core.BUNDLE_ID, 'files': rows}))
    archive_sha = core.sha(archive.read_bytes())
    txt = OUT / 'GENOS_SELECTIVE_20260929_R1_APPLY.txt'
    # ZIP stays alongside this TXT, matching the previous mail handoff format.
    header = '''#!/usr/bin/env bash
set -Eeuo pipefail
SELECTIVE_RUN="$(mktemp -d /tmp/genos-selective-XXXXXXXX)"
exec > >(tee -a "$SELECTIVE_RUN/run.log") 2>&1
trap 'code=$?; printf "FINISHED exit=%s log=%s\\n" "$code" "$SELECTIVE_RUN/run.log"' EXIT
printf 'START GENOS selective-compatible R1 log=%s\\n' "$SELECTIVE_RUN/run.log"
SELECTIVE_SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SELECTIVE_ZIP="$SELECTIVE_SOURCE/GENOS_SELECTIVE_20260929_R1.zip"
printf '%s  %s\\n' 'ARCHIVE_SHA' "$SELECTIVE_ZIP" | sha256sum -c -
SELECTIVE_ROOT="$(realpath -e -- "${DEPLOY_ROOT:-$HOME/DEV}")"
SELECTIVE_PY="${PYTHON_BIN:-$SELECTIVE_ROOT/.venv/bin/python}"
if [[ ! -x "$SELECTIVE_PY" ]]; then SELECTIVE_PY="$(command -v python3)"; fi
"$SELECTIVE_PY" - "$SELECTIVE_ZIP" "$SELECTIVE_RUN/bundle" <<'PY_EXTRACT'
import hashlib,json,sys,zipfile
from pathlib import Path,PurePosixPath
target=Path(sys.argv[2]);target.mkdir()
with zipfile.ZipFile(sys.argv[1]) as z:
 names=z.namelist();assert len(names)==len(set(names)), 'duplicate ZIP member'
 rows=json.loads(z.read('CODE_MANIFEST.json'))['files']
 assert set(names)=={r['path'] for r in rows}|{'CODE_MANIFEST.json'},'unexpected ZIP member'
 for row in rows:
  name=row['path'];p=PurePosixPath(name)
  assert not p.is_absolute() and '..' not in p.parts and str(p)==name and '\\\\' not in name,'unsafe ZIP path'
  assert (z.getinfo(name).external_attr>>16)&0o170000!=0o120000,'ZIP symlink'
  raw=z.read(name);assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'ZIP hash mismatch'
  path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
PY_EXTRACT
printf 'CHECKOUT=%s PYTHON=%s SELECT=%s MODE=%s\\n' "$SELECTIVE_ROOT" "$SELECTIVE_PY" "${SELECT:-decision-repair}" "${MODE:-apply}"
case "${MODE:-apply}" in
 apply|check)
   "$SELECTIVE_PY" "$SELECTIVE_RUN/bundle/apply.py" --deploy-root "$SELECTIVE_ROOT" --feature "${SELECT:-decision-repair}" --mode "${MODE:-apply}"
   git -C "$SELECTIVE_ROOT" diff --check
   ;;
 rollback)
   : "${ROLLBACK_FROM:?BACKUP_READY의 경로를 지정하세요}"
   "$SELECTIVE_PY" "$SELECTIVE_RUN/bundle/apply.py" --deploy-root "$SELECTIVE_ROOT" --feature "${SELECT:-decision-repair}" --mode rollback --rollback-from "$ROLLBACK_FROM"
   ;;
 verify)
   : "${GENOS_GENERATION:?실제 선택된 generation 절대경로를 지정하세요}"
   "$SELECTIVE_PY" "$SELECTIVE_ROOT/06_TOOLS/COMMANDS/genos_release_gate.py" --code-zip "$SELECTIVE_ROOT/TRANSFER/genos-selective-20260929-r1/applied-code.zip" --deploy-root "$SELECTIVE_ROOT" --generation "$GENOS_GENERATION"
   ;;
 *) printf 'MODE must be apply, check, rollback or verify\\n' >&2; exit 2 ;;
esac
'''.replace('ARCHIVE_SHA', archive_sha)
    txt.write_text(header)
    subprocess.run(['bash', '-n', str(txt)], check=True)
    delivery = {'bundle': core.BUNDLE_ID, 'archive': archive.name, 'archive_sha256': archive_sha,
                'apply_txt': txt.name, 'apply_txt_sha256': core.sha(txt.read_bytes()),
                'features': list(features), 'photo_sha256': manifest['photo_sha256'],
                'genos_deployed': False, 'email_sent': False}
    (OUT / 'DELIVERY.json').write_bytes(core.dump(delivery))
    print(json.dumps(delivery, ensure_ascii=False))


if __name__ == '__main__':
    main()
