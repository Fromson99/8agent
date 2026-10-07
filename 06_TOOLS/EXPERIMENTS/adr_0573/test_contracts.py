"""Hard nightly worker timing and no late adoption."""
import multiprocessing
from pathlib import Path
import time
import pytest
from harness import candidate,R

@pytest.fixture(scope='module')
def modules():
    with candidate(snapshot=True): yield

def test_hung_worker_is_terminated_before_late_write(modules,tmp_path):
    from lawrag.pipeline.action_memory import bounded_generate
    class Hung:
        def generate(self,*args): time.sleep(1);(tmp_path/'late.txt').write_text('late');return {}
    before={p.pid for p in multiprocessing.active_children()};start=time.monotonic()
    with pytest.raises(TimeoutError): bounded_generate(Hung(),[],[],.1,tmp_path)
    assert time.monotonic()-start<.9
    time.sleep(1.05)
    assert not (tmp_path/'late.txt').exists()
    assert {p.pid for p in multiprocessing.active_children()}==before

def test_worker_result_and_error_are_received(modules,tmp_path):
    from lawrag.pipeline.action_memory import bounded_generate
    class Good:
        def generate(self,*args): return {'assignments':[],'exclusion_candidates':[]}
    class Bad:
        def generate(self,*args): raise ValueError('private details never copied')
    assert bounded_generate(Good(),[],[],1,tmp_path)=={'assignments':[],'exclusion_candidates':[]}
    with pytest.raises(RuntimeError,match='ValueError'):bounded_generate(Bad(),[],[],1,tmp_path)

def test_outside_window_zero_worker_and_lock_still_available(modules,tmp_path):
    from lawrag.pipeline.action_memory import build
    from datetime import datetime
    class NoModel:
        def eligible(self,e):raise AssertionError('outside')
    value=build(R,runtime=tmp_path,model=NoModel(),at=datetime.fromisoformat('2026-09-29T21:00:00+00:00'))
    assert value['state']=='OUTSIDE_WINDOW'
    assert not (tmp_path/'action-memory/memory.sqlite').exists()
