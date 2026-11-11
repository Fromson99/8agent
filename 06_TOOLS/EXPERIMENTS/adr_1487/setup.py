"""Freeze ADR-1487 before any model call: baseline = MAIN202 release code (progress-report-20261111-r1),
candidate = MAIN203 release code (fts-search-units-20261111-r1, body search as model search groups),
the photo-rule test generation and the four 내규 questions of ADR-1486, same limits."""
from common import *
import shutil
DES.mkdir(parents=True, exist_ok=False)
ptr = read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'); assert ptr['generation'] == 203 and ptr['release_id'] == 'fts-search-units-20261111-r1'
cand = read(ROOT/ptr['manifest_path']); base = read(ROOT/'08_DEPLOYMENT/RELEASES/progress-report-20261111-r1/release.json')
for rel in (cand, base):
    assert all(sha(ROOT/rel['code_root']/n) == h for n, h in rel['files'].items())
product = sorted(n for n in cand['files'] if n.endswith('.py') and n.startswith('02_BACKEND') and cand['files'][n] != base['files'].get(n))
assert product == sorted(['02_BACKEND/semantic_runtime/fulltext.py', '02_BACKEND/semantic_runtime/oracle_query_fulltext.py',
    '02_BACKEND/semantic_runtime/legal_agent/law_candidates.py', '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py',
    '02_BACKEND/semantic_runtime/legal_agent/unit_selection.py', '02_BACKEND/semantic_runtime/oracle_query_plans.py']), product  # plans: derived
PREV = ROOT/'04_EXPERIMENTS/ADR/ADR-1486-linked-documents-staged-picks-qwen/artifacts/design'
GEN = ROOT/'01_DATA/TERM_RELEASES/linked-documents-20261111-r1/generation'
manifest = read(GEN/'manifest.json'); assert sha(GEN/'store.sqlite') == manifest['store_sha256']
cases = read(PREV/'live-cases.json'); grades = read(PREV/'grading-only.json')
criteria = {
    'authorization': 'User 2026-11-11: "1에서 3번하고 메인반영후 삼성메일 보내고 이후에 몇개 질문 실험해봐 qwen으로"; photo rules external use per EXPORT_AUTHORIZATION_PHOTO_RULES_20261111.json',
    'scope': 'Same four 내규 questions and six-document photo-rule generation as ADR-1486. One run per arm, baseline (MAIN202) before candidate (MAIN203). Same data, profile, model, transport. Local SQLite: the candidate applies search groups; the Oracle-only exact-text check is not exercised.',
    'required': ['Arm code bytes unchanged; every loaded semantic_runtime module from the arm tree',
                 'Primary: target articles of ADR-1486 acquired per question (no regression vs baseline)',
                 'Mechanism: candidate LAW_FULLTEXT_DIRECTORY terms are groups (one per model query); baseline single morphemes',
                 'Answer read by hand against the stored original',
                 'Source/ACL integrity, physical calls recorded'],
    'limits': {'physical_total': 120, 'per_request': 40, 'per_physical_seconds': 180, 'reported_cost_usd': 1.0, 'time_box_minutes': 40, 'workers': 1},
    'stop': 'UNKNOWN ends that request without retry; three consecutive UNKNOWN, source/ACL/code/resource violation, budget or time box stop the batch.',
    'quality_certified': False, 'in_sample': True,
    'note': 'One run per arm; a difference is an observation, not a rate. Search speed on Oracle is measured separately (field SQL R2).'}
put(DES/'criteria.json', criteria); put(DES/'grading-only.json', grades); put(DES/'live-cases.json', cases)
put(DES/'provider-policy.json', read(ROOT/cand['code_root']/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
shutil.copyfile(PREV/'authorization.json', DES/'authorization.json')
put(DES/'generation.json', {'path': str(GEN.relative_to(ROOT)), 'manifest_sha256': sha(GEN/'manifest.json'), 'manifest': manifest})
transport = ART/'transport'; transport.mkdir()
pins = read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
    t = transport/name; t.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name, t); pins['files'][name] = sha(t)
put(transport/'transport-pins.json', pins)
arms = {'baseline': {'code_root': base['code_root'], 'files': base['files'], 'label': 'progress-report-20261111-r1 (MAIN202)'},
        'candidate': {'code_root': cand['code_root'], 'files': cand['files'], 'label': 'fts-search-units-20261111-r1 (MAIN203)'}}
put(DES/'arms.json', arms)
paths = [*Path(__file__).parent.glob('*.py'), *(DES/x for x in ('criteria.json', 'live-cases.json', 'authorization.json', 'provider-policy.json', 'arms.json', 'grading-only.json', 'generation.json'))]
put(DES/'freeze-live.json', {'files': {str(p.relative_to(ROOT)): sha(p) for p in paths}, 'selected_pointer': ptr, 'model_calls_before_freeze': 0,
    'isolation_note': 'Both arms are selected release code roots, hash-pinned file by file; not modified during the run (checked per request).'})
print('Frozen MAIN202 baseline + MAIN203 candidate, 4 questions x 2 arms; model 0')
