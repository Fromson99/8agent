"""Offline legacy DOC conversion. Originals and their identities are never rewritten."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from semantic_runtime.contracts import sha
from .genos_build import atomic


def prepare(row, directory, *, timeout=120, emit=print):
    if Path(row['path']).suffix.lower() != '.doc':
        return copy.deepcopy(row)
    original = Path(row['path'])
    if original.is_symlink() or sha(original) != row['sha256']:
        raise ValueError('DOC original changed after inventory')
    directory = Path(directory) / row['sha256']
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError('DOC conversion directory symlink is not allowed')
    directory.mkdir(parents=True, exist_ok=True)
    target, receipt = directory / 'source.docx', directory / 'conversion.json'
    if target.is_symlink() or receipt.is_symlink():
        raise ValueError('DOC conversion artifact symlink is not allowed')
    if receipt.exists():
        metadata = json.loads(receipt.read_text())
        if metadata['original_sha256'] != sha(original) or metadata['converted_sha256'] != sha(target):
            raise ValueError('DOC conversion receipt/hash mismatch; use a new run-id')
    else:
        binary = shutil.which('libreoffice') or shutil.which('soffice')
        if not binary:
            raise ValueError('DOC 변환 도구 없음: LibreOffice/soffice 필요 (pip docling 설치와 별개)')
        emit('[DOC] 원본 보존 → LibreOffice DOCX 변환: ' + row['relative'])
        # No user-controlled shell, no in-place conversion, private profile per invocation.
        with tempfile.TemporaryDirectory(prefix='doc-convert-', dir=directory) as temporary:
            work = Path(temporary)
            source = work / 'source.doc'
            shutil.copyfile(original, source)
            profile = work / 'profile'
            profile.mkdir()
            # Do not execute document macros while converting untrusted uploads.
            (profile / 'user').mkdir()
            (profile / 'user/registrymodifications.xcu').write_text(
                '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
                '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
                '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
                '</item></oor:items>')
            completed = subprocess.run([binary, '-env:UserInstallation=' + profile.as_uri(),
                '--headless', '--convert-to', 'docx:MS Word 2007 XML', '--outdir', str(work), str(source)],
                capture_output=True, timeout=timeout, check=False)
            converted = work / 'source.docx'
            if completed.returncode != 0 or not converted.is_file():
                raise ValueError(f'DOC conversion failed (exit={completed.returncode}, no valid DOCX); password/corruption/format may require manual export')
            with zipfile.ZipFile(converted) as archive:
                if 'word/document.xml' not in archive.namelist() or archive.testzip():
                    raise ValueError('DOC converter produced invalid DOCX')
            metadata = {'original_path': row['path'], 'original_relative': row['relative'],
                        'original_sha256': row['sha256'], 'original_document_id': row['document_id'],
                        'converted_sha256': sha(converted), 'converter': str(Path(binary).resolve()),
                        'converter_sha256': sha(Path(binary).resolve()),
                        'coordinate_source': 'converted_docx', 'format': 'legacy-doc-conversion-v1'}
            converted.replace(target)
            atomic(receipt, metadata)
    prepared = copy.deepcopy(row)
    # Coordinates refer to the actual parsed artifact, with explicit raw parent lineage.
    prepared.update(path=str(target), sha256=metadata['converted_sha256'],
                    document_id=metadata['converted_sha256'][:16], conversion=metadata)
    return prepared
