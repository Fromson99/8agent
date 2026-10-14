"""Editor-only correction: preserve native cards and remove status answer tokens."""
import ast
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PRIOR = OUT.with_name('rag_progress_graph_20261008_r5')
NAME = 'GENOS_WORKFLOW_LIVE_CARDS_20261008_R4'
SOURCE = '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encode = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    assert not (OUT / (NAME + '_EDITOR.zip')).exists(), 'Create a new revision after sealing'
    old = (PRIOR / 'payload' / SOURCE).read_bytes()
    prior_paste = (PRIOR / 'GENOS_RAG_PROGRESS_GRAPH_20261008_R5_WORKFLOW_PASTE_ALL.txt').read_bytes()
    prior_hand = json.loads((PRIOR / 'HANDOFF.json').read_bytes())
    assert sha(prior_paste) == prior_hand['workflow_txt_sha256']
    assert prior_paste.endswith(old)
    source = (ROOT / SOURCE).read_bytes()
    paste = prior_paste[:-len(old)] + source
    ast.parse(paste, feature_version=(3, 10))
    members = {
        NAME + '_PASTE_ALL.txt': paste,
        'genos_rag_chat.py': source,
        'GUIDE_UTF8.txt': (OUT / 'GUIDE_UTF8.txt').read_bytes(),
        'VALIDATION_SUMMARY.txt': (OUT / 'VALIDATION_SUMMARY.txt').read_bytes(),
        'VALIDATION.json': (OUT / 'VALIDATION.json').read_bytes(),
    }
    verify = '''#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
mkdir -p logs
TASK_LOG="logs/verify-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$TASK_LOG") 2>&1
trap 'TASK_STATUS=$?; echo "EXIT=$TASK_STATUS LOG=$TASK_LOG"; exit "$TASK_STATUS"' EXIT
sha256sum -c PACKAGE_SHA256SUMS.txt
python3 - <<'VERIFY_PY'
import ast
from pathlib import Path
ast.parse(Path(''' + repr(NAME + '_PASTE_ALL.txt') + ''').read_text(encoding='utf-8'), feature_version=(3, 10))
print('EDITOR_FILES_VERIFIED; paste the complete PASTE_ALL.txt into the existing workflow Python editor')
VERIFY_PY
'''
    members['VERIFY_EDITOR_FILES.txt'] = verify.encode()
    manifest = {'version': NAME, 'purpose': 'existing-workflow-python-editor-only',
        'files': {n: sha(v) for n, v in members.items()},
        'workflow_revision': 'rag-v6-live-cards-20261008-r4',
        'live_progress_revision': 'workflow-live-cards-20261008-r4',
        'svg_revision': prior_hand['display_revision'],
        'current_judgment_revision': prior_hand['progress_revision'],
        'source_path': SOURCE, 'source_sha256': sha(source),
        'r5_paste_sha256': sha(prior_paste), 'r5_backend_zip_sha256': prior_hand['code_zip_sha256'],
        'known_good_reference': 'workflow_live_progress_20261007_r1/WORKFLOW_PASTE_ALL.txt',
        'supersedes_editor_delivery': 'workflow_live_progress_20261008_r3',
        'native_panel_preserved': True, 'preparation_answer_token': False,
        'preparation_status_channel': 'agentFlowExecutedData',
        'body_tokens': 'verified final answer only',
        'socketio_inline_alias': 'socketio',
        'model_calls': 0, 'backend_modified_by_delivery': False,
        'data_generation_modified_by_delivery': False,
        'field_workflow_pasted': False, 'field_workflow_test': 'NOT_RUN'}
    members['MANIFEST.json'] = encode(manifest)
    members['PACKAGE_SHA256SUMS.txt'] = ''.join(sha(raw) + '  ' + name + '\n'
        for name, raw in sorted(members.items())).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in members.items():
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            info = zipfile.ZipInfo(name, (2026, 10, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    archive = buffer.getvalue()
    zip_sha = sha(archive)
    check_members = {name: sha(raw) for name, raw in members.items()}
    prepare_python = '''import base64,hashlib,io,json,os,sys,zipfile
from pathlib import Path
raw=base64.b64decode(''' + repr(base64.b64encode(archive).decode()) + ''')
assert hashlib.sha256(raw).hexdigest()==''' + repr(zip_sha) + '''
expected=''' + repr(check_members) + '''
root=Path(sys.argv[1])
if root.is_symlink():raise SystemExit('Existing editor output symlink preserved; choose a separate output')
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 assert set(z.namelist())==set(expected)
 assert z.testzip() is None
 payload={name:z.read(name) for name in expected}
 for name,blob in payload.items():
  assert hashlib.sha256(blob).hexdigest()==expected[name]
  target=root/name
  if target.is_symlink():raise SystemExit('Existing symlink preserved: '+str(target))
  if target.exists() and target.read_bytes()!=blob:raise SystemExit('Existing different editor file preserved: '+str(target))
 root.mkdir(parents=True,exist_ok=True)
 for name,blob in payload.items():
  target=root/name
  if not target.exists():
   temp=root/(name+'.writing')
   with temp.open('xb') as f:f.write(blob)
   temp.replace(target)
 for name,pin in expected.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==pin
print(json.dumps({'status':'EDITOR_FILES_READY','output':str(root.resolve()),
 'paste_file':str((root/''' + repr(NAME + '_PASTE_ALL.txt') + ''').resolve()),
 'zip_sha256':''' + repr(zip_sha) + ''',
 'workflow_saved':False,'backend_modified':False,'generation_modified':False},ensure_ascii=False))
'''
    prepare = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
TASK_TRANSFER="${GENOS_DEV_ROOT:-${HOME}/DEV}/TRANSFER"
TASK_LOG_DIR="$TASK_TRANSFER/workflow-live-cards-r4-logs"
if ! mkdir -p "$TASK_LOG_DIR"; then
    TASK_LOG_DIR="${TMPDIR:-/tmp}/8-agent-workflow-live-cards-r4-$(id -u)"
    mkdir -p "$TASK_LOG_DIR"
fi
TASK_LOG="$TASK_LOG_DIR/prepare-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$TASK_LOG") 2>&1
trap 'TASK_STATUS=$?; echo "EXIT=$TASK_STATUS LOG=$TASK_LOG"; exit "$TASK_STATUS"' EXIT
echo "Preparing verified editor files only; preserve the existing SSE backend and data"
python3 - "$TASK_TRANSFER/workflow-live-cards-r4-editor" <<'EDITOR_PREPARE_PY'
''' + prepare_python + '''EDITOR_PREPARE_PY
bash "$TASK_TRANSFER/workflow-live-cards-r4-editor/VERIFY_EDITOR_FILES.txt"
'''
    ast.parse(prepare_python, feature_version=(3, 10))
    for name, raw in members.items():
        (OUT / name).write_bytes(raw)
    (OUT / (NAME + '_EDITOR.zip')).write_bytes(archive)
    (OUT / (NAME + '_PREPARE.txt')).write_text(prepare)
    subprocess.run(['bash', '-n', str(OUT / (NAME + '_PREPARE.txt')),
        str(OUT / 'VERIFY_EDITOR_FILES.txt')], check=True)
    outer_names = [NAME + '_EDITOR.zip', NAME + '_PREPARE.txt', NAME + '_PASTE_ALL.txt',
        'GUIDE_UTF8.txt', 'VALIDATION_SUMMARY.txt']
    (OUT / 'SHA256SUMS.txt').write_text(''.join(sha((OUT / name).read_bytes()) + '  ' + name + '\n'
        for name in outer_names))
    manifest.update({'created_at': datetime.now(timezone.utc).isoformat(),
        'editor_zip_sha256': zip_sha, 'editor_zip_bytes': len(archive),
        'prepare_txt_sha256': sha(prepare.encode()), 'paste_txt_sha256': sha(paste),
        'local_active_pointer_sha256': sha((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()),
        'local_active_pointer_changed': False, 'field_git_commit': None,
        'field_code_serving_revision': None, 'field_generation': None,
        'field_generation_manifest_sha256': None, 'email_status': 'NOT_SENT'})
    (OUT / 'HANDOFF.json').write_bytes(encode(manifest))
    print(json.dumps({'editor_zip_bytes': len(archive), 'paste_bytes': len(paste),
        'prepare_bytes': len(prepare.encode()), 'editor_zip_sha256': zip_sha}))


if __name__ == '__main__':
    main()
