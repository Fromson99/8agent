"""Rebuild from immutable R2 compute / R1 split-layer recipe payloads."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_recipes_20261027_r1'
OLD=HERE.parent/'pipeline_mapped_20261023_r1/GENOS_PIPELINE_SERVICE_20261022_R2.zip'
SERVICE='GENOS_DATAIKU_COMPUTE_20261027_R1'
PACKAGE='DATAIKU_COMPUTE_RECIPES_20261027_R1.zip'

def sha(b):return hashlib.sha256(b).hexdigest()
def writezip(path,values):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in sorted(values.items()):
            info=zipfile.ZipInfo(name,(2026,10,27,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,content)

def build():
    assert sha(OLD.read_bytes())=='a1650207b077571446df2c2942403f4e9c0bfc5781d509db8658d66f2a81b926'
    with zipfile.ZipFile(OLD) as z:
        prefix=OLD.stem+'/'
        payload={n[len(prefix):]:z.read(n) for n in z.namelist()}
    oldpins=json.loads(payload['CODE_PINS.json'])
    assert sha(payload['CODE_PINS.json'])=='771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46'
    for n,h in oldpins['files'].items():assert sha(payload[n])==h,n
    oldworker=payload['worker.py'].decode()
    imports='import os\nfrom pathlib import Path\nimport shutil\nimport subprocess\nimport sys\nimport transport as t\n\n'
    selected=[ast.get_source_segment(oldworker,n) for n in ast.parse(oldworker).body
              if isinstance(n,ast.FunctionDef) and n.name in ('process_group_rss','verify_code','stage_commands','export_result')]
    worker=imports+'\n\n'.join(selected)+'\n\n'+(HERE/'compute_worker_tail.py').read_text()
    payload['worker.py']=worker.encode()
    payload['service.py']=(HERE/'compute_service.py').read_bytes()
    # Preserve engine bytes exactly; update only compute transport + worker wrapper.
    pins={**oldpins,'files':{n:sha(b) for n,b in payload.items() if n!='CODE_PINS.json'}}
    payload['CODE_PINS.json']=(json.dumps(pins,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode()
    code_sha=sha(payload['CODE_PINS.json'])
    writezip(HERE/(SERVICE+'.zip'),{SERVICE+'/'+n:b for n,b in payload.items()})
    (HERE/'COMPUTE_CODE_SHA256.txt').write_text(code_sha+'\n')
    with zipfile.ZipFile(BASE/'DATAIKU_RECIPE_PACKAGE_20261027_R1.zip') as z: client={n:z.read(n) for n in z.namelist()}
    ref=json.loads((HERE.parent/'pipeline_input_selection_20261027_r2/REFERENCE.json').read_text())
    runtime=client['recipes_runtime.py'].decode()
    runtime=runtime.replace("{'BUSY', 'INSTANCE_MISMATCH', 'CODE_MISMATCH', 'UNKNOWN_JOB'}",
       "{'BUSY','INSTANCE_MISMATCH','CODE_MISMATCH','UNKNOWN_JOB','COMPUTE_INSTANCE_CHANGED','COMPUTE_HANDLE_GONE','COMPUTE_LEASE_EXPIRED','COMPUTE_CAPACITY','COMPUTE_AUTH'}")
    client['recipes_runtime.py']=runtime.encode()
    client['named_inputs.py']=ref['adapter_source'].encode()
    for name in ['controller.py','COMPUTE_CODE_SHA256.txt','control.py']:
        client[name]=(HERE/name).read_bytes()
    client['REFERENCE.json']=(json.dumps(ref)+'\n').encode()
    client['resume_source.txt']=(HERE.parent/'pipeline_resume_20261027_r3/resume.py').read_bytes()
    client['updater.py']=(HERE/'updater.py').read_bytes()
    writezip(HERE/PACKAGE,client)
    bootstrap=(BASE/'bootstrap.py').read_text().replace(
        '        import recipes_runtime\n        recipes_runtime.execute(stage, cfg, work)',
        '        import recipes_runtime\n        from named_inputs import install_input_selection\n'
        '        install_input_selection(recipes_runtime)\n        import controller\n        controller.execute(stage, cfg, work)')
    constants="LANDING_ID = 'ehA8dpVm'\nPACKAGE_NAME = "+repr(PACKAGE)+"\nPACKAGE_SHA256 = "+repr(sha((HERE/PACKAGE).read_bytes()))+"\nPACKAGE_BYTES = "+str((HERE/PACKAGE).stat().st_size)+'\n'
    bootstrap=constants+bootstrap
    (HERE/'bootstrap.txt').write_text(bootstrap)
    script="# LEGAL_RAG Python 노트북: 전체를 한 셀에서 실행. 레시피 실행 중 설치하지 마세요.\nACTION = 'apply' # apply / inspect / rollback\n"+bootstrap+'''
work, root = verified_package()
sys.path.insert(0,str(root))
import updater
CFG=updater.update(dataiku.api_client().get_project('LEGAL_RAG'),root,BOOTSTRAP,ACTION)
print('DATAIKU_COMPUTE_FLOW_READY: GENOS 새 리비전 배포 후 00 → 02 → 03')
'''
    script=script.replace('work, root = verified_package()\nsys.path.insert', 'BOOTSTRAP = '+repr(bootstrap)+'\nwork, root = verified_package()\nsys.path.insert')
    (HERE/'DATAIKU_COMPUTE_INSTALL_20261027_R1.txt').write_text(script)
    control='# Dataiku LEGAL_RAG 노트북 한 셀 전체 실행\nACTION = "cancel" # status / cancel / retry\n'+bootstrap+'''
work, root = verified_package()
sys.path[:0]=[str(root),str(root/'client'),str(root/'client/02_BACKEND')]
import control
control.run(ACTION,root,work)
'''
    (HERE/'DATAIKU_COMPUTE_CONTROL_20261027_R1.txt').write_text(control)
    for n in ['DATAIKU_COMPUTE_INSTALL_20261027_R1.txt','DATAIKU_COMPUTE_CONTROL_20261027_R1.txt']:
        ast.parse((HERE/n).read_text(),feature_version=(3,9));compile((HERE/n).read_text(),n,'exec')
    out={'protocol':'dataiku-owned-compute-v1','code_sha256':code_sha,'baseline_code_sha256':'771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46',
         'unchanged_engine_files':len(payload)-3,'service_files':len(payload),
         'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in
             [SERVICE+'.zip',PACKAGE,'DATAIKU_COMPUTE_INSTALL_20261027_R1.txt','DATAIKU_COMPUTE_CONTROL_20261027_R1.txt']}}
    (HERE/'BUILD.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__':build()
