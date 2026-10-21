"""Installed-code check with synthetic filenames only; no RAW/model/network access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def main(root):
    root = Path(root).resolve(strict=True)
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline import document_representations as reps
    assert Path(reps.__file__).resolve() == root / '02_BACKEND/lawrag/pipeline/document_representations.py'
    def row(name, body):
        h = hashlib.sha256(body.encode()).hexdigest()
        return {'path': '/synthetic/' + name, 'relative': name, 'name': name, 'source': 'internal',
                'document_id': h[:16], 'sha256': h, 'doc_type': None, 'engine': ''}
    old = row('규정(20190710).docx', 'old')
    new = row('규정(20220331).docx', 'new')
    selected, excluded = reps.select_latest_internal([old, new])
    assert len(selected) == len(excluded) == 1 and selected[0]['sha256'] == new['sha256']
    assert selected[0]['filename_version']['date'] == '20220331'
    try:
        reps.select_latest_internal([new, row('규정(20220331)(2).docx', 'different')])
    except ValueError as exc:
        assert 'Conflicting latest' in str(exc)
    else:
        raise AssertionError('ambiguous newest revision accepted')
    p = root / '06_TOOLS/COMMANDS/composed_build.py'
    spec = importlib.util.spec_from_file_location('latest_composed', p)
    cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
    calls = []
    assert cli.run(['--run-id', 'synthetic-latest', '--latest-internal-versions', '--no-models', '--check-only'],
                   call=lambda cmd: calls.append(cmd) or 0) == 0
    assert '--latest-internal-versions' in calls[0]
    print(json.dumps({'status': 'INSTALLED_CODE_PASS', 'root': str(root),
                      'python': sys.executable, 'version': sys.version,
                      'policy': reps.LATEST_INTERNAL_POLICY, 'model_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1])
