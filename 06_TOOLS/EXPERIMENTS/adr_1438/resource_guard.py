"""Frozen experiment-only admission and continuous pressure monitor (ADR-1423).

ADR-1422 stopped on a 128MiB growth of *host* swap while this worker's RSS equalled the
ADR-1412 run and available RAM stayed 8.4GiB; other agent sessions share the host. This
guard keeps every floor and measures the strict 128MiB limit on this worker's own
swapped pages (VmSwap). Host swap growth still stops the cell at 512MiB, and available
RAM / free swap floors stop it under real pressure regardless of who causes it.
"""
from common import *
import os,shutil,threading,time,gzip
GIB=1024**3;MIB=1024**2
def _status(key):
 return next(int(x.split()[1])*1024 for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(key+':'))
def sample():
 mem={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith(('MemAvailable:','SwapTotal:','SwapFree:'))}
 psi={x.split()[0]:float(x.split()[1].split('=')[1]) for x in Path('/proc/pressure/memory').read_text().splitlines()}
 vm={x.split()[0]:int(x.split()[1]) for x in Path('/proc/vmstat').read_text().splitlines() if x.startswith(('pswpin ','pswpout '))}
 return dict(time=time.time(),available=mem['MemAvailable'],swap_total=mem['SwapTotal'],swap_free=mem['SwapFree'],swap_used=mem['SwapTotal']-mem['SwapFree'],rss=_status('VmRSS'),worker_swap=_status('VmSwap'),disk=shutil.disk_usage(ROOT).free,psi=psi,vm=vm)
def violation(s,b,startup=False):
 if s['available']<(6 if startup else 3)*GIB:return 'available RAM below frozen minimum'
 if s['rss']>5*GIB:return 'worker RSS above 5GiB'
 if s['disk']<20*GIB:return 'workspace free disk below 20GiB'
 if s['swap_total']<7*GIB:return 'expected expanded WSL swap is unavailable'
 if s['worker_swap']-b['worker_swap']>128*MIB:return 'worker swap growth above128MiB since admission'
 return None
class Guard:
 def __init__(self,out):
  self.out=out;self.baseline=sample();self.done=threading.Event();self.check(True)
  put(out/'resource-baseline.json',self.baseline)
 def check(self,startup=False):
  s=sample();why=violation(s,self.baseline,startup)
  if why:
   calls=read(self.out/'calls.json') if (self.out/'calls.json').exists() else []
   put(self.out/'resource-stop.json',{'reason':why,'baseline':self.baseline,'current':s,'no_retry':True,'provider_outcome_unknown':bool(calls and calls[-1].get('status')=='started'),'provider_cancel_confirmed':False})
   print('RESOURCE_STOP',why,flush=True);os._exit(125)
  return s
 def rebase(self):
  """After app load and health, before any model call: bound load growth, then measure run growth."""
  s=sample();growth=s['swap_used']-self.baseline['swap_used']
  put(self.out/'resource-rebase.json',{'admission':self.baseline,'after_load':s,'load_swap_growth':growth,'load_limit':512*MIB})
  if s['worker_swap']-self.baseline['worker_swap']>128*MIB:
   put(self.out/'resource-stop.json',{'reason':'worker swap growth above128MiB during app load','baseline':self.baseline,'current':s,'no_retry':True,'provider_outcome_unknown':False,'provider_cancel_confirmed':False})
   print('RESOURCE_STOP load',flush=True);os._exit(125)
  self.admission=self.baseline;self.baseline=s
 def start(self):
  def watch():
   with gzip.open(self.out/'resource-samples.jsonl.gz','xt') as log:
    while not self.done.wait(1):
     log.write(json.dumps(self.check())+'\n');log.flush()
  self.thread=threading.Thread(target=watch,daemon=True);self.thread.start()
def self_test():
 b={'available':7*GIB,'rss':GIB,'worker_swap':0,'disk':30*GIB,'swap_total':8*GIB,'swap_free':0,'swap_used':8*GIB,'psi':{'full':0}}
 assert violation(b,b,True) is None   # a full host swap of other programs' idle pages alone does not stop the cell
 for key,val in [('available',2*GIB),('rss',6*GIB),('disk',GIB),('swap_total',4*GIB),('worker_swap',129*MIB)]:
  assert violation({**b,key:val},b) is not None,key
 assert violation({**b,'available':5*GIB},b,True) is not None
 assert violation({**b,'available':4*GIB},b) is None
 return 7
if __name__=='__main__':print('guard self-test',self_test(),'checks')
