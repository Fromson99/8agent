import importlib.util
import json
from pathlib import Path

import pytest
from lawrag.pipeline.genos_raw_move import move
from .test_genos_build import XML

SCRIPT = Path(__file__).resolve().parents[3] / '06_TOOLS/COMMANDS/genos_recover_raw_nfs.py'
spec = importlib.util.spec_from_file_location('nfs_recovery', SCRIPT)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path
    (root / '00_SYSTEM').mkdir()
    (root / '00_SYSTEM/WORKSPACE.json').write_text(json.dumps({'roots': [{'id':'data','canonical_path':'01_DATA'}]}))
    source = root / 'data/corpus'
    (source / 'internal/팀').mkdir(parents=True)
    (source / 'internal/팀/원본.xml').write_text(XML)
    (source / 'law').mkdir()
    (source / 'law/manifest.json').write_text(json.dumps({'items':[{'body_file':str(source / 'internal/팀/원본.xml')}]}))
    def unsupported(*a): raise OSError(22, 'Invalid argument')
    monkeypatch.setattr('lawrag.pipeline.genos_raw_move.rename_no_replace', unsupported)
    with pytest.raises(OSError): move(source, root/'01_DATA', apply=True)
    return root


def read(root):
    return json.loads((root/'01_DATA/LOGS/raw-migration/receipt.json').read_text())


def test_prepared_nfs_copy_and_repeat(prepared):
    root = prepared
    before = recovery.scan(root/'data/corpus')
    assert recovery.recover(root)['status'] == 'PREVIEW_ONLY'
    assert not (root/'01_DATA/RAW').exists()
    result = recovery.recover(root, apply=True)
    assert result['status'] == 'COPIED_VERIFIED'
    assert before == recovery.scan(root/'data/corpus')
    assert read(root)['status']=='COMPLETED' and read(root)['source_retained']
    assert not (root/'01_DATA/RAW/.migration-in-progress').exists()
    assert json.loads((root/'01_DATA/RAW/law/manifest.json').read_text())['items'][0]['body_file']=='internal/팀/원본.xml'
    assert recovery.recover(root, apply=True)['status'] == 'ALREADY_COPIED'


def test_interrupted_partial_file_resumes_without_truncation(prepared, monkeypatch):
    real = recovery.copy_stream
    def interrupted(stream, dest, **kwargs):
        with dest.open('xb') as f: f.write(stream.read(11))
        raise KeyboardInterrupt
    monkeypatch.setattr(recovery, 'copy_stream', interrupted)
    with pytest.raises(KeyboardInterrupt): recovery.recover(prepared, apply=True)
    assert read(prepared)['status'] == 'COPYING'
    assert (prepared/'01_DATA/RAW/.migration-in-progress').exists()
    monkeypatch.setattr(recovery, 'copy_stream', real)
    assert recovery.recover(prepared, apply=True)['status'] == 'COPIED_VERIFIED'


@pytest.mark.parametrize('problem',['existing','source','recipe','escape','symlink'])
def test_refuses_unsafe_inputs(prepared, problem):
    root=prepared; record=root/'01_DATA/LOGS/raw-migration/receipt.json'
    if problem=='existing': (root/'01_DATA/RAW').mkdir()
    elif problem=='source': (root/'data/corpus/new.xml').write_text(XML)
    elif problem=='symlink': (root/'data/corpus/link').symlink_to(root/'00_SYSTEM')
    else:
        d=read(root)
        if problem=='recipe':d['manifests']['law/manifest.json']={'bad':'data'}
        else:d['before']['../escape']={'sha256':'0'*64,'bytes':0}
        record.write_text(json.dumps(d))
    with pytest.raises(ValueError): recovery.recover(root, apply=True)
    assert read(root)['status']=='PREPARED'


def test_destination_tamper_refused(prepared):
    recovery.recover(prepared, apply=True)
    (prepared/'01_DATA/RAW/internal/팀/원본.xml').write_text('user change')
    with pytest.raises(ValueError):recovery.recover(prepared, apply=True)


def test_completion_marker_cleanup_recovery(prepared, monkeypatch):
    real=Path.unlink
    def interrupt(p,*a,**kw):
        if p.name=='.migration-in-progress':raise KeyboardInterrupt
        return real(p,*a,**kw)
    monkeypatch.setattr(Path,'unlink',interrupt)
    with pytest.raises(KeyboardInterrupt):recovery.recover(prepared,apply=True)
    assert read(prepared)['status']=='COMPLETED'
    monkeypatch.setattr(Path,'unlink',real)
    assert recovery.recover(prepared,apply=True)['status']=='ALREADY_COPIED'
    assert not (prepared/'01_DATA/RAW/.migration-in-progress').exists()


def test_lock_refuses_concurrent_job(prepared):
    import fcntl
    with (prepared/'01_DATA/.raw-migration.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert recovery.main(['--root',str(prepared),'--apply'])==1
    assert read(prepared)['status']=='PREPARED'


def test_delivered_shell_exact_code_and_execution(prepared):
    import subprocess
    shell=SCRIPT.parents[2]/'09_ARTIFACTS/HANDOFF/GENOS/genos_recover_raw_nfs.sh.txt'
    assert SCRIPT.read_text() in shell.read_text()
    r=subprocess.run(['bash',str(shell),'--root',str(prepared),'--apply'],capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
    assert 'COPIED_VERIFIED' in r.stdout
    assert read(prepared)['status']=='COMPLETED'


def test_changed_source_during_copy_keeps_gate(prepared,monkeypatch):
    real=recovery.copy_stream
    def changed(*a,**kw):
        real(*a,**kw)
        (prepared/'data/corpus/new.xml').write_text(XML)
    monkeypatch.setattr(recovery,'copy_stream',changed)
    with pytest.raises(ValueError,match='최종 해시'):
        recovery.recover(prepared,apply=True)
    assert read(prepared)['status']=='COPYING'
    assert (prepared/'01_DATA/RAW/.migration-in-progress').exists()


def test_corrupt_partial_never_overwritten(prepared,monkeypatch):
    def interrupted(stream,dest,**kwargs):
        dest.write_bytes(b'not original')
        raise KeyboardInterrupt
    real=recovery.copy_stream
    monkeypatch.setattr(recovery,'copy_stream',interrupted)
    with pytest.raises(KeyboardInterrupt):recovery.recover(prepared,apply=True)
    monkeypatch.setattr(recovery,'copy_stream',real)
    with pytest.raises(ValueError,match='원본과 다름'):
        recovery.recover(prepared,apply=True)
