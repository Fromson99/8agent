"""Freeze a single public multi-document question before model observations."""
from common import *
from copy import deepcopy
import sqlite3, shutil

DES.mkdir(parents=True, exist_ok=True)
pointer_path = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
pointer = read(pointer_path)
release_path = ROOT / pointer['manifest_path']
assert sha(release_path) == pointer['release_manifest_sha256']
release = read(release_path)
assert pointer['generation'] == 134
data = ROOT / release['data_path']
manifest = read(data / 'manifest.json')
assert sha(data / 'manifest.json') == release['data_manifest_sha256']
documents = ['2a410c9dfc65dac1', '5be4de51a89dc664', '7bbe815ff43b6635', '92aac373f5bd944b']
connection = sqlite3.connect((data / 'store.sqlite').as_uri() + '?mode=ro', uri=True)
metadata = []
for did in documents:
    doc = json.loads(connection.execute('SELECT json FROM document WHERE document_id=?', (did,)).fetchone()[0])
    meta = doc['document_metadata']
    assert meta['source_category'] == 'external' and meta['raw_role'] == 'body'
    metadata.append({'document_id': did, 'title': meta['document_title'], 'source_category': meta['source_category'],
                     'source_artifact_sha256': doc.get('source_artifact_sha256')})
connection.close()
question = '상장회사가 자기주식을 직접 취득하거나 신탁계약으로 취득할 때, 취득 방법·한도와 결정 절차는 어떻게 달라지나요? 상법의 일반규정, 자본시장법의 특례, 시행령의 세부조건을 연결해서 설명하고, 서로 다른 조항의 적용 관계가 불명확하면 구분해 주세요.'
case = {'id': 'complex-public-law-001', 'question': question,
        'document_ids': documents, 'selection': 'Public body documents by title; no target clause IDs or reference answer in model request',
        'request': {'question': question, 'document_ids': documents, 'team_id': 'risk_team',
                    'public_question': True, 'use_llm': True, 'session_id': 'adr1300-complex-law', 'request_id': 'initial'}}
criteria = {
 'hypothesis': 'Existing navigation can connect a listed-company own-share question across public law, special rule, delegated decree and definitions; GENOS final display can preserve these sources behind disclosures without repeating fallback originals in prose.',
 'success': ['One actual native API request completes with source-bound claims and explicit rule/condition links across at least three public documents',
             'Actual navigation receipts and full model input identify which links were offered, followed, read and used; merely present graph edges do not count as model use',
             'Citation text, scope, edition and source hashes match saved originals; no private/internal document transmission',
             'GENOS workflow run returns source disclosures through actual dict and socket paths, with original text preserved and collapsed by default',
             'Source-only fallback, if reached, remains INCOMPLETE with zero final claims; disclose originals once and preserve full original response privately',
             'Duplicate API request adds no model calls; no changes to MAIN, dataset or field deployment'],
 'failure': 'Any timeout/UNKNOWN ends model work. No terminal rerun, schema weakening, invented links or silently accepted failed review. A source-only result is a semantic failure, even when UI tests pass.',
 'limits': {'physical_calls_total': 20, 'per_turn_seconds': 1800, 'per_model_seconds': 180, 'rss_GiB': 4,
            'minimum_start_available_GiB': 5, 'minimum_available_GiB': 3, 'max_swap_growth_MiB': 128, 'minimum_workspace_free_GiB': 20},
 'scope': 'One in-sample prospectively fixed case, no causal A/B, no external judge, no legal-quality/generalization claim; only local corpus edition is tested.',
 'concurrency': 'One heavy model/data process at a time; wait until existing ADR1298 run_all is complete.',
 'display_scope': 'GENOS server/workflow output contract, not a separate conversation visualization. Actual field frontend sanitization/click needs field execution; current session cannot access GENOS.',
}
put(DES/'baseline.json', {'pointer': pointer, 'pointer_sha256': sha(pointer_path), 'release': release})
put(DES/'source.json', {'data_path': release['data_path'], 'source_manifest': manifest, 'document_ids': documents, 'documents': metadata})
put(DES/'cases.json', [case])
put(DES/'criteria.json', criteria)
put(DES/'authorization.json', {'user_instruction': '로컬데이터에서 연결관계 복잡한걸 한번 실험해봐 내규 데이터 없어 그리고 펼쳐지는건 genos에서 동작해야해',
    'public_only': True, 'document_ids': documents, 'question': question, 'model': 'qwen/qwen3.8-27b', 'physical_limit': 20})
put(ART/'preparation-notes.json', {'before_model_failures': ['First reservation command used nonexistent parent arm integrated; rejected before any claim/write. Correct completed parent arm verified used.',
    'Read-only navigation inspection attempted nonexistent heading/source_id SQL columns; failed SELECT only. Correct JSON/view schema inspected before use.'],
    'prior_demo': '09_ARTIFACTS/AUDITS/20261103-connected-source-demonstration', 'prior_demo_is_not_this_experiment': True})
m = read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta'] = criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='One source-grounded cross-document answer and GENOS disclosure fidelity',
    success_criteria=criteria['success'], failure_criteria=[criteria['failure']], criteria_frozen_before_run=True,
    criteria_freeze_evidence={'path': str((DES/'criteria.json').relative_to(ROOT)), 'sha256': sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed MAIN134 technical implementation, historical baseline only', controls='No historical answer comparison')
m['design']['arms'][1].update(changes='Same MAIN134 agent/model contracts on actual public corpus, GENOS display correction only', controls='No model prompt/retrieval change, no ontology publication, one frozen question')
m['runs'][0].update(arm_ids=['verified'], artifact_path=str((ART/'live/result.json').relative_to(ROOT)), selection_rule='One fixed public complex question once; no adaptive repeats')
m['dataset'].update(name='Local public own-share multi-document connection probe', version='20261103-v1',
    frozen_source=str((DES/'cases.json').relative_to(ROOT)), sha256=sha(DES/'cases.json'), legal_version_checked=False, reference_version_checked=False)
m['llm_policy']['llm_calls'] = [{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
# Navigation is unchanged, but actual stage accounting will be collected.
m['retrieval_accounting']['changed'] = False
put(ADR/'실험/manifest.json', m)
parent = read(ROOT/'04_EXPERIMENTS/ADR/ADR-1292-rag-ontology-console-integration/artifacts/design/freeze.json')
sources = set(parent['files'])
assert all(sha(ROOT/n) == h for n,h in parent['files'].items()), 'Working drift requires a new explicit baseline review'
sys.path.insert(0, str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
snapshot = ac.snapshot(ADR, 'verified', sorted(sources), experiment_id=m['experiment_id'], arm_id='verified', run_ids=['run-001'])/'snapshot'
put(DES/'candidate-path.json', {'snapshot': str(snapshot.relative_to(ROOT))})
put(DES/'working-before.json', {n: sha(ROOT/n) for n in sorted(sources)})
for name, donor in [('pinned_imports.py','adr_1297'),('resource_guard.py','adr_1297'),('authorization.py','adr_1298')]:
    shutil.copyfile(ROOT/f'06_TOOLS/EXPERIMENTS/{donor}/{name}', Path(__file__).parent/name)
print('Prepared candidate', len(sources), 'files; four public documents; no model call')
