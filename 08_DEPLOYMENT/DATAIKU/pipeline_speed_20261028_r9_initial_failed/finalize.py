"""Bind the tested local delivery and measured component; field time is unknown."""
import ast
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from build import HERE, ROOT, BASE, SERVICE, PACKAGE, OLD_CODE, sha, save, writezip


def suite(name, expected):
    tests=ET.parse(HERE/name).getroot().findall('.//testcase')
    failed=[t.attrib['name'] for t in tests if t.find('failure') is not None or t.find('error') is not None or t.find('skipped') is not None]
    assert len(tests)==expected and not failed,(name,len(tests),failed)
    return {'tests':len(tests),'passed':len(tests),'failed':failed}


def main():
    suites={'protocol_install_resume':suite('TEST.xml',103),'native_pipeline':suite('NATIVE_TEST.xml',4)}
    build=json.loads((HERE/'BUILD.json').read_text())
    with zipfile.ZipFile(HERE/(SERVICE+'.zip')) as z:
        payload={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    pins=json.loads(payload['CODE_PINS.json'])['files']
    assert sha(payload['CODE_PINS.json'])==build['code_sha256']
    assert all(sha(payload[n])==h for n,h in pins.items())
    assert set(payload)==set(pins)|{'CODE_PINS.json'}
    with zipfile.ZipFile(BASE/'GENOS_DATAIKU_COMPUTE_20261028_R8.zip') as z:
        old={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    changed=[n for n in payload if payload[n]!=old[n]]
    assert set(changed)=={'worker.py','02_BACKEND/semantic_runtime/unit_fulltext.py','CODE_PINS.json'}
    assert "'--fulltext-workers', '4'" in payload['worker.py'].decode()
    assert 'chunksize=1)' in payload['02_BACKEND/semantic_runtime/unit_fulltext.py'].decode()
    with zipfile.ZipFile(HERE/PACKAGE) as z:
        client={n:z.read(n) for n in z.namelist()}
    assert client['COMPUTE_CODE_SHA256.txt'].decode().strip()==build['code_sha256']
    files=json.loads(client['PACKAGE_FILES.json'])
    assert set(client)==set(files)|{'PACKAGE_FILES.json'}
    assert all(sha(client[n])==h for n,h in files.items())
    for name, row in build['files'].items():
        raw=(HERE/name).read_bytes();assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
    for name in ['GENOS_R9_INSTALL.txt','ROLLBACK_GENOS.txt']:
        subprocess.run(['bash','-n',str(HERE/name)],check=True)
    for name in ['DATAIKU_R9_INSTALL.txt','DATAIKU_R9_CONTROL.txt','DATAIKU_02_시간진단.txt']:
        ast.parse((HERE/name).read_text())
    embedded=(HERE/'install_compute.py').read_text().split("if __name__ == '__main__':")[0]
    install=(HERE/'GENOS_R9_INSTALL.txt').read_text()
    for tag in ('PY_INSTALL','PY_STAGE'):
        cell=install.split("<<'"+tag+"'\n")[1].split('\n'+tag)[0]
        assert cell.startswith(embedded);ast.parse(cell)
    checkouts=[]
    for dev in sorted((ROOT/'09_ARTIFACTS/TEMP/speed-r9-lifecycle-final').glob('test_genos_install_same_checko*/DEV')):
        if 'current' in str(dev):continue
        raw=subprocess.check_output(['git','show','HEAD:CODE_PINS.json'],cwd=dev)
        assert sha(raw)==build['code_sha256']
        checkouts.append({'path':str(dev),'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=dev,text=True).strip(),
            'committed_pins_sha256':sha(raw),'installed_checked_then_rolled_back':True})
    assert len(checkouts)==7
    native=[]
    for p in sorted((ROOT/'09_ARTIFACTS/TEMP/speed-r9-native-final').glob('test_actual_native_flow_with*/compute/result.zip')):
        if 'current' in str(p):continue
        with zipfile.ZipFile(p) as z:
            release=json.loads(z.read('audit/release.json'))
            assert release['settings']['fulltext_workers']==4 and release['offline_e2e']=='PASS'
        native.append({'archive':str(p),'sha256':sha(p.read_bytes()),'fulltext_workers':4,'offline_e2e':'PASS'})
    assert len(native)==2
    a0=ROOT/'04_EXPERIMENTS/ADR/ADR-1180-pipeline02-bounded-index-speed/artifacts/run-001/result.json'
    a1=ROOT/'04_EXPERIMENTS/ADR/ADR-1181-pipeline02-balanced-tokenization/artifacts/run-001/result.json'
    r0=json.loads(a0.read_text());r1=json.loads(a1.read_text())
    slow=r0['runs'][0]['measurement']['seconds'];previous=r1['runs'][0]['measurement']['seconds'];fast=r1['runs'][1]['measurement']['seconds']
    assert all(r['mismatches']==0 and r['exit_code']==0 for r in r1['runs'])
    assert fast/previous<=0.85
    performance={'scope':'Local PeCab token generation for12288fixedunitinputs, not wholeindex/02/GENOS',
        'first_1worker_seconds':slow,'fresh_3worker_cache_seconds':previous,'4worker_balanced_seconds':fast,
        'first_1worker_to_final_ratio':slow/fast,'fresh_followup_reduction_percent':100*(1-fast/previous),
        'mismatches':0,'peak_process_group_bytes':r1['runs'][1]['peak_process_group_bytes'],
        'single_runs_fixed_order':True,'local_logical_cpus':r1['local_logical_cpus'],'field_cpu':4,'field_ram_gib':16,
        'records':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p.read_bytes())} for p in (a0,a1)]}
    binding={'baseline_code_sha256':OLD_CODE,'code_pins_sha256':build['code_sha256'],'code_zip':build['files'][SERVICE+'.zip'],
        'critical_files':{n:pins[n] for n in changed if n in pins},'local_installer_checkouts':checkouts,'native_generations':native,
        'field_checkout':'~/DEV legal_pipeline_serving; absolute path unconfirmed','field_commit':None,'field_revision':None,
        'field_generation':None,'generation_policy':'ephemeral compute; Dataiku owns state/logs/results',
        'root_commit_push':False,'main_changed':False,'onsite_deployed':False,'local_python':sys.version,'platform':platform.platform()}
    save('RELEASE_BINDING.json',binding)
    save('VALIDATION.json',{'status':'LOCAL_TECHNICAL_DELIVERY_PASS_FIELD_1H_UNVERIFIED','suites':suites,'tests_passed':107,
        'server_files':len(payload),'unchanged_r8_files':len(payload)-len(changed),'changed_server_files':changed,
        'performance':performance,'model_calls':0,'onsite_total_seconds':None,'goal_1hour_achieved':False,
        'intermediate_failed_added_resume':False,'raw_01_reusable':True,'requires_02_recompute':True,
        'main_changed':False,'onsite_deployed':False,'email_sent':False,
        'preserved_diagnostics':['INTERRUPTED_TEST.log: sandbox async wait after13checks','ASYNC_DIAGNOSTIC.log: idle worker and asyncio selector wait; identical103tests passed outside restricted harness'],
        'inherited_r8_compatibility_note':'R8 historical compatibility test failure is preserved in its validation; this delivery does not relabel the old suite as all-pass.'})
    names=[SERVICE+'.zip',PACKAGE,'CODE_MANIFEST.json','RELEASE_BINDING.json','VALIDATION.json','GENOS_R9_INSTALL.txt',
        'DATAIKU_R9_INSTALL.txt','DATAIKU_R9_CONTROL.txt','DATAIKU_02_시간진단.txt','ROLLBACK_GENOS.txt',
        'install_compute.py','GUIDE.txt','PATCH_NOTES.txt']
    outer=HERE/'DATAIKU_SPEED_20261028_R9.zip';writezip(outer,{n:(HERE/n).read_bytes() for n in names})
    with zipfile.ZipFile(outer) as z:
        assert z.testzip() is None and set(z.namelist())==set(names)
        assert all(z.read(n)==(HERE/n).read_bytes() for n in names)
    save('DELIVERY_MANIFEST.json',{**build,'delivery_files':{n:{'bytes':(HERE/n).stat().st_size,'sha256':sha((HERE/n).read_bytes())} for n in names+[outer.name]},'onsite_deployed':False,'email_sent':False})
    print('VALIDATED',107,'tests',str(outer),outer.stat().st_size)

if __name__=='__main__':main()
