"""Sequential, bounded test batches on the frozen candidate plus two recovery audits."""
from common import *
import subprocess,time,signal,xml.etree.ElementTree as ET
m=read(ART/'design-freeze.json')
for n,h in m['design']['test_bindings'].items():assert sha(ROOT/n)==h,n
sets=[['test_required_structure_selection','test_model_structure_selection','test_structural_scope_output_recovery'],
      ['test_natural_language_routing','test_scoped_multiturn_api','test_multiturn_structured_scope'],
      ['test_law_name_recovery','test_unattempted_gap_finish','test_assessment_source_reply','test_public_display_boundary','test_memory_runtime_v2']]
results=[]
for i,names in enumerate(sets,1):
    log=ART/f'contracts-final-{i}.log';xml=ART/f'contracts-final-{i}.xml'
    assert not log.exists() and not xml.exists()
    cmd=[str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('run_contracts.py')),'-q',*[f'05_TESTS/CONTRACTS/{n}.py' for n in names],'--junitxml='+str(xml)]
    with log.open('x') as f:
        proc=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT);start=time.monotonic();peak=0
        while proc.poll() is None:
            st=Path(f'/proc/{proc.pid}/status')
            rss=next((int(x.split()[1])*1024 for x in st.read_text().splitlines() if x.startswith('VmRSS:')),0) if st.exists() else 0;peak=max(peak,rss)
            if rss>1024**3 or time.monotonic()-start>240:proc.send_signal(signal.SIGINT);proc.wait(timeout=15);raise RuntimeError('contract resource limit')
            time.sleep(.25)
    suites=ET.parse(xml).getroot().findall('testsuite');passed=proc.returncode==0 and all(int(s.get('errors',0))==int(s.get('failures',0))==0 for s in suites)
    results.append({'batch':i,'passed':passed,'tests':sum(int(s.get('tests')) for s in suites),'peak_rss_bytes':peak,'xml':{'path':str(xml.relative_to(ROOT)),'sha256':sha(xml)},'log':{'path':str(log.relative_to(ROOT)),'sha256':sha(log)}})
    print('batch',i,results[-1]['tests'],'pass',passed,flush=True)
save(ART/'contracts-final.json',{'passed':all(r['passed'] for r in results),'tests':sum(r['tests'] for r in results),'batches':results,'extra_recovery_audit':{'path':'05_TESTS/CONTRACTS/test_structural_scope_output_recovery.py','sha256':sha(ROOT/'05_TESTS/CONTRACTS/test_structural_scope_output_recovery.py'),'added_after_model_freeze':True,'purpose':'Additional deterministic omitted-field repair/resume coverage; no model outcome or threshold change'}})
