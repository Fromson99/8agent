"""Bound total physical-call time, including a peer sending keepalive bytes."""
from contextlib import contextmanager
import signal

@contextmanager
def physical_deadline(seconds,on_timeout):
    previous=signal.getsignal(signal.SIGALRM)
    assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)
    def expired(*_):
        on_timeout()
        raise TimeoutError('physical_call_wall_deadline')
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,max(.001,seconds))
    try:yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)
