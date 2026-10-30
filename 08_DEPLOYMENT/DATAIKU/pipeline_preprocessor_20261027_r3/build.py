"""Build a successor from sealed R2 bytes, preserving R1/R2 history."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'pipeline_preprocessor_20261027_r2'
R1 = HERE.parent / 'pipeline_stateless_20261027_r1'
SERVICE = 'GENOS_DATAIKU_COMPUTE_20261027_R3'
PACKAGE = 'DATAIKU_COMPUTE_RECIPES_20261027_R3.zip'
OLD_CODE = '6903032227143a1b94fe0eec8a701592d819a2e08f061ce76453b42df687121c'
R1_CODE = '868b23d7b0b4ac0d825a1a38644a582966118caad7796ca8b6e780df9f322dfa'
spec=importlib.util.spec_from_file_location('sealed_r2_builder',BASE/'build.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
sha, edit, writezip = previous.sha, previous.edit, previous.writezip


def build():
    with zipfile.ZipFile(BASE/'GENOS_DATAIKU_COMPUTE_20261027_R2.zip') as z:
        original={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    assert sha(original['CODE_PINS.json'])==OLD_CODE
    pins=json.loads(original['CODE_PINS.json'])
    assert all(sha(original[n])==h for n,h in pins['files'].items())
    payload=dict(original)
    worker=original['worker.py'].decode().replace('import parser_config','import parser_config\nimport review_audit')
    worker=edit(worker,"'--structure-vlm', 'off'","'--structure-vlm', 'on'")
    worker=edit(worker,"env.setdefault('GENOS_PREPROCESSOR_RESPONSE_MODE', 'docling')", "env.setdefault('GENOS_PREPROCESSOR_RESPONSE_MODE', 'auto')\n    env.setdefault('LLM_BACKEND', 'genos')\n    env['STRUCTURE_RECIPE_VLM'] = 'on'")
    worker=edit(worker,"    t.pack(paths, output / 'result.zip', metadata={'inventory': inventory,", "    evidence, review_summary = review_audit.inventory(workspace)\n    paths.update(evidence)\n    t.write(output/'review-summary.json', review_summary)\n    paths['audit/review-summary.json'] = output/'review-summary.json'\n    t.pack(paths, output / 'result.zip', metadata={'inventory': inventory,")
    worker=edit(worker,"'pipeline': 'native-no-models',\n           'quality_certified': False, 'active_changed': False, 'model_calls': 0", "'pipeline': 'native-existing-genos-review',\n           'quality_certified': False, 'active_changed': False, **review_summary")
    payload['worker.py']=worker.encode()
    service=original['service.py'].decode().replace('import parser_config','import parser_config\nimport review_audit')
    service=edit(service,"        with GUARD:\n            h.update(state='CANCELLED' if code=='CANCELLED' else 'FAILED', error=code)", "        # Publish a terminal state only after the final audit snapshot is ready.\n        try:\n            review_audit.export(folder)\n            h['audit'] = digest_file(folder/'audit.zip')\n        except Exception as audit_error:\n            h['audit_error'] = 'AUDIT_EXPORT_' + type(audit_error).__name__.upper()\n        with GUARD:\n            h.update(state='CANCELLED' if code=='CANCELLED' else 'FAILED', error=code)")
    service=edit(service,"'parser_config_sha256':h['parser_config_sha256'],", "'parser_config_sha256':h['parser_config_sha256'],\n            'audit':h.get('audit'), 'audit_error':h.get('audit_error'),")
    service=edit(service,"kind not in ('log','result')", "kind not in ('log','result','audit')")
    service=edit(service,"            path = h['folder']/('compute.log' if kind=='log' else 'result.zip')", "            if kind=='audit' and (h['state'] not in {'FAILED','CANCELLED'} or not h.get('audit')):\n                raise ValueError('AUDIT_NOT_READY')\n            path = h['folder']/({'log':'compute.log','result':'result.zip','audit':'audit.zip'}[kind])")
    service=edit(service,"            result = public(h)\n            shutil.rmtree(h['folder'])", "            if h.get('audit') and data.get('audit_sha256') != h['audit']['sha256']:\n                raise ValueError('AUDIT_RECEIPT_REQUIRED')\n            result = public(h)\n            shutil.rmtree(h['folder'])")
    payload['service.py']=service.encode()
    for n in ('parser_config.py','review_audit.py'):payload[n]=(HERE/n).read_bytes()
    payload['CODE_PINS.json']=(json.dumps({**pins,'files':{n:sha(b) for n,b in payload.items() if n!='CODE_PINS.json'}},sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode()
    code_sha=sha(payload['CODE_PINS.json'])
    writezip(HERE/(SERVICE+'.zip'),{SERVICE+'/'+n:b for n,b in payload.items()})
    for n in ('worker.py','service.py'):(HERE/n).write_bytes(payload[n])
    with zipfile.ZipFile(BASE/'DATAIKU_COMPUTE_RECIPES_20261027_R2.zip') as z:
        client={n:z.read(n) for n in z.namelist()}
    controller=client['controller.py'].decode()
    controller=edit(controller,"    count=store.value.get('attempt_count',1)\n    if count>=3", "    if store.value.get('model_execution_possible'):\n        raise ValueError('MODEL_RETRY_REQUIRES_PRESERVED_LEDGER_RESUME')\n    count=store.value.get('attempt_count',1)\n    if count>=3")
    controller=edit(controller,"            store.value['phase']='RUN_INTENT';store.save()", "            store.value.update(phase='RUN_INTENT',model_execution_possible=True);store.save()")
    controller=edit(controller,"            budget_call(store,wire,'CLOSE',**auth(state))\n            error=", "            if current.get('audit'):\n                collect_audit(store,wire,state,current['audit'],work)\n                budget_call(store,wire,'CLOSE',**auth(state),audit_sha256=current['audit']['sha256'])\n            elif not current.get('audit_error'):\n                budget_call(store,wire,'CLOSE',**auth(state))\n            else:\n                store.value['audit_error']=current['audit_error'];store.save()\n                print('AUDIT_NOT_SAVED; temporary handle retained until lease expiry',flush=True)\n            error=")
    # A failed audit upload can be retried without re-running any model.
    controller=edit(controller,"    if store.value.get('phase') in {'FAILED','CANCELLED','HANDLE_LOST'}:\n        raise", "    if store.value.get('phase') in {'FAILED','CANCELLED'} and store.value.get('last_observed',{}).get('audit') and not store.value.get('audit_blob'):\n        state=store.value['compute'];audit=store.value['last_observed']['audit']\n        collect_audit(store,wire,state,audit,work)\n        budget_call(store,wire,'CLOSE',**auth(state),audit_sha256=audit['sha256'])\n    if store.value.get('phase') in {'FAILED','CANCELLED','HANDLE_LOST'}:\n        raise")
    controller += '''

def collect_audit(store,wire,state,audit,work):
    """Verified diagnostic-only bytes. Never mark them STRUCTURED/SQL-loadable."""
    if type(audit.get('bytes')) is not int or not 0 < audit['bytes'] <= 64*1024*t.CHUNK or not re.fullmatch('[0-9a-f]{64}',str(audit.get('sha256',''))):
        raise ValueError('AUDIT_MANIFEST')
    archive=work/'compute-audit.zip';offset=0;digest=hashlib.sha256()
    with archive.open('wb') as target:
        while offset<audit['bytes']:
            block=read_chunk(store,wire,state,'audit',offset)
            if not block or offset+len(block)>audit['bytes']:raise ValueError('AUDIT_SIZE')
            save_chunk(store,'attempts/'+state['handle']+'/audit/'+str(offset).zfill(16)+'.chunk',block)
            target.write(block);digest.update(block);offset+=len(block)
    if digest.hexdigest()!=audit['sha256']:raise ValueError('AUDIT_HASH')
    store.value['audit_blob']=store.put_blob(archive);store.save()
'''
    client['controller.py']=controller.encode()
    control=client['control.py'].decode()
    control=edit(control,"    if action=='retry':\n", "    if action=='retry':\n        if state.get('model_execution_possible'):\n            raise ValueError('MODEL_RETRY_REQUIRES_PRESERVED_LEDGER_RESUME')\n")
    control=edit(control,"'result_saved':bool(state.get('result_blob'))", "'result_saved':bool(state.get('result_blob')),\n                 'audit_saved':bool(state.get('audit_blob')),\n                 'model_execution_possible':bool(state.get('model_execution_possible'))")
    client['control.py']=control.encode()
    client['checkpoint_upgrade.py']=(HERE/'checkpoint_upgrade.py').read_bytes()
    client['COMPUTE_CODE_SHA256.txt']=(code_sha+'\n').encode()
    runtime=client['recipes_runtime.py'].decode().replace("'PREPROCESSOR_DOCLING_RESPONSE_REQUIRED'", "'PREPROCESSOR_RESPONSE_MODE_INVALID','PREPROCESSOR_REVIEW_CONFIG_REQUIRED','AUDIT_NOT_READY','AUDIT_RECEIPT_REQUIRED'")
    client['recipes_runtime.py']=runtime.encode()
    updater=client['updater.py'].decode().replace('preprocessor-r2-before.json','preprocessor-r3-before.json')
    updater=edit(updater,"return [ref['prior_compute_bootstrap']+'\\nrun_recipe('+repr(stage)+', '+repr(cfg)+')\\n']", "return [b+'\\nrun_recipe('+repr(stage)+', '+repr(cfg)+')\\n' for b in ref['prior_compute_bootstraps']]")
    client['updater.py']=updater.encode()
    ref=json.loads(client['REFERENCE.json'])
    ref['prior_compute_bootstraps']=[(R1/'bootstrap.txt').read_text(),(BASE/'bootstrap.txt').read_text()]
    client['REFERENCE.json']=(json.dumps(ref)+'\n').encode()
    client['PACKAGE_FILES.json']=(json.dumps({n:sha(b) for n,b in client.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    writezip(HERE/PACKAGE,client)
    for n in ('controller.py','updater.py'):(HERE/n).write_bytes(client[n])
    old_boot=(BASE/'bootstrap.txt').read_text()
    boot=old_boot.replace('DATAIKU_COMPUTE_RECIPES_20261027_R2.zip',PACKAGE).replace(sha((BASE/'DATAIKU_COMPUTE_RECIPES_20261027_R2.zip').read_bytes()),sha((HERE/PACKAGE).read_bytes())).replace('PACKAGE_BYTES = 282044','PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size))
    (HERE/'bootstrap.txt').write_text(boot)
    for kind in ('INSTALL','CONTROL'):
        content=(BASE/f'DATAIKU_PREPROCESSOR_{kind}_20261027_R2.txt').read_text()
        content=content.replace(old_boot,boot).replace(repr(old_boot),repr(boot)).replace('pipeline_preprocessor_r2_updater','pipeline_preprocessor_r3_updater').replace('PREPROCESSOR_R2_FLOW_READY','PREPROCESSOR_R3_FLOW_READY')
        (HERE/f'DATAIKU_PREPROCESSOR_{kind}_20261027_R3.txt').write_text(content)
        ast.parse(content)
    for name,content in payload.items():
        if name.endswith('.py'):compile(content,name,'exec')
    result={'baseline_code_sha256':OLD_CODE,'supported_previous_code_sha256':[R1_CODE,OLD_CODE],
            'code_sha256':code_sha,'service_changed':[n for n,b in payload.items() if b!=original.get(n)],
            'service_files':len(payload),'service_unchanged':sum(payload.get(n)==b for n,b in original.items()),
            'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in (SERVICE+'.zip',PACKAGE)}}
    (HERE/'BUILD.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':build()
