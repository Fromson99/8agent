"""Build cumulative, hash-bound search timing/reuse handoff over delivered R3."""
import ast
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent/'no_socket_chat_20261007_r3'
NAME = 'GENOS_QUERY_LATENCY_20261007_R3'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def main():
    archive_path = OUT/(NAME+'.zip')
    if archive_path.exists(): raise ValueError('Frozen ZIP exists; choose a new revision')
    prior = json.loads((PARENT/'HANDOFF.json').read_text())
    prior_zip = PARENT/(prior['version']+'.zip')
    assert sha(prior_zip.read_bytes()) == prior['code_zip_sha256']
    with zipfile.ZipFile(prior_zip) as archive:
        manifest_raw = archive.read('CODE_MANIFEST.json')
        assert sha(manifest_raw) == prior['code_manifest_sha256']
        parent = json.loads(manifest_raw)
        payload = {r['path']: archive.read(r['path']) for r in parent['files']}
    rows = {r['path']: dict(r) for r in parent['files']}
    pipeline = json.loads((ROOT/'00_SYSTEM/PIPELINE.json').read_text())
    latest = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    assert latest['generation'] == 45 and latest['release_id'] == 'session-runtime-v6-20261007-r1'
    release = json.loads((ROOT/latest['manifest_path']).read_text())
    assert sha((ROOT/latest['manifest_path']).read_bytes()) == latest['release_manifest_sha256']
    expected = {'00_SYSTEM/PIPELINE.json',
        '02_BACKEND/semantic_runtime/unit_fulltext.py',
        '02_BACKEND/semantic_runtime/term_index.py',
        '02_BACKEND/semantic_runtime/request_report.py',
        '02_BACKEND/semantic_runtime/legal_agent/law_candidates.py',
        '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py',
        '02_BACKEND/semantic_runtime/legal_agent/unit_reading.py',
        '02_BACKEND/semantic_runtime/legal_agent/memory_rag.py',
        '02_BACKEND/semantic_runtime/legal_agent/gateway.py',
        *(e['manifest'] for e in pipeline['engines'].values()), *release['files']}
    changed = []
    for path, raw in tuple(payload.items()):
        new = (ROOT/path).read_bytes()
        if new == raw: continue
        assert path in expected, 'Unexpected work drift: '+path
        changed.append(path)
        rows[path].update(sha256=sha(new), bytes=len(new),
            allowed_predecessors=sorted({sha(raw), *rows[path].get('allowed_predecessors', []), *([release['files'][path]] if path in release['files'] else [])}))
        payload[path] = new
    added = ('02_BACKEND/semantic_runtime/query_latency.py',
        '06_TOOLS/OFFLINE/genos_query_latency_summary.py',
        '07_DOCS/REFERENCE/OPERATIONS/GENOS_QUERY_LATENCY_20261007_R1.md')
    for path in added:
        raw = (ROOT/path).read_bytes()
        assert path not in payload
        payload[path] = raw
        rows[path] = {'path': path, 'sha256': sha(raw), 'bytes': len(raw),
                      'allow_missing_predecessor': True}
    for path, raw in payload.items():
        assert sha(raw) == rows[path]['sha256']
        assert Path(path).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs', '.db', '.sqlite', '.pem', '.key'}
        if path.endswith('.py'):
            ast.parse(raw, filename=path, feature_version=(3, 10) if '/workflow/' in path else (3, 11))
    pointer = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    assert pointer == latest and pointer['generation'] == 45
    candidate = dict(release['files'])
    candidate.update({p: rows[p]['sha256'] for p in (*changed, *added) if p.endswith('.py')})
    manifest = {**parent, 'id': NAME,
        'files': [rows[p] for p in sorted(rows)],
        'required_files': [*parent['required_files'], *({'path': p, 'sha256': rows[p]['sha256']} for p in added)],
        'parent_code_zip_sha256': prior['code_zip_sha256'],
        'main_basis': {**parent['main_basis'], 'pointer': pointer, 'serving_files': release['files'],
                       'code_root': release['code_root'], 'data_path': release['data_path'],
                       'data_manifest_sha256': release['data_manifest_sha256'],
                       'candidate_serving_files': candidate,
                       'local_active_pointer_changed': False},
        'scope': {'updated_files': sorted(changed), 'added_files': list(added),
                  'unchanged_parent_code_files': len(parent['files'])-len(changed)},
        'query_latency': {'revision': 'query-latency-20261007-r1', 'default_enabled': True,
                          'switch': 'GENOS_QUERY_LATENCY', 'log_level': 'INFO',
                          'metadata_cache_scope': 'one-request-sqlite-connection',
                          'max_match_cache_rows': 50000, 'overflow': 'complete-original-sql',
                          'requires_rebuilt_generation': False},
        'field_deployment_status': 'NOT_VERIFIED'}
    manifest_raw = encode(manifest)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, raw in sorted({**payload, 'CODE_MANIFEST.json': manifest_raw}.items()):
            archive.writestr(path, raw)
    zip_raw = buffer.getvalue()
    old_script = (PARENT/(prior['version']+'_APPLY.txt')).read_text()
    assert sha(old_script.encode()) == prior['apply_txt_sha256']
    script = old_script.replace(prior['version'], NAME).replace(prior['code_zip_sha256'], sha(zip_raw))
    script = script.replace('no-socket-chat-r3-logs', 'query-latency-r3-logs')
    script = script.replace('NO_SOCKET_CHAT_EXIT', 'QUERY_LATENCY_EXIT')
    script = script.replace('NO_SOCKET_CHAT_CONTRACT', 'QUERY_LATENCY_CONTRACT')
    script = script.replace('Restore workflow SSE or integrated JSON over local MAIN generation 44',
                            'Instrument and reuse law search preparation over local MAIN generation 45')
    old = "assert 'socketio' not in sys.modules\nprint('QUERY_LATENCY_CONTRACT PASS',main_router.MODE,flush=True)"
    new = "assert 'socketio' not in sys.modules\nfrom semantic_runtime.query_latency import REVISION\nfrom semantic_runtime.unit_fulltext import MATCH_CACHE_ROWS\nassert REVISION=='query-latency-20261007-r1' and MATCH_CACHE_ROWS==50000\nprint('QUERY_LATENCY_CONTRACT PASS',main_router.MODE,REVISION,flush=True)"
    assert script.count(old) == 1
    script = script.replace(old, new)
    loader = script.split("<<'LOADER_PY'\n", 1)[1].rsplit('\nLOADER_PY', 1)[0]
    ast.parse(loader, feature_version=(3, 11))
    push = (PARENT/(prior['version']+'_PUSH_NEW_REMOTE.txt')).read_text().replace(prior['version'], NAME).replace('R3', 'query-latency R3')
    summary = payload['06_TOOLS/OFFLINE/genos_query_latency_summary.py']
    workflow = payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
    # Write once after all source/inventory/grammar checks. No in-place generation edits.
    archive_path.write_bytes(zip_raw)
    (OUT/'CODE_MANIFEST.json').write_bytes(manifest_raw)
    (OUT/(NAME+'_APPLY.txt')).write_text(script)
    (OUT/(NAME+'_PUSH_NEW_REMOTE.txt')).write_text(push)
    (OUT/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_bytes(workflow)
    (OUT/(NAME+'_SUMMARIZE.txt')).write_bytes(summary)
    record = {**prior, 'version': NAME, 'created_at': datetime.now(timezone.utc).isoformat(),
        'parent_code_zip_sha256': prior['code_zip_sha256'], 'code_zip_sha256': sha(zip_raw),
        'code_zip_bytes': len(zip_raw), 'code_manifest_sha256': sha(manifest_raw),
        'code_files': len(rows), 'apply_txt_sha256': sha(script.encode()),
        'workflow_txt_sha256': sha(workflow), 'summary_txt_sha256': sha(summary),
        'main_release_manifest_sha256': latest['release_manifest_sha256'],
        'integrated_selected_release': latest['release_id'],
        'source_git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'changed_payload_files': sorted([*changed, *added]), 'selected_local_baseline': pointer,
        'local_active_pointer_changed': False, 'actual_selected_generation': None,
        'actual_generation_manifest_sha256': None, 'push_commit': None,
        'code_serving_revision': None, 'genos_deployed': False, 'field_workflow_test': 'NOT_RUN',
        'chat_binding': 'FIELD_SELECTION_NOT_VERIFIED', 'email_status': 'NOT_SENT',
        'reported_field_state': {'photos': 'RECALL_141_SECONDS_SELECT_190_SECONDS',
                                 'code_serving_hash': 'NOT_PROVIDED'},
        'validation_mode': 'synthetic-contracts-and-handoff-verification-no-model-calls',
        'external_model_calls_for_delivery': 0, 'requires_rebuilt_generation': False}
    (OUT/'HANDOFF.json').write_bytes(encode(record))
    print(json.dumps({'files': len(rows), 'changed': sorted(changed),
                      'zip_sha256': sha(zip_raw), 'zip_bytes': len(zip_raw)}))


if __name__ == '__main__': main()
