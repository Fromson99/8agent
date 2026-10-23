"""One child at a time; resource pressure stops remaining trials, never retries."""
from common import *
import subprocess,time,signal,sys
kind=sys.argv[1]
assert kind in ('candidate','trials','contracts')
def available():return next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
def run(args,label,ceiling,timeout):
 assert available()>3*1024**3
 log=ART/(label+'.log');assert not log.exists()
 start=time.monotonic();peak=0;cause=None
 with log.open('x') as stream:
  p=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-B',*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
  while p.poll() is None:
   path=Path(f'/proc/{p.pid}/status')
   rss=next((int(x.split()[1])*1024 for x in path.read_text().splitlines() if x.startswith('VmRSS:')),0) if path.exists() else 0
   peak=max(peak,rss)
   if rss>ceiling or available()<3*1024**3 or time.monotonic()-start>timeout:
    cause='MEMORY_OR_DEADLINE';p.send_signal(signal.SIGINT)
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
    break
   time.sleep(.5)
 save(ART/(label+'-resources.json'),{'exit_code':p.returncode,'peak_rss_bytes':peak,'seconds':time.monotonic()-start,'interruption':cause})
 print(label,p.returncode,round(peak/1024**2),'MiB',flush=True)
 if p.returncode or cause:raise SystemExit(1)
if kind=='candidate':run([str(Path(__file__).with_name('full_query.py')),'candidate'],'known-candidate',6*1024**3,1200)
if kind=='trials':
 for cid,arm in read(ART/'design-freeze.json')['design']['call_order'][2:]:
  run([str(Path(__file__).with_name('run_case.py')),arm,cid],f'trial-{cid}-{arm}',1024**3,240)
if kind=='contracts':
 C=ROOT/read(ART/'stage.json')['roots']['candidate']
 names=['test_assessment_review_continuity','test_read_choice_input_preservation','test_source_span_norm','test_assessment_source_reply','test_bounded_delivered_handoff','test_assessment_gap_action','test_reference_decision_continuity','test_reference_context_continuity','test_public_display_boundary','test_unified_scope_semantic_authority']
 paths=[str((C if (C/f'05_TESTS/CONTRACTS/{n}.py').exists() else ROOT)/f'05_TESTS/CONTRACTS/{n}.py') for n in names]
 run([str(Path(__file__).with_name('run_contracts.py')),'-q',*paths,'--tb=short','--junitxml='+str(ART/'contracts.xml')],'contracts',3*1024**3,480)
