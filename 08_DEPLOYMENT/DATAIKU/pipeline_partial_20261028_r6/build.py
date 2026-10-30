import ast,importlib.util,json,re,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'document_four_types_20261028_r1'
SERVICE='GENOS_DATAIKU_COMPUTE_20261028_R6'
PACKAGE='DATAIKU_COMPUTE_RECIPES_20261028_R6.zip'
OLD_CODE='78811f3b4620c91057a995eaf567cf078c886c6090d3ea02061f3bef2ec5901c'
spec=importlib.util.spec_from_file_location('r5build',BASE/'build.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
sha,edit,writezip=old.sha,old.edit,old.writezip


def worker(source):
    s=source.decode().replace('import review_audit','import review_audit\nimport partial_pipeline\nimport pipeline_coverage')
    s=edit(s,"    return [\n", "    selected=run+'-selected'\n    return [\n")
    s=edit(s,"['document-release', 'prepare', '--run-id', run,", "['document-release', 'prepare', '--run-id', selected,")
    s=edit(s,"['document-release', 'reindex', '--from-run-id', run,\n         '--run-id', run+'-index'", "['document-release', 'reindex', '--from-run-id', selected,\n         '--run-id', selected+'-index'")
    s=edit(s,"'--export', str(root), run])", "'--export', str(root), selected])")
    s=edit(s,"    output = workspace.parent\n", "    output = workspace.parent\n    coverage=pipeline_coverage.validate(t.read(output/'pipeline-coverage.json'))\n    partial_pipeline.verify_generation(generation,coverage)\n")
    s=edit(s,"    paths.update(evidence)", "    paths.update(evidence)\n    paths.update(partial_pipeline.export_paths(output))")
    s=edit(s,"'quality_certified': False, 'active_changed': False, **review_summary}", "'quality_certified': False, 'active_changed': False, 'coverage':pipeline_coverage.summary(coverage), **review_summary}")
    s=edit(s,"print('POD_RUNTIME_CONFIG_OK: document/model execution not yet checked', flush=True)", "print('PIPELINE_CONFIG_OK: mode='+parser_config.environment()[0]+'; document/model execution not yet checked', flush=True)")
    s=edit(s,"    env['GENOS_PREPROCESSOR_TRANSPORT'] = 'pod'\n    env['GENOS_PDF_PARSER'] = 'preprocessor'\n    env['GENOS_PREPROCESSOR_RESPONSE_MODE'] = 'docling'", "    env.update(parser_config.environment()[1])")
    s=edit(s,"        subprocess.run(command,cwd=workspace,env=env,check=True)", """        if phase=='STRUCTURE':
            result=subprocess.run(command,cwd=workspace,env=env,check=False)
            if result.returncode not in (0,2):result.check_returncode()
            print('PHASE SELECT_VERIFIED_SUCCESSES',flush=True)
            subprocess.run([sys.executable,'-B',str(workspace/'worker.py'),'--select',str(workspace),run,str(result.returncode)],cwd=workspace,env=env,check=True)
        else:
            subprocess.run(command,cwd=workspace,env=env,check=True)""")
    s=edit(s,"    elif len(sys.argv)==6 and sys.argv[1]=='--compute':", "    elif len(sys.argv)==5 and sys.argv[1]=='--select':\n        partial_pipeline.select(Path(sys.argv[2]),sys.argv[3],int(sys.argv[4]))\n    elif len(sys.argv)==6 and sys.argv[1]=='--compute':")
    return s.encode()


def controller(source):
    s=source.decode().replace('import transport as t','import transport as t\nimport pipeline_coverage')
    s=edit(s,"    store.value.update(result_blob=store.put_blob(target),phase='STRUCTURED')", """    coverage,blobs=pipeline_coverage.read(target,EXPECTED)
    for name,raw in blobs.items():
        store.folder.upload_stream(prefix+name,io.BytesIO(raw))
    store.value.update(result_blob=store.put_blob(target),phase='STRUCTURED',coverage=coverage,
                       coverage_paths={name:prefix+name for name in blobs})
    pipeline_coverage.display(coverage)""")
    s=edit(s,"'deadline':store.value['deadline'],'oracle_written':False}", "'deadline':store.value['deadline'],'oracle_written':False,\n            'coverage':pipeline_coverage.summary(store.value['coverage']),'coverage_paths':store.value['coverage_paths']}")
    s=edit(s,"        return {'status':'STRUCTURED','reused':True}", "        pipeline_coverage.display(store.value['coverage'])\n        return {'status':structure_status(store),'reused':True,'coverage':record['coverage'],'coverage_paths':record['coverage_paths']}")
    s=edit(s,"        return {'status':'STRUCTURED','oracle_written':False,'logs':'Dataiku managed folder'}", "        return {'status':structure_status(store),'oracle_written':False,'coverage':pipeline_coverage.summary(store.value['coverage']),'coverage_paths':store.value['coverage_paths'],'logs':'Dataiku managed folder'}")
    s=edit(s,"def structured_record(store):", "def structure_status(store):\n    return 'STRUCTURED_WITH_OMISSIONS' if store.value['coverage']['coverage']=='PARTIAL' else 'STRUCTURED'\n\n\ndef structured_record(store):")
    s=edit(s,"    returned=job/'returned'", "    coverage,_=pipeline_coverage.read(job/'result.zip',EXPECTED)\n    if coverage!=upstream.value['coverage']:raise ValueError('LOAD_COVERAGE_CHANGED')\n    returned=job/'returned'")
    s=edit(s,"    t.write(returned/'transport-manifest.json',manifest)", "    pipeline_coverage.verify_generation(returned/'generation',coverage)\n    pipeline_coverage.display(coverage)\n    t.write(returned/'transport-manifest.json',manifest)")
    s=edit(s,"summary={'status':'COMPLETE','oracle_written':True", "summary={'status':'COMPLETE_WITH_OMISSIONS' if coverage['coverage']=='PARTIAL' else 'COMPLETE','coverage':pipeline_coverage.summary(coverage),'coverage_paths':upstream.value['coverage_paths'],'oracle_written':True")
    return s.encode()


def main():
    with zipfile.ZipFile(BASE/'GENOS_DATAIKU_COMPUTE_20261028_R5.zip') as z:original={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    assert sha(original['CODE_PINS.json'])==OLD_CODE
    pins=json.loads(original['CODE_PINS.json']);assert all(sha(original[n])==h for n,h in pins['files'].items())
    payload=dict(original)
    payload['worker.py']=worker(original['worker.py'])
    payload['pod_parser_config.py']=original['parser_config.py']
    with zipfile.ZipFile(HERE.parent/'pipeline_preprocessor_20261027_r3/GENOS_DATAIKU_COMPUTE_20261027_R3.zip') as z:
        payload['http_parser_config.py']=z.read('GENOS_DATAIKU_COMPUTE_20261027_R3/parser_config.py')
    for n in ('partial_pipeline.py','pipeline_coverage.py','parser_config.py'):payload[n]=(HERE/n).read_bytes()
    payload['CODE_PINS.json']=(json.dumps({**pins,'files':{n:sha(b) for n,b in payload.items() if n!='CODE_PINS.json'}},sort_keys=True,indent=2)+'\n').encode()
    code=sha(payload['CODE_PINS.json']);writezip(HERE/(SERVICE+'.zip'),{SERVICE+'/'+n:b for n,b in payload.items()})
    (HERE/'worker.py').write_bytes(payload['worker.py'])
    with zipfile.ZipFile(BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R5.zip') as z:client={n:z.read(n) for n in z.namelist()}
    client['pipeline_coverage.py']=payload['pipeline_coverage.py']
    client['controller.py']=controller(client['controller.py'])
    (HERE/'controller.py').write_bytes(client['controller.py'])
    client['COMPUTE_CODE_SHA256.txt']=(code+'\n').encode()
    upgrade=client['checkpoint_upgrade.py'].decode().replace('PREVIOUS_CODES = {',"PREVIOUS_CODES = {'"+OLD_CODE+"', ")
    upgrade=upgrade.replace("if previous_code in {", "if previous_code in {'"+OLD_CODE+"', ")
    upgrade=upgrade.replace("'reason': 'SAME_POD_PARSER_AND_CONVERSION'", "'reason': 'VERIFIED_SUCCESSFUL_DOCUMENTS_ONLY'")
    client['checkpoint_upgrade.py']=upgrade.encode()
    client['updater.py']=client['updater.py'].replace(b'document-probe-r5-before.json',b'partial-pipeline-r6-before.json')
    ref=json.loads(client['REFERENCE.json']);ref['prior_compute_bootstraps'].append((BASE/'bootstrap.txt').read_text());client['REFERENCE.json']=(json.dumps(ref)+'\n').encode()
    client['PACKAGE_FILES.json']=(json.dumps({n:sha(b) for n,b in client.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    writezip(HERE/PACKAGE,client)
    oldboot=(BASE/'bootstrap.txt').read_text()
    boot=oldboot.replace('DATAIKU_COMPUTE_RECIPES_20261028_R5.zip',PACKAGE).replace(sha((BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R5.zip').read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    boot=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),boot);(HERE/'bootstrap.txt').write_text(boot)
    for kind in ('INSTALL','CONTROL'):
        s=(BASE/f'DATAIKU_R5_{kind}.txt').read_text().replace(oldboot,boot).replace(repr(oldboot),repr(boot)).replace('pipeline_probe_r5_updater','pipeline_partial_r6_updater')
        s=s.replace('PROBE_R5_FLOW_READY: 클라이언트 갱신 완료. 네 문서 확인은 DATAIKU_FOUR_FORMAT_TEST.txt 실행','PARTIAL_R6_FLOW_READY: GENOS R6 리비전 적용 후 00 → 기존 02 → 기존 03 순서로 실행')
        (HERE/f'DATAIKU_R6_{kind}.txt').write_text(s);ast.parse(s)
    for n,b in list(payload.items())+list(client.items()):
        if n.endswith('.py'):compile(b,n,'exec')
    (HERE/'BUILD.json').write_text(json.dumps({'baseline_code_sha256':OLD_CODE,'code_sha256':code,'service_files':len(payload),
        'unchanged_baseline_files':sum(payload.get(n)==b for n,b in original.items()),'changed_files':[n for n,b in payload.items() if original.get(n)!=b],
        'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in (SERVICE+'.zip',PACKAGE)}},indent=2)+'\n')
    print('BUILT',code,len(payload))

if __name__=='__main__':main()
