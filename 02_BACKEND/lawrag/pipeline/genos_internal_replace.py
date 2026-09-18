"""Replace active internal input with PDF folders; preserve rollback copies."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import uuid

from .genos_stages import plain_path
from .genos_build import atomic


def inventory(root):
    root = plain_path(root)
    if not root.is_dir():
        raise ValueError('Missing directory: ' + str(root))
    result = {}
    for path in sorted(root.rglob('*')):
        plain_path(path)
        mode = path.stat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError('Special file: ' + str(path))
        with path.open('rb') as stream:
            result[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


def replace(data, *, apply=False):
    data = plain_path(data)
    source = data / 'PDF'
    target = plain_path(data / 'RAW/internal')
    marker = plain_path(data / 'RAW/.migration-in-progress')
    if marker.exists():
        raise ValueError('Unfinished migration: inspect RAW/.migration-in-progress')
    original = inventory(source)
    previous = inventory(target) if target.exists() else None
    selected = {}
    for name, fingerprint in original.items():
        rel = Path(name)
        if rel.suffix.lower() != '.pdf':
            continue
        # PDF/internal/... and PDF/<folder>/... converge on RAW/internal/<folder>/...
        dest = Path(*rel.parts[1:]) if rel.parts[0] == 'internal' else rel
        if dest.as_posix() in selected:
            raise ValueError('Duplicate destination PDF: ' + dest.as_posix())
        with (source / rel).open('rb') as stream:
            if b'%PDF-' not in stream.read(1024):
                raise ValueError('Invalid PDF header: ' + name)
        selected[dest.as_posix()] = {'source': name, 'sha256': fingerprint}
    if not selected:
        raise ValueError('No PDF inputs; existing internal data retained')
    result = {'pdf_count': len(selected), 'old_internal_files': len(previous or {}),
              'excluded_non_pdf': len(original)-len(selected), 'applied': False}
    if not apply:
        return result
    recovery = data / 'LOGS' / ('internal-replace-' + uuid.uuid4().hex)
    recovery.mkdir(parents=True, mode=0o700)
    stage = recovery / 'new-internal';stage.mkdir()
    receipt = {'data': str(data), 'state': 'PREPARING', 'original_pdf': original,
               'original_internal': previous, 'selected': selected}
    atomic(recovery / 'receipt.json', receipt)
    try:
        for name, row in selected.items():
            dest = stage / name;dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / row['source'], dest)
        expected = {name: row['sha256'] for name, row in selected.items()}
        if inventory(stage) != expected or inventory(source) != original:
            raise ValueError('PDF changed during migration')
        if (inventory(target) if target.exists() else None) != previous:
            raise ValueError('Internal data changed during migration')
        target.parent.mkdir(parents=True, exist_ok=True)
        receipt['state'] = 'SWAPPING';atomic(recovery / 'receipt.json', receipt)
        atomic(marker, {'recovery': str(recovery)})
        if target.exists():
            target.rename(recovery / 'old-internal')
        stage.rename(target)
        source.rename(recovery / 'original-pdf')
        receipt['state'] = 'COMPLETED';atomic(recovery / 'receipt.json', receipt)
        marker.unlink()
    except BaseException:
        # Recovery also accepts a SWAPPING receipt after process termination.
        rollback(recovery)
        raise
    return {**result, 'applied': True, 'backup': str(recovery)}


def rollback(recovery):
    recovery = plain_path(recovery)
    receipt = json.loads((recovery / 'receipt.json').read_text())
    if receipt['state'] == 'ROLLED_BACK':
        return {'rolled_back': True}
    data = plain_path(receipt['data']);target=data/'RAW/internal';source=data/'PDF'
    old=recovery/'old-internal';pdf=recovery/'original-pdf'
    expected={name: row['sha256'] for name,row in receipt['selected'].items()}
    if old.exists() and inventory(old) != receipt['original_internal']:
        raise ValueError('Backup internal drift')
    if pdf.exists() and (inventory(pdf) != receipt['original_pdf'] or source.exists()):
        raise ValueError('Backup PDF drift or PDF destination exists')
    if old.exists() or receipt['original_internal'] is None:
        if target.exists():
            if inventory(target) != expected:
                raise ValueError('Current internal changed; rollback stopped')
            target.rename(recovery/'replaced-internal')
        if old.exists():old.rename(target)
    if pdf.exists():pdf.rename(source)
    receipt['state']='ROLLED_BACK';atomic(recovery/'receipt.json',receipt)
    marker=plain_path(data/'RAW/.migration-in-progress')
    if marker.exists() and json.loads(marker.read_text()).get('recovery') == str(recovery):
        marker.unlink()
    return {'rolled_back': True, 'backup': str(recovery)}
