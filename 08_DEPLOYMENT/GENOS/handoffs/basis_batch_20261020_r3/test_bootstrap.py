"""Actual ZIP/TXT -> pipeline CLI -> service bootstrap; no application injection."""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import os
import subprocess
import zipfile

from test_risk_team_compare_workflow import generation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_BASIS_BATCH_20261020_R3'
TRACE = []


def test_real_uploaded_list_plan_and_inherited_configuration(tmp_path, generation):
    from lawrag.pipeline.fulltext_stage import derive
    from lawrag.pipeline.search_selection import plan, activate
    selected = tmp_path / 'native-generation'
    derive(generation, selected, workers=1)
    activate(plan(selected, latest=True))
    transfer = tmp_path / 'actual-transfer'; transfer.mkdir()
    checkout = tmp_path / 'physical-checkout'; checkout.mkdir()
    home = tmp_path / 'home'; home.mkdir()
    (home / 'DEV').symlink_to(checkout, target_is_directory=True)
    with zipfile.ZipFile(ROOT / '08_DEPLOYMENT/GENOS/handoffs/main92_cumulative_20261020_r1/code.zip') as archive:
        archive.extractall(checkout)
    runtime = tmp_path / 'runtime'
    config = {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed',
              'generation': str(selected), 'runtime': str(runtime),
              'generation_manifest_sha256': hashlib.sha256((selected / 'manifest.json').read_bytes()).hexdigest()}
    config_path = checkout / '00_SYSTEM/GENOS_SERVING_PATHS.json'
    config_path.write_text(json.dumps(config))
    config_before = config_path.read_bytes()
    data_before = {p.relative_to(selected).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in selected.rglob('*') if p.is_file()}
    # Isolate endpoint secrets; no monkeypatches or synthetic application in child.
    env = {k:v for k,v in os.environ.items()
           if not k.startswith(('GENOS_', 'SEMANTIC_', 'LEGAL_AGENT_', 'PYTHON',
                                'LAWRAG_', 'SOURCE_PROVIDER_', 'WORKFLOW_', 'TASK_TEST_'))}
    env.update(HOME=str(home), PATH=str(ROOT / '.venv/bin') + os.pathsep + os.environ['PATH'],
               PYTHONDONTWRITEBYTECODE='1', DP='oracle',
               GENOS_RAG_IMPLEMENTATION='"legal-agent-unified-v6"')

    def command(args, expected=0, *, override=None):
        completed = subprocess.run([str(a) for a in args], cwd=transfer,
            env={**env, **(override or {})}, capture_output=True, text=True, timeout=90)
        output = completed.stdout + completed.stderr
        TRACE.append({'args':[str(a) for a in args], 'exit':completed.returncode,
                      'expected':expected, 'output':output})
        with gzip.open(HERE / 'BOOTSTRAP_TRACE.json.gz', 'wt') as stream:
            json.dump(TRACE, stream, ensure_ascii=False)
        assert (completed.returncode == 0) == (expected == 0), output[-16000:]
        return output

    command(['git', 'init', '-q', checkout])
    package = transfer / NAME
    command(['python3', '-m', 'zipfile', '-e', HERE / (NAME + '.zip'), package])
    script = package / (NAME + '_RUN.txt')
    old_name = 'GENOS_BASIS_BATCH_20261020_R2'
    old = transfer / old_name
    command(['python3', '-m', 'zipfile', '-e',
             HERE.with_name('basis_batch_20261020_r2') / (old_name + '.zip'), old])
    command(['bash', old / (old_name + '_RUN.txt'), 'apply'])
    command(['bash', script, 'gate'])
    assert not (package / 'INSTALL_STATE.json').exists()
    failure = command(['bash', old / (old_name + '_RUN.txt'), 'list',
                       '--job', runtime / 'failed-r2'], expected=1)
    assert 'unsupported GENOS_RAG_IMPLEMENTATION' in failure
    assert not (runtime / 'failed-r2' / 'PLAN.json').exists()
    for value in ('"legal-agent-unified-v6"', 'retired-implementation-v0', '',
                  'legal-agent-unified-v6'):
        output = command(['bash', script, 'list'],
                         override={'GENOS_RAG_IMPLEMENTATION':value})
        assert '"event": "BATCH_RAG_BINDING"' in output
        assert '"implementation": "legal-agent-unified-v6"' in output
        assert 'basis.batch.latest_internal' in output
    command(['bash', script, 'plan', '--count', '3'])
    job = runtime / 'basis-batch/pilot-20261020-r1'
    saved = (job / 'PLAN.json').read_bytes()
    value = json.loads(saved)
    assert [row['document_id'] for row in value['documents']] == ['inside']
    assert value['binding']['generation_path'] == str(selected)
    with (job / 'LATEST_INTERNAL.csv').open(encoding='utf-8-sig') as stream:
        assert [row['document_id'] for row in csv.DictReader(stream)] == ['inside']
    status = command(['bash', script, 'status'])
    assert value['batch_id'] in status
    command(['bash', script, 'plan'], expected=1)
    assert (job / 'PLAN.json').read_bytes() == saved
    # Missing model must remain a failure; no fallback model/network calls.
    failed_run = command(['bash', script, 'run'], expected=1)
    assert 'GENOS 내부 모델' in failed_run or '내부 모델' in failed_run
    assert not (job / 'STATE.json').exists()
    assert not (runtime / 'basis-links/SQLITE_ENABLED.json').exists()
    assert config_path.read_bytes() == config_before
    assert env['GENOS_RAG_IMPLEMENTATION'] == '"legal-agent-unified-v6"'
    data_after = {p.relative_to(selected).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in selected.rglob('*') if p.is_file()}
    assert data_after == data_before
    record = {'status':'PASS', 'actual_shell_commands':len(TRACE),
              'app_injection':False, 'old_R2_error_reproduced':True,
              'list_plan_status_actual_entry':True, 'source_data_unchanged':True,
              'R2_already_applied_R3_gate_only':True,
              'existing_plan_preserved':True, 'unconfigured_model_still_rejected':True,
              'generation_fixture':'synthetic internal/external documents; local fulltext',
              'external_model_calls':0, 'GENOS_model_calls':0,
              'zip_sha256':hashlib.sha256((HERE / (NAME + '.zip')).read_bytes()).hexdigest()}
    (HERE / 'BOOTSTRAP_VALIDATION.json').write_text(json.dumps(record, indent=2) + '\n')
