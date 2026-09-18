from pathlib import Path
import pytest
from lawrag.pipeline.genos_internal_replace import replace, rollback


def setup(tmp_path):
    (tmp_path/'RAW/internal/old').mkdir(parents=True)
    (tmp_path/'RAW/internal/old/document.hwp').write_bytes(b'old')
    (tmp_path/'RAW/internal/archive.zip').write_bytes(b'zip')
    (tmp_path/'PDF/internal/rules').mkdir(parents=True)
    (tmp_path/'PDF/internal/rules/a.pdf').write_bytes(b'%PDF-1.7 mock')
    (tmp_path/'PDF/internal/source.zip').write_bytes(b'zip')
    return tmp_path


def test_replace_preserves_folders_backup_and_rollback(tmp_path):
    data=setup(tmp_path)
    assert replace(data)['pdf_count']==1
    assert (data/'RAW/internal/old/document.hwp').exists()
    result=replace(data,apply=True)
    assert [str(p.relative_to(data/'RAW/internal')) for p in (data/'RAW/internal').rglob('*') if p.is_file()]==['rules/a.pdf']
    assert not (data/'PDF').exists()
    backup=Path(result['backup'])
    assert (backup/'old-internal/old/document.hwp').read_bytes()==b'old'
    rollback(backup)
    assert (data/'PDF/internal/rules/a.pdf').exists()
    assert (data/'RAW/internal/archive.zip').exists()
    assert not (data/'RAW/.migration-in-progress').exists()


def test_empty_and_collision_do_not_replace(tmp_path):
    data=setup(tmp_path)
    (data/'PDF/rules').mkdir()
    (data/'PDF/rules/a.pdf').write_bytes(b'%PDF-1.7 other')
    with pytest.raises(ValueError,match='Duplicate'):replace(data,apply=True)
    assert (data/'RAW/internal/old/document.hwp').exists()


def test_drift_blocks_rollback(tmp_path):
    data=setup(tmp_path);result=replace(data,apply=True)
    (data/'RAW/internal/rules/a.pdf').write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):rollback(Path(result['backup']))


def test_failure_during_swap_restores_originals(tmp_path,monkeypatch):
    data=setup(tmp_path);rename=Path.rename
    def fail(path,target):
        if path==data/'PDF':raise OSError('simulated rename failure')
        return rename(path,target)
    monkeypatch.setattr(Path,'rename',fail)
    with pytest.raises(OSError):replace(data,apply=True)
    assert (data/'RAW/internal/old/document.hwp').exists()
    assert (data/'PDF/internal/rules/a.pdf').exists()
    assert not (data/'RAW/.migration-in-progress').exists()
