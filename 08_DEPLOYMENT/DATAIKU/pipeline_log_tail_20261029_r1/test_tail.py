import io
from tail_reader import LogTail, follow
import tail_reader
import pytest


class Folder:
    def __init__(self): self.files = {}; self.reads = []
    def list_paths_in_partition(self): return ['/'+n for n in self.files]
    def get_download_stream(self, path):
        self.reads.append(path.lstrip('/'))
        return io.BytesIO(self.files[path.lstrip('/')])
    def upload_stream(self,*args): raise AssertionError('Tail must never write')


def put(folder, offset, raw, prefix='current/'):
    folder.files[prefix+str(offset).zfill(16)+'.log'] = raw


def test_empty_then_new_logs_utf8_boundary_no_duplicates_or_other_attempt():
    f = Folder(); r = LogTail(f,'current/')
    put(f,0,b'old failure\n',prefix='previous/')
    assert list(r.read_new()) == []
    raw = '색인 시작\n'.encode()
    put(f,0,raw[:2])
    assert list(r.read_new()) == []
    put(f,2,raw[2:])
    assert ''.join(r.read_new()) == '색인 시작\n'
    reads = list(f.reads)
    assert list(r.read_new()) == [] and f.reads == reads
    assert not any(p.startswith('previous/') for p in f.reads)


def test_starts_latest_then_waits_for_missing_chunk():
    f = Folder(); put(f,0,b'old\n'); put(f,4,b'new\n')
    r = LogTail(f,'current/')
    assert ''.join(r.read_new()) == 'new\n'
    assert f.reads == ['current/0000000000000004.log']
    put(f,12,b'end\n')
    assert list(r.read_new()) == []
    put(f,8,b'mid\n')
    assert ''.join(r.read_new()) == 'mid\nend\n'


def test_initial_output_bounded_but_new_lines_all_follow():
    f = Folder(); raw = ''.join(f'{i}\n' for i in range(100)).encode(); put(f,0,raw)
    r = LogTail(f,'current/')
    assert ''.join(r.read_new()) == ''.join(f'{i}\n' for i in range(40,100))
    put(f,len(raw),b'next\n')
    assert ''.join(r.read_new()) == 'next\n'


def test_interrupt_stops_observer_only(monkeypatch,capsys):
    f = Folder()
    def interrupt(_): raise KeyboardInterrupt
    monkeypatch.setattr(tail_reader.time,'sleep',interrupt)
    follow(f,'current/')
    assert f.files == {} and f.reads == []
    assert '02 작업에는 취소를 보내지 않았습니다' in capsys.readouterr().out
