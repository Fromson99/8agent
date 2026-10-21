"""Bounded verification process: stop background service threads after receipts."""
import runpy,sys,os,traceback
from pathlib import Path
status=1
try:
    scope=runpy.run_path(str(Path(__file__).with_name('verify_active.py')),run_name='__main__')
    scope['app'].state.pipeline.store.close()
    print('VERIFY_PROCESS_CLEAN_EXIT')
    status=0
except BaseException:
    traceback.print_exc()
finally:
    sys.stdout.flush();sys.stderr.flush()
    os._exit(status)
