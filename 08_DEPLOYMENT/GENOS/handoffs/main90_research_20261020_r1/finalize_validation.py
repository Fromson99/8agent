from pathlib import Path
import hashlib, json

H = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
passes = [json.loads((H / ('PASS_' + mode + '.json')).read_text())
          for mode in ('preserved-config-interruption', 'no-config-standalone')]
assert all(v['status'] == 'PASS' for v in passes)
log = (H / 'CONTRACT_TESTS_02.txt').read_text()
assert '87 passed' in log and 'INSTALLED_CONTRACT_IMPORTS PASS' in log
assert '2 passed' in (H / 'DELIVERY_TESTS_01.txt').read_text()
python = json.loads((H / 'PYTHON311.json').read_text())
assert python['status'] == 'PASS' and python['code_zip_sha256'] == sha(H / 'code.zip')
binding = json.loads((H / 'SOURCE_BINDING.json').read_text())
value = {
    'status': 'LOCAL_DELIVERY_VERIFIED_FIELD_PENDING',
    'version': 'GENOS_MAIN90_RESEARCH_20261020_R1',
    'base': binding['base_package'],
    'code_zip_sha256': sha(H / 'code.zip'),
    'local_main_release_manifest_sha256': binding['local_main_release_manifest_sha256'],
    'changes': {'with_manifests_and_pins': len(binding['changes']),
                'unchanged': binding['unchanged_files'],
                'exact_main_files': len(binding['exact_main_files']),
                'pipeline_exception': 'Only Oracle guide reference points to the included field guide; executable code and engine/profile pins match MAIN90.'},
    'contract_tests': {
        'passed': 87, 'product_imports_from_packaged_code': 230,
        'coverage': 'durable investigation needs, research priorities, evidence update wire contracts, RP connected-document registration, actual API wiring and existing display contracts',
        'fixture': 'synthetic documents and scripted models; no network/model calls',
        'log': 'CONTRACT_TESTS_02.txt', 'resource_receipt': 'CONTRACT_RESOURCES_02.json',
        'first_attempt': {'passed': 84, 'failed': 3, 'log': 'CONTRACT_TESTS_01.txt',
                          'cause': 'pytest importlib mode loaded shared synthetic transport fixtures under different module identities',
                          'resolution': 'Use prepend mode matching the source MAIN runner; product bytes unchanged.'}},
    'main_source_verification': {
        'stage_contracts_passed': 87, 'working_contracts_passed': 87, 'actual_local_service_checks': 12,
        'receipt': '09_ARTIFACTS/AUDITS/20261020-durable-research-main/RESULT.json'},
    'delivery_tests': {
        'passed': 2, 'scenarios': passes, 'commands': sum(v['commands'] for v in passes),
        'coverage': 'actual uploaded TRANSFER ZIP/TXT, existing Git checkout, symlink resolution, interrupted apply recovery, idempotence, same committed checkout code gate, tamper refusal, exact rollback and preservation of user data/configuration',
        'resource_receipt': 'DELIVERY_RESOURCES_01.json'},
    'python311': python,
    'source_pointer_sha256': sha(H / 'SOURCE_POINTER.json'),
    'selected_local_main_changed_by_packaging': False,
    'quality_certified': False,
    'cutover': 'USER_DIRECTED_CUTOVER',
    'known_legal_limitations': 'Prior four-question ADR0936: RP article 5-18 and enforcement-decree article 181 were not acquired; leverage article 3-26 paragraph 7 was absent from current direct citations. These are not fixed or recertified by packaging tests.',
    'field': {'checkout': 'existing DEV; earlier field physical root /workspace',
              'commit': None, 'generation_path': None, 'generation_manifest_sha256': None,
              'oracle_query_release': None, 'codeserving_revision': None,
              'workflow_editor_saved': False, 'verified': False},
    'remaining': ['GENOS code import/commit/push/revision deployment',
                  'verify workflow editor (included bytes equal previous WORKFLOW_PROGRESS R1)',
                  'same four questions in workflow test UI using internal model and actual Oracle/NFS'],
    'file_sha256': {n: sha(H / n) for n in [
        'CODE_MANIFEST.json', 'SOURCE_BINDING.json', 'PACKAGE_SPEC.json', 'run.py',
        'replace.py', 'code_smoke.py', 'CONTRACT_TESTS_01.txt', 'CONTRACT_TESTS_02.txt',
        'DELIVERY_TESTS_01.txt']},
}
(H / 'VALIDATION.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': value['status'], 'contract_tests': 87, 'installation_commands': value['delivery_tests']['commands']}))
