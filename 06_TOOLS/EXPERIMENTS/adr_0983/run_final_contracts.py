from common import *
import subprocess,time,xml.etree.ElementTree as ET
f=read(ART/'design-freeze.json');paths=list(f['design']['test_bindings'])
for n,h in f['design']['test_bindings'].items():assert sha(ROOT/n)==h,n
out=ART/'contracts-final.log';xml=ART/'contracts-final.xml';assert not out.exists()
with out.open('x') as stream:
 p=subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('run_contracts.py')),'-q',*paths,'--tb=short','--junitxml='+str(xml)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=540)
suites=ET.parse(xml).getroot().findall('testsuite')
result={'passed':p.returncode==0,'tests':sum(int(x.get('tests')) for x in suites),'failures':sum(int(x.get('failures')) for x in suites),'errors':sum(int(x.get('errors')) for x in suites),'xml_sha256':sha(xml),'log_sha256':sha(out)}
save(ART/'contracts-final.json',result);print(result,flush=True)
