"""Verify the shipped inventory and, optionally, every installed code file."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--include-evidence', action='store_true')
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    print('PYTHON', sys.executable, sys.version.replace('\n', ' '), flush=True)
    if sys.version_info < (3, 11):
        raise ValueError('Python 3.11+ required')
    delivery = json.loads((bundle / 'DELIVERY.json').read_text())
    archive = bundle / 'code.zip'
    assert sha(archive) == delivery['code_zip_sha256'], 'code.zip hash mismatch'
    assert sha(bundle / 'CODE_MANIFEST.json') == delivery['code_manifest_sha256'], 'manifest hash mismatch'
    manifest = json.loads((bundle / 'CODE_MANIFEST.json').read_text())
    assert manifest['format'] == '8agent-code/1'
    expected = {r['path']: r for r in manifest['files']}
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist()) == len(set(z.namelist())), 'duplicate archive entries'
        assert set(z.namelist()) == set(expected) | {'CODE_MANIFEST.json'}, 'inventory mismatch'
        assert z.read('CODE_MANIFEST.json') == (bundle / 'CODE_MANIFEST.json').read_bytes()
        for name, row in expected.items():
            path = Path(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
            raw = z.read(name)
            assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], name
            if args.root:
                target = args.root / name
                assert not target.is_symlink() and target.is_file() and sha(target) == row['sha256'], name
        workflow = z.read('08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
        assert workflow == (bundle / 'WORKFLOW.py').read_bytes() == (bundle / 'WORKFLOW_PASTE_ALL.txt').read_bytes()
        assert z.read('06_TOOLS/OFFLINE/genos_code_replace.py') == (bundle / 'apply.py').read_bytes()
    if args.include_evidence:
        record = json.loads((bundle / 'EVIDENCE_RECEIPT.json').read_text())
        assert sha(bundle / 'evidence.zip') == record['sha256'], 'historical evidence hash mismatch'
    print('PASS', json.dumps({'code_files': len(expected), 'code_zip_sha256': delivery['code_zip_sha256'],
                              'installed_root': str(args.root) if args.root else None,
                              'activation_performed': False}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
