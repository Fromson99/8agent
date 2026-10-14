"""Launch only the explicitly verified research revision; never select MAIN."""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import traceback


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load():
    sys.dont_write_bytecode = True
    # Run from repository root; path discovery belongs to workspace bootstrap.
    sys.path.insert(0, str(Path.cwd() / '02_BACKEND'))
    from lawrag.platform.workspace import load_layout
    workspace = load_layout()
    candidate = workspace.path('backend') / 'lawrag/research/candidates/adr_0713/lab'
    binding_path = workspace.path('experiments') / 'ADR/ADR-0713-legal-knowledge-lab-deduction/artifacts/design/launch-binding.json'
    binding = json.loads(binding_path.read_text())
    manifest_path = candidate / 'candidate.json'
    if sha(manifest_path) != binding['manifest_sha256']:
        raise ValueError('Candidate manifest changed; launch binding must be reviewed again')
    manifest = json.loads(manifest_path.read_text())
    revision = next(r for r in manifest['revisions'] if r['revision_id'] == binding['revision_id'])
    if revision['revision_sha256'] != binding['revision_sha256'] or manifest['production_loadable']:
        raise ValueError('Candidate revision is not bound')
    for f in revision['files']:
        if sha(workspace.root / f['frozen_path']) != f['snapshot_sha256']:
            raise ValueError('Frozen file changed: ' + f['target_path'])
    baseline_path = binding_path.parent / 'baseline.json'
    if sha(baseline_path) != binding['baseline_sha256']:
        raise ValueError('Baseline binding changed')
    baseline = json.loads(baseline_path.read_text())
    release = baseline['release']
    if sha(workspace.root / baseline['pointer']['manifest_path']) != baseline['pointer']['release_manifest_sha256']:
        raise ValueError('Pinned release manifest changed')
    code = workspace.root / release['code_root']
    for name, expected in release['files'].items():
        if sha(code / name) != expected:
            raise ValueError('Pinned RAG code changed: ' + name)
    if sha(workspace.root / release['data_path'] / 'manifest.json') != release['data_manifest_sha256']:
        raise ValueError('Pinned data manifest changed')
    snapshot = candidate / 'revisions' / revision['revision_id'] / 'snapshot'
    sys.path.insert(0, str(snapshot / '02_BACKEND'))
    return workspace, baseline, snapshot


def main():
    parser = argparse.ArgumentParser(description='Independent legal knowledge laboratory')
    parser.add_argument('--port', type=int, default=5581)
    parser.add_argument('--qa-worker')
    args = parser.parse_args()
    workspace, baseline, snapshot = load()
    runtime = workspace.path('runtime') / 'knowledge-lab' / 'adr-0713'
    if args.qa_worker:
        ident = args.qa_worker
        if len(ident) != 32 or not all(c in '0123456789abcdef' for c in ident):
            raise ValueError('Invalid question ID')
        output = runtime / 'questions' / ident
        from knowledge_lab.qa import run
        try:
            run(workspace.root, baseline, output, json.loads((output / 'input.json').read_text()),
                snapshot / '02_BACKEND/lawrag/research/experiment_client.py')
        except Exception as exc:
            # Trace is local only; credentials never enter the public result.
            (output / 'error.txt').write_text(traceback.format_exc())
            (output / 'result.json').write_text(json.dumps({'status': 'FAILED', 'error': '질문 실행에 실패했습니다. 연구실의 오류 기록을 확인하세요.', 'error_type': type(exc).__name__}, ensure_ascii=False))
        return
    import uvicorn
    from knowledge_lab.app import create_app
    app = create_app(workspace, baseline, runtime, Path(__file__).resolve())
    print(f'Knowledge Lab: http://127.0.0.1:{args.port} (MAIN unchanged)', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
