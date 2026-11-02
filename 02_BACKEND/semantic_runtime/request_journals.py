"""Read-only discovery of a request journal and its registered workflow children."""
import json
from .oracle_runtime_paths import Path
import re
from . import runtime_sqlite as sqlite3

from .contracts import digest


def paths(runtime, run_id):
    if not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{32}', run_id):
        return []
    runtime = Path(runtime)
    found = list((runtime/'legal-agent'/'runs').glob(f'*/{run_id}/journal.sqlite'))
    workflow = runtime/'workflows'/run_id/'journal.sqlite'
    if workflow.is_file():
        found.append(workflow)
    return found


def scope(db, run_id):
    row = db.execute('SELECT run_id,binding_json,binding_hash FROM run WHERE singleton=1').fetchone()
    if not row or row[0] != run_id:
        return None
    binding = json.loads(row[1])
    if not isinstance(binding, dict) or digest(binding) != row[2]:
        return None
    native_scope = binding.get('scope') or {}
    if not isinstance(native_scope, dict):
        return None
    documents = native_scope.get('document_version_ids')
    if documents is None and 'workflow' in binding:
        saved = db.execute('SELECT request_json,request_hash,binding_hash FROM workflow_state WHERE singleton=1').fetchone()
        if not saved or saved[2] != row[2]:
            return None
        request = json.loads(saved[0])
        if not isinstance(request, dict) or digest(request) != saved[1] or saved[1] != binding.get('request'):
            return None
        documents = binding.get('document_ids')
        if documents != request.get('document_ids') or binding.get('principal') != request.get('principal'):
            return None
    if not isinstance(documents, list) or any(not isinstance(d, str) for d in documents):
        return None
    return frozenset(documents), row[2]


def children(parent, run_id):
    """Follow recorded children only, with path, identity, hash and scope checks.

    An invalid/incomplete registration is omitted from diagnostics and display;
    the workflow's own integrity checks still own execution and failure state.
    """
    parent = Path(parent).resolve()
    result = []
    with sqlite3.connect(parent.as_uri()+'?mode=ro', uri=True, timeout=.2) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_child_run'").fetchone():
            return result
        admitted = scope(db, run_id)
        if admitted is None:
            return result
        for call_id, ident, raw_path, binding_hash, raw_input in db.execute(
                'SELECT c.call_id,c.run_id,c.journal,c.binding_hash,w.input_json '
                'FROM workflow_child_run c JOIN workflow_call w USING(call_id) WHERE w.kind=\'rag\' ORDER BY c.rowid'):
            try:
                side = json.loads(raw_input)['side']
                if side not in ('internal', 'external') or not re.fullmatch('[a-f0-9]{32}', ident):
                    continue
                path = Path(raw_path).resolve()
                # Resolving a symlink below children must not enlarge the root.
                root = parent.parent.resolve()/'children'/side
                if not path.is_relative_to(root) or path.name != 'journal.sqlite' or not path.is_file():
                    continue
                with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=.2) as child:
                    child_scope = scope(child, ident)
                if child_scope is None or child_scope[1] != binding_hash or not child_scope[0] <= admitted[0]:
                    continue
                result.append({'run_id': ident, 'path': path, 'side': side, 'call_id': call_id})
            except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
                continue
    return result
