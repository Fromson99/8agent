"""Bind maintenance, paired probe and installation checks to the exact package."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile

H = Path(__file__).resolve().parent
R = H.parents[3]
M = R / '09_ARTIFACTS/AUDITS/20261020-main95-comparison-scope'
B = R / '09_ARTIFACTS/AUDITS/20261020-comparison-display-scope'
E = R / '04_EXPERIMENTS/ADR/ADR-0956-comparison-required-scope-retest'
read = lambda p: json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
def passed(path):
    suites = ET.parse(path).getroot().findall('testsuite')
    assert suites
    assert all(int(s.get('failures', 0)) == int(s.get('errors', 0)) ==
               int(s.get('skipped', 0)) == 0 for s in suites), path
    return sum(int(s.get('tests', 0)) for s in suites)

assert not (H / 'SEALED.json').exists()
pointer = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation'] == 95
manifest = read(R / pointer['manifest_path'])
assert sha(R / pointer['manifest_path']) == pointer['release_manifest_sha256']
frozen = read(M / 'frozen.json')
assert manifest['files'] == frozen['target_files']
with zipfile.ZipFile(H / 'code.zip') as z:
    for name, digest in manifest['files'].items():
        assert hashlib.sha256(z.read(name)).hexdigest() == digest
        for root in (R, R / manifest['code_root'], R / frozen['candidate_root'], H / 'test-code'):
            assert sha(root / name) == digest, (root, name)
consumer = read(M / 'consumer-active.json')
assert consumer['status'] == 'PASS' and not consumer['app_injected']
assert all(consumer['checks'].values())
local_tests = passed(B / 'checks.xml')
handoff_tests = passed(H / 'CONTRACT_TESTS_01.xml')
delivery_tests = passed(H / 'DELIVERY_TESTS_01.xml')
assert delivery_tests == 2
scenarios = [read(p) for p in sorted(H.glob('PASS_*.json'))]
assert len(scenarios) == 2 and all(s['status'] == 'PASS' for s in scenarios)
resources = {n: read(H / n) for n in ('CONTRACT_RESOURCES_01.json', 'DELIVERY_RESOURCES_01.json')}
assert all(x['returncode'] == 0 and x['stop_reason'] is None for x in resources.values())
experiment = read(E / 'artifacts/run-001/result.json')
assert experiment['scope_success'] and experiment['status'] == 'complete'
assert (E / 'FINAL_VALIDATION.txt').read_text().startswith('OK:')
imports = read(H / 'INSTALLED_MODULES.json') if (H / 'INSTALLED_MODULES.json').exists() else None
v = {
    'status': 'PASS', 'runtime_files': len(manifest['files']),
    'runtime_matches_working_frozen_selected_handoff': True,
    'local_MAIN': pointer, 'workflow': '1.20.2',
    'local_contracts_passed': local_tests, 'handoff_contracts': handoff_tests,
    'installation_scenarios': delivery_tests,
    'installation_commands': sum(s['commands'] for s in scenarios),
    'syntax': read(H / 'PYTHON311.json'),
    'syntax_note': 'Python 3.11 grammar parse plus compilation on the recorded local interpreter; no actual Python 3.11 or GENOS execution claim.',
    'local_actual_service': consumer, 'code_zip_sha256': sha(H / 'code.zip'),
    'experiment': {'path': str(E.relative_to(R)), 'result_sha256': sha(E / 'artifacts/run-001/result.json'),
                   'new_model_calls': experiment['model_calls'], 'by_arm': experiment['by_arm'],
                   'scope_success': True, 'all_product_answers_partial': True},
    'source_kind': 'Synthetic paired external-model scope probe, contracts, real local source-only ingress',
    'GENOS_field_verified': False, 'quality_certified': False,
    'data_profile_search_unchanged': True,
    'limits': [
        'No GENOS deployment, internal model, Oracle or NFS field execution.',
        'Approved-link scope and stricter-internal false-CONFLICT findings remain.',
        'Unnecessary/stale unresolved prose remains; all 8 live probe answers are partial.',
        'Control repair failures contribute to call counts; single paired run is not an isolated causal or general performance estimate.',
        'Six older general RAG test failures recorded by MAIN94 and reproduced on MAIN93 remain unresolved; not rerun or certified fixed here.',
        'Global ADR graph retains 9 unrelated historical errors; ADR0956 final validation passes.',
        'Old code-bound runs require their original revision; no forced resume.'
    ],
    'resources': resources
}
(H / 'VALIDATION.json').write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v[k] for k in ('status', 'runtime_files', 'local_contracts_passed',
                                    'handoff_contracts', 'installation_scenarios', 'installation_commands')}))
