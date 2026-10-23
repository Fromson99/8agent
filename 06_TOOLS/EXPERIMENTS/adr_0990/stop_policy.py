"""Experiment-level sticky stop; process exit zero cannot hide provider failure."""
from common import read, save

class RunStopped(RuntimeError):
    pass

class StopPolicy:
    def __init__(self, path, max_calls=8):
        self.path, self.max_calls = path, max_calls

    def before_call(self, calls):
        if self.path.exists():
            raise RunStopped('experiment already stopped: ' + read(self.path)['reason'])
        if calls >= self.max_calls:
            self.stop('CALL_BUDGET', calls)
            raise RunStopped('physical model call budget exhausted')

    def stop(self, reason, calls, status_code=None):
        if not self.path.exists():
            save(self.path, dict(reason=reason, calls=calls, status_code=status_code))

def terminal_failure(result, stop=None, exit_code=0):
    if stop:
        return stop['reason']
    if exit_code:
        return 'PROCESS_FAILURE'
    if result.get('error'):
        return 'RECORDED_FAILURE'
    if result.get('service_status') != 200:
        return 'SERVICE_FAILURE'
    return None
