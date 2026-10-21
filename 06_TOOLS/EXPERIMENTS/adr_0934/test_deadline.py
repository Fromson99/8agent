from pathlib import Path
import concurrent.futures,importlib.util,subprocess,sys
P=Path(__file__).with_name('deadline.py')
spec=importlib.util.spec_from_file_location('threaded_deadline',P);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_normal_worker_call_does_not_use_main_thread_signal_registration():
    def work():
        with module.physical_deadline(1,lambda:None):return 'returned'
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(work).result()=='returned'

def test_stalled_worker_interrupts_only_its_isolated_process():
    code='''import sys,threading,time,os
sys.path.insert(0,sys.argv[1])
from deadline import physical_deadline
def stalled():
 with physical_deadline(.05,lambda:None):time.sleep(5)
try:
 t=threading.Thread(target=stalled,daemon=True);t.start()
 while t.is_alive():time.sleep(.01)
except KeyboardInterrupt:os._exit(0)
os._exit(1)
'''
    p=subprocess.run([sys.executable,'-c',code,str(P.parent)],timeout=3,capture_output=True,text=True)
    assert p.returncode==0,p.stderr
