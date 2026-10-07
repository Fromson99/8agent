"""Execute the TXT's configuration and failure paths without GENOS calls."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TXT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_FULL_PIPELINE_BACKUP_E2E_R3.txt'


def run_config(tmp_path, extra=None, after=''):
    source = TXT.read_text()
    header = source.split('DEPLOY_ROOT=', 1)[0]
    config = source.split('# Use the existing parser service', 1)[1].split('stage union_verification', 1)[0]
    script = header + '\n# Use the existing parser service' + config + '\n' + after
    env = {k: v for k, v in os.environ.items() if not k.startswith('GENOS_')}
    env.update(GENOS_PREPROCESSOR_ID='187', GENOS_PREPROCESSOR_SHARED_ROOT=str(tmp_path))
    env.update(extra or {})
    return subprocess.run(['bash', '-c', script], cwd=ROOT, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def test_existing_parser_configuration_is_sufficient(tmp_path):
    result = run_config(tmp_path, {'GENOS_PREPROCESSOR_API_KEY': 'secret-fixture'},
                        '[[ "$GENOS_PDF_CONVERTER_ID" == 187 ]]\n'
                        '[[ "$GENOS_PDF_CONVERTER_SHARED_ROOT" == "$GENOS_PREPROCESSOR_SHARED_ROOT" ]]\n'
                        '[[ "$GENOS_PDF_CONVERTER_API_KEY" == "$GENOS_PREPROCESSOR_API_KEY" ]]')
    assert result.returncode == 0, result.stdout
    assert 'PREPROCESSOR_CONFIG_VALID' in result.stdout
    assert 'secret-fixture' not in result.stdout
    assert 'KST]' in result.stdout and 'elapsed_seconds=' in result.stdout


def test_explicit_converter_is_preserved(tmp_path):
    result = run_config(tmp_path, {'GENOS_PDF_CONVERTER_ID': '999',
                                  'GENOS_PDF_CONVERTER_SHARED_ROOT': str(tmp_path)},
                        '[[ "$GENOS_PDF_CONVERTER_ID" == 999 ]]')
    assert result.returncode == 0, result.stdout


def test_separate_service_requires_its_mount(tmp_path):
    result = run_config(tmp_path, {'GENOS_PDF_CONVERTER_ID': '999'})
    assert result.returncode == 2
    assert 'separate converter selected' in result.stdout
    assert 'FAILED stage=preflight exit_code=2' in result.stdout


def test_parser_only_url_does_not_become_converter_endpoint(tmp_path):
    result = run_config(tmp_path, {'GENOS_PREPROCESSOR_URL': 'http://preprocessor-187:8080/parser'})
    assert result.returncode != 0
    assert '/parser is parsing-only' in result.stdout


def test_failure_has_stage_line_and_original_exit_code(tmp_path):
    result = run_config(tmp_path, after='stage structure\n(exit 17)')
    assert result.returncode == 17
    assert 'FAILED stage=structure exit_code=17 line=' in result.stdout
    assert 'line=unknown' not in result.stdout
    assert 'FINISHED status=17 stage=structure' in result.stdout
