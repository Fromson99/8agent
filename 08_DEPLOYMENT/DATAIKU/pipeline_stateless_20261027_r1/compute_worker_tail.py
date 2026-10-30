def compute(folder, run, archives):
    root=Path(__file__).resolve().parent
    pins=verify_code(root)
    workspace=folder/'workspace';workspace.mkdir()
    for name in pins['files']:
        dst=t.checked(workspace,name);dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,dst)
    shutil.copyfile(root/'CODE_PINS.json',workspace/'CODE_PINS.json')
    for item in t.read(workspace/'00_SYSTEM/WORKSPACE.json')['roots']:
        (workspace/item['canonical_path']).mkdir(exist_ok=True)
    for slot,prefixes in [('raw',('01_DATA/RAW/','01_DATA/INPUT_MAPPING/')),('support',('01_DATA/LEXICON/','01_DATA/CATALOG/'))]:
        archive=folder/(slot+'.zip')
        if archive.stat().st_size!=archives[slot]['bytes'] or t.sha(archive)!=archives[slot]['sha256']:
            raise ValueError('INPUT_HASH')
        t.write(folder/('input-'+slot+'.json'),t.unpack(archive,workspace,prefixes=prefixes))
    if t.read(folder/'input-support.json')['metadata']['glossary_config_sha256']!=t.sha(workspace/'00_SYSTEM/GLOSSARY_PIPELINE.json'):
        raise ValueError('SUPPORT_POLICY_CHANGED')
    env={k:v for k,v in os.environ.items() if k not in {'LAWRAG_WORKSPACE_ROOT','LAWRAG_TOOL_WORKSPACE_ROOT','PYTHONPATH'}}
    env.update(LAWRAG_WORKSPACE_ROOT=str(workspace),LAWRAG_TOOL_WORKSPACE_ROOT=str(workspace),
               PYTHONPATH=str(workspace/'02_BACKEND'),PYTHONDONTWRITEBYTECODE='1',
               PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH',''),
               OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    for phase,command in stage_commands(workspace,run):
        print('PHASE '+phase,flush=True)
        # Same process group as this worker: one cancellation terminates the full tree.
        subprocess.run(command,cwd=workspace,env=env,check=True)
    verify_code(root)


if __name__=='__main__':
    import json
    if len(sys.argv)==4 and sys.argv[1]=='--export':
        export_result(Path(sys.argv[2]),sys.argv[3])
    elif len(sys.argv)==5 and sys.argv[1]=='--compute':
        compute(Path(sys.argv[2]),sys.argv[3],json.loads(sys.argv[4]))
    else:
        raise SystemExit('COMPUTE_ENTRY_REQUIRED')
