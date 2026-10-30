import os
import json
import time
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import sys
import transport as t
import parser_config
import review_audit
import partial_pipeline
import pipeline_coverage

@contextmanager
def phase_timing(phase):
    started=time.monotonic();status='FAILED'
    try:
        yield
        status='COMPLETE'
    finally:
        print('PHASE_RESULT '+json.dumps({'phase':phase,'status':status,
              'seconds':round(time.monotonic()-started,3)}),flush=True)

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
    selected=run+'-selected'
    return [
        ('STRUCTURE', pipeline + ['build-data-stages', '--run-id', run, '--stage', 'structure', '--execute',
         '--latest-internal-versions', '--filename-exceptions', str(root / '01_DATA/INPUT_MAPPING/filename-exceptions.json'),
         '--structure-vlm', 'off', '--pdf-conversion', 'off']),
        ('PREPARE', pipeline + ['document-release', 'prepare', '--run-id', selected,
         '--glossary-dir', str(glossary), '--glossary-corpus-policy', 'replace']),
        ('INDEX', pipeline + ['document-release', 'reindex', '--from-run-id', selected,
         '--run-id', selected+'-index', '--fulltext-workers', '1']),
        ('RETURN', [sys.executable, '-B', str(root / 'worker.py'), '--export', str(root), selected])]

def export_result(workspace, run):
    sys.path.insert(0, str(workspace / '02_BACKEND'))
    from lawrag.pipeline import oracle_full_package as full, oracle_query_package as query
    generation = workspace / '01_DATA/TERM_RELEASES' / (run+'-index') / 'serving/baseline/generation'
    release = t.read(generation.parents[1] / 'release.json')
    if not release.get('completed') or not release.get('serving_verified') or release.get('offline_e2e') != 'PASS':
        raise ValueError('PIPELINE_NOT_VERIFIED')
    output = workspace.parent
    coverage=pipeline_coverage.validate(t.read(output/'pipeline-coverage.json'))
    partial_pipeline.verify_generation(generation,coverage)
    # Heavy SQL projection runs here in GENOS; Dataiku only imports verified rows.
    query.export(generation, output / 'query', seconds=21600, database_only=True)
    _, paths, inventory = full.inventory(generation)
    paths['query/query-data.db'] = output / 'query/query-data.db'
    paths['audit/release.json'] = generation.parents[1] / 'release.json'
    paths['audit/input-raw.json'] = output / 'input-raw.json'
    paths['audit/input-support.json'] = output / 'input-support.json'
    for p in t.files(workspace / '01_DATA/LOGS'):
        paths['audit/pipeline-logs/' + str(p.relative_to(workspace / '01_DATA/LOGS'))] = p
    evidence, review_summary = review_audit.inventory(workspace)
    paths.update(evidence)
    paths.update(partial_pipeline.export_paths(output))
    t.write(output/'review-summary.json', review_summary)
    paths['audit/review-summary.json'] = output/'review-summary.json'
    t.pack(paths, output / 'result.zip', metadata={'inventory': inventory,
           'code_sha256': t.sha(workspace / 'CODE_PINS.json'), 'pipeline': 'native-only-preprocessor-bypassed',
           'quality_certified': False, 'active_changed': False, 'coverage':pipeline_coverage.summary(coverage), **review_summary})

def compute(folder, run, archives, parser_sha):
    root=Path(__file__).resolve().parent
    pins=verify_code(root)
    parser_config.require(root, parser_sha)
    print('PIPELINE_CONFIG_OK: mode='+parser_config.environment()[0]+'; document/model execution not yet checked', flush=True)
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
    env.update(parser_config.environment()[1])
    env.setdefault('LLM_BACKEND', 'genos')
    env['STRUCTURE_RECIPE_VLM'] = 'off'
    for phase,command in stage_commands(workspace,run):
        with phase_timing(phase):
            print('PHASE '+phase,flush=True)
            # Same process group as this worker: one cancellation terminates the full tree.
            if phase=='STRUCTURE':
                result=subprocess.run(command,cwd=workspace,env=env,check=False)
                if result.returncode not in (0,2):result.check_returncode()
                print('PHASE SELECT_VERIFIED_SUCCESSES',flush=True)
                subprocess.run([sys.executable,'-B',str(workspace/'worker.py'),'--select',str(workspace),run,str(result.returncode)],cwd=workspace,env=env,check=True)
            else:
                subprocess.run(command,cwd=workspace,env=env,check=True)
    verify_code(root)


if __name__=='__main__':
    import json
    if len(sys.argv)==4 and sys.argv[1]=='--export':
        export_result(Path(sys.argv[2]),sys.argv[3])
    elif len(sys.argv)==5 and sys.argv[1]=='--select':
        partial_pipeline.select(Path(sys.argv[2]),sys.argv[3],int(sys.argv[4]))
    elif len(sys.argv)==6 and sys.argv[1]=='--compute':
        compute(Path(sys.argv[2]),sys.argv[3],json.loads(sys.argv[4]),sys.argv[5])
    else:
        raise SystemExit('COMPUTE_ENTRY_REQUIRED')
