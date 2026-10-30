"""Frozen experiment-only admission and continuous pressure monitor."""
from common import *
import os,shutil,threading,time
GIB=1024**3;MIB=1024**2
def sample():
 mem={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith(('MemAvailable:','SwapTotal:','SwapFree:'))}
 rss=next(int(x.split()[1])*1024 for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:'))
 psi={x.split()[0]:float(x.split()[1].split('=')[1]) for x in Path('/proc/pressure/memory').read_text().splitlines()}
 vm={x.split()[0]:int(x.split()[1]) for x in Path('/proc/vmstat').read_text().splitlines() if x.startswith(('pswpin ','pswpout '))}
 return dict(time=time.time(),available=mem['MemAvailable'],swap_used=mem['SwapTotal']-mem['SwapFree'],rss=rss,disk=shutil.disk_usage(ROOT).free,psi=psi,vm=vm)
def violation(s,b,startup=False):
 if s['available']<(5 if startup else 3)*GIB:return 'available RAM below frozen minimum'
 if s['rss']>4*GIB:return 'worker RSS above 4GiB'
 if s['disk']<20*GIB:return 'workspace free disk below 20GiB'
 if s['swap_used']-b['swap_used']>128*MIB:return 'global swap growth above 128MiB since admission'
 if s['psi']['full']>1.0:return 'memory full stall avg10 above 1 percent'
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
 def start(self):
  def watch():
   with (self.out/'resource-samples.jsonl').open('a') as log:
    while not self.done.wait(1):
     log.write(json.dumps(self.check())+'\n');log.flush()
  threading.Thread(target=watch,daemon=True).start()
def self_test():
 b={'available':6*GIB,'rss':GIB,'disk':30*GIB,'swap_used':3500*MIB,'psi':{'full':0}}
 assert violation(b,b,True) is None
 for key,val in [('available',2*GIB),('rss',5*GIB),('disk',GIB),('swap_used',b['swap_used']+129*MIB),('psi',{'full':1.1})]:
  assert violation({**b,key:val},b) is not None
 assert violation({**b,'available':4*GIB},b,True) is not None
 assert violation({**b,'available':4*GIB},b) is None
 return 8
