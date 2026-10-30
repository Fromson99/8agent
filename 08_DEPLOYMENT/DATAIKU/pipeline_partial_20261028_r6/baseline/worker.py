import os
from pathlib import Path
import shutil
import subprocess
import sys
import transport as t
import parser_config
import review_audit

def process_group_rss(group):
    pages = 0
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == group:
                pages += int(fields[21])
        except (FileNotFoundError, ProcessLookupError):
            pass
    return pages * os.sysconf('SC_PAGE_SIZE')

def verify_code(root):
    pins = t.read(root / 'CODE_PINS.json')
    for name, expected in pins['files'].items():
        if t.sha(t.checked(root, name)) != expected:
            raise ValueError('CODE_CHANGED: ' + name)
    return pins

def stage_commands(root, run):
    pipeline = [sys.executable, '-B', str(root / '06_TOOLS/pipeline.py')]
    policy = t.read(root / '00_SYSTEM/GLOSSARY_PIPELINE.json')
    glossary = root / '01_DATA' / policy['current_draft']['path']
    return [
        ('STRUCTURE', pipeline + ['build-data-stages', '--run-id', run, '--stage', 'structure', '--execute',
         '--latest-internal-versions', '--filename-exceptions', str(root / '01_DATA/INPUT_MAPPING/filename-exceptions.json'),
         '--structure-vlm', 'on', '--pdf-conversion', 'on']),
        ('PREPARE', pipeline + ['document-release', 'prepare', '--run-id', run,
         '--glossary-dir', str(glossary), '--glossary-corpus-policy', 'replace']),
        ('INDEX', pipeline + ['document-release', 'reindex', '--from-run-id', run,
         '--run-id', run+'-index', '--fulltext-workers', '1']),
        ('RETURN', [sys.executable, '-B', str(root / 'worker.py'), '--export', str(root), run])]

def export_result(workspace, run):
    sys.path.insert(0, str(workspace / '02_BACKEND'))
    from lawrag.pipeline import oracle_full_package as full, oracle_query_package as query
    generation = workspace / '01_DATA/TERM_RELEASES' / (run+'-index') / 'serving/baseline/generation'
    release = t.read(generation.parents[1] / 'release.json')
    if not release.get('completed') or not release.get('serving_verified') or release.get('offline_e2e') != 'PASS':
        raise ValueError('PIPELINE_NOT_VERIFIED')
    output = workspace.parent
    # Heavy SQL projection runs here in GENOS; Dataiku only imports verified rows.
    query.export(generation, output / 'query', seconds=21600, direct_parts=True)
    _, paths, inventory = full.inventory(generation)
    paths['query/query-data.db'] = output / 'query/query-data.db'
    paths['audit/release.json'] = generation.parents[1] / 'release.json'
    paths['audit/input-raw.json'] = output / 'input-raw.json'
    paths['audit/input-support.json'] = output / 'input-support.json'
    for p in t.files(workspace / '01_DATA/LOGS'):
        paths['audit/pipeline-logs/' + str(p.relative_to(workspace / '01_DATA/LOGS'))] = p
    evidence, review_summary = review_audit.inventory(workspace)
    paths.update(evidence)
    t.write(output/'review-summary.json', review_summary)
    paths['audit/review-summary.json'] = output/'review-summary.json'
    t.pack(paths, output / 'result.zip', metadata={'inventory': inventory,
           'code_sha256': t.sha(workspace / 'CODE_PINS.json'), 'pipeline': 'native-existing-genos-review',
           'quality_certified': False, 'active_changed': False, **review_summary})

def compute(folder, run, archives, parser_sha):
    root=Path(__file__).resolve().parent
    pins=verify_code(root)
    parser_config.require(root, parser_sha)
    print('POD_RUNTIME_CONFIG_OK: document/model execution not yet checked', flush=True)
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
    env['GENOS_PREPROCESSOR_TRANSPORT'] = 'pod'
    env['GENOS_PDF_PARSER'] = 'preprocessor'
    env['GENOS_PREPROCESSOR_RESPONSE_MODE'] = 'docling'
    env.setdefault('LLM_BACKEND', 'genos')
    env['STRUCTURE_RECIPE_VLM'] = 'on'
    for phase,command in stage_commands(workspace,run):
        print('PHASE '+phase,flush=True)
        # Same process group as this worker: one cancellation terminates the full tree.
        subprocess.run(command,cwd=workspace,env=env,check=True)
    verify_code(root)


if __name__=='__main__':
    import json
    if len(sys.argv)==4 and sys.argv[1]=='--export':
        export_result(Path(sys.argv[2]),sys.argv[3])
    elif len(sys.argv)==6 and sys.argv[1]=='--compute':
        compute(Path(sys.argv[2]),sys.argv[3],json.loads(sys.argv[4]),sys.argv[5])
    else:
        raise SystemExit('COMPUTE_ENTRY_REQUIRED')
