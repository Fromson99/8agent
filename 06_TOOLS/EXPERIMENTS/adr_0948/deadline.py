"""Thread-safe watchdog for an isolated experiment process, not product code.

The main runner already records BaseException and exits without accepting a
late response. No retry/fallback or extra model call is introduced.
"""
from contextlib import contextmanager
import os,signal,threading

@contextmanager
def physical_deadline(seconds,on_timeout):
    expired=threading.Event()
    def stop():
        expired.set()
        try:on_timeout()
        finally:os.kill(os.getpid(),signal.SIGINT)
    timer=threading.Timer(max(.001,seconds),stop);timer.daemon=True;timer.start()
    try:
        yield
        if expired.is_set():raise TimeoutError('physical_call_wall_deadline')
    finally:
        timer.cancel();timer.join()
