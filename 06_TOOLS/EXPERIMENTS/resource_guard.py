"""Run one resource-bounded verification worker; preserve measurements on failure."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,resource,shutil,signal,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('--record',required=True);p.add_argument('--rss-gib',type=float,default=8);p.add_argument('--as-gib',type=float,default=9);p.add_argument('--min-available-gib',type=float,default=2);p.add_argument('--min-disk-gib',type=float,default=10);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
G=1024**3;cmd=a.command[1:] if a.command[:1]==['--'] else a.command
if not cmd:p.error('a command is required')
out=Path(a.record).resolve();out.parent.mkdir(parents=True,exist_ok=True)
if out.exists():raise SystemExit('Preserve existing resource receipt; use a new attempt path')
lock=open('/tmp/8agent-heavy-verification.lock','a')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('Another guarded heavy verification is running')
def available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):return int(line.split()[1])*1024
def free_disk():return min(shutil.disk_usage(Path.cwd()).free,shutil.disk_usage('/mnt/c').free)
if available()<a.min_available_gib*G+G:raise SystemExit('Insufficient free RAM to start safely')
if free_disk()<a.min_disk_gib*G:raise SystemExit('Insufficient physical disk space to start safely')
def limits():resource.setrlimit(resource.RLIMIT_AS,(int(a.as_gib*G),int(a.as_gib*G)))
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
start=time.monotonic();child=subprocess.Popen(cmd,env=env,start_new_session=True,preexec_fn=limits)
peak=0;minimum=available();reason=None;signalled=None;samples=out.with_suffix('.jsonl')
def rss_group():
    total=0
    for d in Path('/proc').iterdir():
        if not d.name.isdigit():continue
        try:
            if os.getpgid(int(d.name))!=child.pid:continue
            for line in (d/'status').read_text().splitlines():
                if line.startswith('VmRSS:'):total+=int(line.split()[1])*1024;break
        except (OSError,ValueError):pass
    return total
try:
    with samples.open('x') as log:
        while child.poll() is None:
            rss=rss_group();av=available();disk=free_disk();peak=max(peak,rss);minimum=min(minimum,av)
            log.write(json.dumps({'seconds':round(time.monotonic()-start,2),'rss_bytes':rss,'available_bytes':av,'disk_free_bytes':disk})+'\n');log.flush()
            if reason is None:
                if rss>a.rss_gib*G:reason='worker_rss_ceiling'
                elif av<a.min_available_gib*G:reason='system_available_memory_floor'
                elif disk<a.min_disk_gib*G:reason='physical_disk_floor'
                if reason:
                    print('RESOURCE_STOP '+reason,flush=True);os.killpg(child.pid,signal.SIGINT);signalled=time.monotonic()
            elif time.monotonic()-signalled>10:os.killpg(child.pid,signal.SIGKILL)
            time.sleep(2)
except KeyboardInterrupt:
    reason='user_interrupted';os.killpg(child.pid,signal.SIGINT)
finally:
    try:code=child.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);code=child.wait()
    value={'command':cmd,'returncode':code,'stop_reason':reason,'seconds':time.monotonic()-start,'peak_group_rss_bytes':peak,'min_available_bytes':minimum,'limits':vars(a),'samples_sha256':hashlib.sha256(samples.read_bytes()).hexdigest()}
    out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
raise SystemExit(code if code else 75 if reason else 0)
