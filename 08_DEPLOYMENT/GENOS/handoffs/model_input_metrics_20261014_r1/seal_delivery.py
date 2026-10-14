"""Seal verified code, exact installer bytes and compact validation records."""
import ast, gzip, hashlib, json, subprocess, zipfile
from pathlib import Path
import xml.etree.ElementTree as E

O=Path(__file__).resolve().parent; R=O.parents[3]; N='GENOS_MODEL_INPUT_METRICS_20261014_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()


def main():
    assert not (O/(N+'.zip')).exists(), 'Preserve sealed archive'
    source=json.loads((O/'SOURCE_BINDING.json').read_bytes())
    assert source['source_files']==json.loads((O/'WORKING_INTEGRATION.json').read_bytes())['source_files']
    for n,h in source['source_files'].items():
        raw=(R/n).read_bytes();assert sha(raw)==h;ast.parse(raw,feature_version=(3,10))
        p=O/'payload'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    def stats(name):
        suite=E.parse(O/name).getroot().find('testsuite')
        return {k:int(suite.attrib[k]) for k in ('tests','failures','errors','skipped')}
    def failures(name):
        return sorted(t.attrib['name'] for t in E.parse(O/name).iter('testcase') if t.find('failure') is not None)
    assert stats('DELIVERY_TESTS.xml')=={'tests':4,'failures':0,'errors':0,'skipped':0}
    assert failures('WORKING_TESTS.xml')==failures('BASELINE_TESTS.xml')
    command_count=boots=gates=installed_tests=0;roots=[]
    for path in sorted(O.glob('TEST_*.json.gz')):
        rows=json.loads(gzip.decompress(path.read_bytes()));command_count+=len(rows)
        assert rows[-1]['returncode']==0 and rows[-1]['argv'][2]=='undo'
        for row in rows:
            out=row['stdout']
            boots+=out.count('SERVICE_PROFILE_BOOTSTRAP PASS')
            gates+=out.count('GENOS_RELEASE_GATE PASS')
            if 'installed_runner.py' in str(row['argv']):
                assert row['returncode']==0 and '20 passed' in out
                installed_tests+=20;roots.append(row['argv'][2])
    assert boots==8 and gates==4 and installed_tests==80
    active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
    validation={'revision':N,'working_tests':stats('WORKING_TESTS.xml'),
        'unchanged_baseline_tests':stats('BASELINE_TESTS.xml'),'unchanged_failures':failures('BASELINE_TESTS.xml'),
        'delivery_tests':stats('DELIVERY_TESTS.xml'),'installed_contract_tests':installed_tests,
        'service_boots':boots,'same_checkout_synthetic_generation_gates':gates,'installer_commands':command_count,
        'verified_code_roots':roots,'known_inventories':source['known_predecessors'],
        'source_files':source['source_files'],'real_model_calls':0,'real_network_calls':0,
        'active_release_unchanged':active['release_id'],'active_generation':active['generation'],
        'genos_field_deployment':'NOT_VERIFIED','field_commit':None,'field_generation_path':None,
        'field_generation_manifest_sha256':None,'field_serving_revision':None,
        'test_data':'synthetic generation built locally; installed readers/API and same installed engine pins verified',
        'limits':['length root cause and internal context capacity require field evidence',
            'nine existing broad-suite failures remain', 'no MAIN promotion or GENOS deployment'],
        'fixture_repairs':['build-only factorized_audit absent in field bundle; prebuilt synthetic tree supplied',
            'isolated synthetic tree directory to avoid fixture database collision']}
    (O/'VALIDATION.json').write_bytes(enc(validation))
    for n in ('WORKING_TESTS.xml','BASELINE_TESTS.xml','DELIVERY_TESTS.xml','BASELINE_TESTS.log','DELIVERY_FIXTURE_SETUP_FAILURE.xml'):
        p=O/n
        if p.exists():(O/(n+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
    for name in ('test_model_input_metrics.py','test_final_failure_logging.py'):
        p=O/'tests'/name;p.parent.mkdir(exist_ok=True);p.write_bytes((R/'05_TESTS/CONTRACTS'/name).read_bytes())
    include=['apply_patch.py','PATCH_SPEC.json.gz','SOURCE_BINDING.json','INVENTORY_BINDINGS.json.gz',
        'WORKING_INTEGRATION.json','VALIDATION.json','GUIDE_UTF8.txt','FINDINGS_UTF8.txt',N+'_RUN.txt',
        'build_delivery.py','bind_working.py','seal_delivery.py','test_delivery.py','installed_runner.py','baseline_runner.py']
    include += [str(p.relative_to(O)) for folder in ('payload','reviewed','tests') for p in (O/folder).rglob('*.py') if p.is_file()]
    include += [p.name for p in O.glob('TEST_*.json.gz')]
    include += [p.name for p in O.glob('*TESTS*.gz')]
    manifest={'version':N,'files':[{'path':n,'sha256':sha((O/n).read_bytes()),'bytes':(O/n).stat().st_size} for n in sorted(set(include))]}
    (O/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    with zipfile.ZipFile(O/(N+'.zip'),'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n in sorted(set(include+['CODE_MANIFEST.json'])):z.write(O/n,n)
    with zipfile.ZipFile(O/(N+'.zip')) as z:
        assert z.testzip() is None
        for row in manifest['files']:assert sha(z.read(row['path']))==row['sha256']
        assert z.read(N+'_RUN.txt')==(O/(N+'_RUN.txt')).read_bytes()
    names=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','FINDINGS_UTF8.txt','VALIDATION.json']
    (O/'SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in names))
    print(json.dumps({'zip_bytes':(O/(N+'.zip')).stat().st_size,'sha256':sha((O/(N+'.zip')).read_bytes()),
        'installed_contract_tests':installed_tests,'service_boots':boots,'generation_gates':gates,'commands':command_count}))


if __name__=='__main__':main()
