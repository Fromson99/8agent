#!/usr/bin/env python3
"""Build the PDF input patch against the three onsite hashes observed 2026-09-15."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-four-stage-20260910.zip'
BASE_HASH = 'bd2a2ffe005776c29e720c1fa712d8cceea8c4b7177979cf8aa213f390cdadce'
NAME = 'genos-internal-pdf-input-20260915-v2'
PINS = {
    '02_BACKEND/lawrag/pipeline/genos_corpus.py': '41de9358cca5d650a6f2f2619a9fef1acd92a5fc4bd7042f637c40db7cd8d12e',
    '06_TOOLS/COMMANDS/genos_data_stages.py': '7b0b9fe9573b09e5b58a8e19f149d1b67d967156de37f3c0f495954c0bedf06d',
    '02_BACKEND/lawrag/pipeline/genos_build.py': 'cfa42e40ebbe114ee5ab3533ebfd71f0ea00ca5bcd54d643863e7b3e258caacb',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def change(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


def patched(name, s):
    if name.endswith('genos_corpus.py'):
        replacements = [
            ('exclude_internal=False):', 'exclude_internal=False,\n            internal_pdf_root=None):'),
            ('corpus = corpus.resolve(strict=True)', 'corpus = corpus.resolve(strict=internal_pdf_root is None)\n    if corpus.exists() and not corpus.is_dir():\n        raise ValueError("corpus root must be a directory")'),
            ('    attempted = set()', "    internal_root = (Path(internal_pdf_root).expanduser().absolute()\n                     if internal_pdf_root is not None else corpus / 'internal')\n    if internal_pdf_root is not None:\n        report['input_roots'] = {'external': str(corpus),\n                                 'internal': None if exclude_internal else str(internal_root)}\n    attempted = set()"),
            ('for folder in sorted(corpus.iterdir()):', 'for folder in sorted(corpus.iterdir()) if corpus.is_dir() else []:'),
            ("elif skip_invalid:\n            root = corpus / 'internal'\n            if not root.is_dir() or root.is_symlink():", "elif skip_invalid or internal_pdf_root is not None:\n            root = internal_root\n            if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():"),
            ("                if path.suffix.lower() not in builder.EXTENSIONS", "                if internal_pdf_root is not None and path.suffix.lower() != '.pdf' and not path.is_symlink():\n                    report['excluded'].append({'source': 'internal', 'path': str(path), 'reason': 'non_pdf_internal'})\n                    continue\n                if path.suffix.lower() not in builder.EXTENSIONS"),
            ("                    one = builder.inventory(root, 'internal'", "                    if internal_pdf_root is not None and not path.is_symlink() and not path.stat().st_size:\n                        raise ValueError('empty internal PDF')\n                    one = builder.inventory(root, 'internal'"),
            ("builder.inventory(corpus / 'internal', 'internal'", "builder.inventory(internal_root, 'internal'"),
            ("            row['kind'] = 'internal'", "            row['kind'] = 'internal'\n            if internal_pdf_root is not None:\n                row['input_collection'] = 'PDF/internal'"),
            ("    for source in SOURCES:\n        manifest =", "    for source in SOURCES:\n        folder = corpus / source\n        if internal_pdf_root is not None and not folder.exists() and not folder.is_symlink():\n            continue  # Explicit PDF input also supports installations with no external RAW.\n        manifest ="),
            ("    return plan, report", "    if internal_pdf_root is not None:\n        plan['input_roots'] = dict(report['input_roots'])\n    return plan, report"),
        ]
    elif name.endswith('genos_data_stages.py'):
        replacements = [
            ("    if not raw.is_dir():\n        p.error('원문 폴더 없음: ' + str(raw) + '. 먼저 genos_move_raw.py로 이전하세요.')\n", ''),
            ('exclude_internal=args.exclude_internal, skip_invalid=True, emit=progress.emit)', "exclude_internal=args.exclude_internal, skip_invalid=True, emit=progress.emit,\n                    internal_pdf_root=data / 'PDF/internal')"),
            ("result = {'stage': 'raw', 'status': 'INPUT_CHECK_ONLY'", "result = {'ok': inventory['ok'], 'stage': 'raw', 'status': 'INPUT_CHECK_ONLY'"),
        ]
    else:
        replacements = [("'aliases', 'source_metadata', 'conversion'):", "'aliases', 'source_metadata', 'conversion', 'input_collection'):")]
    for old, new in replacements:
        s = change(s, old, new)
    ast.parse(s, feature_version=(3, 11))
    return s


def build():
    assert digest(BASE.read_bytes()) == BASE_HASH
    output = BASE.parent / NAME
    output.mkdir(exist_ok=False)
    manifest = {'schema': 1, 'baseline_archive': BASE.name, 'baseline_archive_sha256': BASE_HASH,
                'scope': 'Existing GENOS structure pipeline; internal PDF input only. Not a full engine upgrade.',
                'files': {}}
    diff = []
    with zipfile.ZipFile(BASE) as archive:
        for name, expected in PINS.items():
            original = archive.read(name)
            assert digest(original) == expected
            modified = patched(name, original.decode()).encode()
            path = output / 'payload' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(modified)
            manifest['files'][name] = {'before_sha256': expected, 'after_sha256': digest(modified)}
            diff.extend(difflib.unified_diff(original.decode().splitlines(True), modified.decode().splitlines(True),
                                            fromfile='a/' + name, tofile='b/' + name))
    (output / 'PATCH.diff').write_text(''.join(diff))
    (output / 'PATCH_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'install.py').write_bytes(Path(__file__).with_name('genos_input_patch_install.py').read_bytes())
    (output / 'README_KO.md').write_bytes(Path(__file__).with_name('GENOS_INTERNAL_PDF_COMPAT.md').read_bytes())
    target = output.with_suffix('.zip')
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                archive.write(path, str(path.relative_to(output.parent)))
    print(json.dumps({'zip': str(target), 'sha256': digest(target.read_bytes()), 'bytes': target.stat().st_size}))


if __name__ == '__main__':
    build()
