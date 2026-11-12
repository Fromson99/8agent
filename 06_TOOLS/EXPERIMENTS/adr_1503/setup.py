"""Freeze ADR-1503 before any model call: candidate = selected MAIN212 special-external-20261111-r1 (MAIN211 + server-links-r2,
provider-reka, follow-optional-coords, compare-special-external, compare-outline-view, unit-rows-shared, document-tree-shared), test generation with 금융투자업규정·금융투자업규정시행세칙 (external) and
위험관리기준시행세칙 photo r2 (internal), one 대사 question. Internal rules sent under the user's 2026-11-11 authorization."""
from common import *
import shutil, sqlite3
DES.mkdir(parents=True, exist_ok=True)
assert not (DES / 'freeze.json').exists(), 'already frozen'
rel = lambda p: str(Path(p).relative_to(ROOT))
pointer = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'); assert pointer['release_id'] == 'special-external-20261111-r1', pointer
names = read(STAGED.parent / 'main-release.json') if (STAGED.parent / 'main-release.json').exists() else {}
release = read(BASELINE / 'release.json'); files = {n: sha(STAGED / n) for n in release['files']}
changed = sorted(n for n, h in files.items() if h != release['files'][n])
assert len(changed) == 44, changed
put(DES / 'candidate.json', {'code_root': rel(STAGED), 'files': files, 'changed_from_main211': changed,
                             'code_changes': ['server-links-r2', 'provider-reka', 'follow-optional-coords', 'compare-special-external', 'compare-manifest-docflow-r2', 'compare-manifest-basis-r2', 'compare-outline-view', 'unit-rows-shared', 'document-tree-shared'],
                             'regression': '163 files, 0 new failures (main_release test); MAIN212 selected', 'parent': 'ADR-1502 run-001 (same question, external 제3-24조의4 not reached)'})
shutil.copyfile(STAGED / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json', DES / 'provider-policy.json')
assert read(ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json') == read(DES / 'provider-policy.json')
pins = read(ROOT / '04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
    target = ART / 'transport' / name; target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target); pins['files'][name] = sha(target)
put(ART / 'transport/transport-pins.json', pins)
GEN = ROOT / '01_DATA/TERM_RELEASES/liquidity-compare-20261111-r1/generation'
manifest = read(GEN / 'manifest.json'); assert sha(GEN / 'store.sqlite') == manifest['store_sha256'] and manifest['export_allowed'] is False
docs = [{'document_id': d, 'name': n} for d, n in sqlite3.connect((GEN / 'store.sqlite').as_uri() + '?mode=ro', uri=True).execute('SELECT document_id,name FROM document')]
put(DES / 'comparison-source.json', {'data_path': rel(GEN), 'source_manifest': manifest, 'documents': docs, 'synthetic': False,
                                     'built_by': '09_ARTIFACTS/AUDITS/20261111-liquidity-compare/build.py'})
for name in ('scripted-source.json', 'scripted-case.json'):
    shutil.copyfile(PARENT / 'design' / name, DES / name)
question = '대사: 유동성비율 관련한 외부규정과 내부 규정은 어떻게 되나요?'
put(DES / 'case.json', {'id': 'liquidity-ratio', 'question': question, 'document_ids': sorted(d['document_id'] for d in docs), 'synthetic': False})
put(DES / 'grading-only.json', {'targets': [{'side': 'external', 'document': '금융투자업규정', 'article': '제3-24조의4'},
                                            {'side': 'internal', 'document': '위험관리기준시행세칙', 'article': '제6-4조'}],
                                'source': 'user message 2026-11-11 (not sent to the model)'})
put(DES / 'authorization.json', {'user_instruction': '내규 외부로 쏴도 됨 / 특례 예외 조문까지 가게 만들고 메인에 싹 반영하고 코드 검사만 하고 삼성메일로 쏴줘 그리고 실험해줘', 'workflow_id': 'risk_team_compare_workflow',
                                 'question': question, 'documents': docs, 'generation_id': manifest['generation_id'], 'store_sha256': manifest['store_sha256'],
                                 'record': rel(ROOT / '01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json')})
criteria = {'question': 'With the special/exception external read stage, does the 대사 reach 금융투자업규정 제3-24조의4 (and still 위험관리기준시행세칙 제6-4조)?',
            'primary_metric': 'Target articles in the comparison table (external 제3-24조의4, internal 제6-4조); special_external reads recorded',
            'limits': {'physical_total': 60, 'per_physical_seconds': 180, 'reported_cost_usd': 1.0, 'request_seconds': 900,
                       'ram_start_gib': 4, 'wait_seconds': 1800, 'swap_free_start_gib': 0},
            'stop': 'One request. An unknown provider outcome stops external sending, no re-send.', 'quality_certified': False, 'in_sample': True}
put(DES / 'criteria.json', criteria)
frozen = [*sorted(TOOLS.glob('*.py')), *(DES / n for n in ('candidate.json', 'provider-policy.json', 'comparison-source.json', 'scripted-source.json',
                                                         'case.json', 'scripted-case.json', 'authorization.json', 'criteria.json')),
          ART / 'transport/transport-pins.json', ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',
          ROOT / '05_TESTS/CONTRACTS/test_internal_concept_comparison.py']
put(DES / 'freeze.json', {'files': {rel(p): sha(p) for p in frozen}, 'model_calls_before_freeze': 0})
print('frozen', len(changed), 'changed from MAIN211 (MAIN212);', len(docs), 'documents')
