"""Lossless cold storage preserves pinned bytes, resume checks and permissions."""
from contextlib import closing
import gzip
import json
import sqlite3
import stat
import pytest
from semantic_runtime import navigation_storage as storage
from semantic_runtime.contracts import sha
from lawrag.pipeline.term_generation import build_generation
from test_navigation_storage import original_source


@pytest.fixture
def completed(tmp_path, term_glossary):
    source = original_source(tmp_path / 'source.sqlite')
    output = tmp_path / 'build'
    result = build_generation(source, term_glossary, output, serving=True,
                              storage_profile='compact-v2', fulltext_granularity='unit')
    return source, output, result, term_glossary


def test_archive_preserves_generation_manifest_bytes_sql_and_resume(completed):
    source, output, result, glossary = completed
    audit = output / 'audit/navigation'
    original = audit / 'navigation.sqlite'
    before = original.stat(); digest = sha(original)
    manifest = (audit / 'manifest.json').read_bytes()
    with closing(sqlite3.connect(original)) as db:
        counts = {t: db.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in storage.AUDIT_TABLES}
    archived = storage.archive_audit(audit)
    assert archived['saved_bytes'] > 0 and not original.exists()
    assert (audit / 'manifest.json').read_bytes() == manifest
    assert storage.verify_build(output) == result
    assert storage.archive_audit(audit) == archived
    expected = json.loads(manifest)
    with storage.audit_database(audit, expected) as restored:
        assert sha(restored) == digest
        assert stat.S_IMODE(restored.stat().st_mode) == stat.S_IMODE(before.st_mode)
        assert restored.stat().st_uid == before.st_uid
        with closing(sqlite3.connect(restored)) as db:
            assert counts == {t: db.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in storage.AUDIT_TABLES}
    assert not list(audit.parent.glob('.audit-restore-*'))
    assert build_generation(source, glossary, output, serving=True,
                            storage_profile='compact-v2', fulltext_granularity='unit') == result
    assert storage.restore_audit(audit) == original
    assert sha(original) == digest and stat.S_IMODE(original.stat().st_mode) == stat.S_IMODE(before.st_mode)
    assert storage.archive_audit(audit) == archived


def test_archive_failure_keeps_original_and_manifest(completed, monkeypatch):
    source, output, result, glossary = completed
    audit = output / 'audit/navigation'; original = audit / 'navigation.sqlite'; before = sha(original)
    def interrupted(*a, **k): raise RuntimeError('controlled archive verification failure')
    monkeypatch.setattr(storage, '_inflate', interrupted)
    with pytest.raises(RuntimeError, match='controlled'):
        storage.archive_audit(audit)
    assert sha(original) == before and not (audit / 'navigation.sqlite.gz').exists()
    assert not list(audit.glob('.archive-*'))
    assert storage.verify_build(output) == result


def test_corrupt_or_oversized_archive_fails_closed(completed):
    source, output, result, glossary = completed
    audit = output / 'audit/navigation'; storage.archive_audit(audit)
    archive = audit / 'navigation.sqlite.gz'
    expected = json.loads((audit / 'manifest.json').read_text())
    with gzip.open(archive, 'wb') as stream:
        stream.write(b'x' * (expected['audit_bytes'] + 1))
    with pytest.raises(ValueError, match='pinned size'):
        storage.verify_build(output)
    assert not (audit / 'navigation.sqlite').exists()
    assert not list(audit.parent.glob('.audit-restore-*'))
