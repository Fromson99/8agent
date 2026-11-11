"""Freeze ADR-1483 before any model call: baseline = selected MAIN194 release code, candidate =
MAIN194 + linked_documents (main_release stage), the photo-rule test generation, three questions,
grading targets, limits and the user's scoped export authorization."""
from common import *
import shutil
DES.mkdir(parents=True, exist_ok=False)
ptr = read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'); assert ptr['generation'] == 196 and ptr['release_id'] == 'lean-records-20261111-r1'
rel = read(ROOT/ptr['manifest_path']); B = ROOT/rel['code_root']; base_files = rel['files']
assert all(sha(B/n) == h for n, h in base_files.items())
audit = ROOT/'09_ARTIFACTS/AUDITS/20261111-linked-documents'; mr = read(audit/'release-r5/main-release.json')
stage = mr['stage']; assert stage['status'] == 'PASSED' and stage['base_release_id'] == ptr['release_id']
S = ROOT/stage['code_root']; cand_files = stage['files']; assert all(sha(S/n) == h for n, h in cand_files.items())
product = sorted(n for n in cand_files if n.endswith('.py') and cand_files[n] != base_files.get(n))
assert set(product) - {'02_BACKEND/semantic_runtime/oracle_query_plans.py'} == {'02_BACKEND/semantic_runtime/legal_agent/guided_answer.py', '02_BACKEND/semantic_runtime/legal_agent/guided_navigation.py', '02_BACKEND/semantic_runtime/legal_agent/linked_documents.py', '02_BACKEND/semantic_runtime/legal_agent/repository.py'}, product
GEN = ROOT/'01_DATA/TERM_RELEASES/linked-documents-20261111-r1/generation'
manifest = read(GEN/'manifest.json'); assert sha(GEN/'store.sqlite') == manifest['store_sha256']
import sqlite3
docs = {d: n for d, n in sqlite3.connect((GEN/'store.sqlite').as_uri()+'?mode=ro', uri=True).execute('SELECT document_id,name FROM document')}
by = lambda word: next(d for d, n in docs.items() if n.endswith(' > '+word) or n.endswith('> '+word))
target = {'guide': by('상품위원회운영지침'), 'product': by('상품관리준칙'), 'detail': by('위험관리기준시행세칙')}
CASES = [
    ('q1-field', '신규 상품을 판단하는 기준과 프로세스, 상품 관련 전결권은 어떻게 되나요?',
     [{'document': 'product', 'article': '제2-1조'}, {'document': 'product', 'article': '제2-2조'}]),
    ('q2-new-product', '상품위원회 운영지침에서 말하는 신상품은 어떤 기준으로 정해지나요?',
     [{'document': 'product', 'article': '제2-1조'}]),
    ('q3-terms', '상품위원회 운영지침에 정의되지 않은 용어는 어디에서 정하나요?',
     [{'document': 'detail', 'article': '제1-4조'}]),
]
criteria = {
    'authorization': 'User 2026-11-11: "사진 내규는 외부전송해도 되고 … 내규도 검색했을때 연결관계 타고가서 원하는 조문까지 들고오는거야 … 구현해봐"; record 01_DATA/RAW/internal/risk_team/EXPORT_AUTHORIZATION_PHOTO_RULES_20261111.json',
    'scope': 'Three questions in 내규 mode over the six-document photo-rule test generation (4 photo transcriptions incl. partial 상품관리준칙 + 2 labelled mock 준칙). One run per arm, baseline (MAIN194 code) before candidate (MAIN194 + linked_documents). Same data, profile, model, transport.',
    'required': ['Arm code bytes unchanged; every loaded semantic_runtime module from the arm tree',
                 'Primary: target article of the rule the guideline hands over (상품관리준칙 제2-1조 / 위험관리기준시행세칙) acquired per question',
                 'Mechanism: candidate records DELEGATED_DOCUMENTS_RESOLVED and reads the location as a server read; baseline has no such event',
                 'Answer read by hand against the stored original; a question back to the user about which rule is meant counts as not reached',
                 'Source/ACL integrity, physical calls recorded, duplicate request adds 0 calls'],
    'limits': {'physical_total': 120, 'per_request': 40, 'per_physical_seconds': 180, 'reported_cost_usd': 1.0, 'time_box_minutes': 40, 'workers': 1},
    'stop': 'UNKNOWN ends that request without retry; three consecutive UNKNOWN, source/ACL/code/resource violation, budget or time box stop the batch.',
    'quality_certified': False, 'in_sample': True,
    'note': 'Questions written for this experiment from the field question; the mock rules exist only to give same-kind wrong candidates. One run per arm; a difference is an observation, not a rate.'}
cases = [{'id': cid, 'arms': ['baseline', 'candidate'], 'document_ids': sorted(docs), 'steps': [{'number': 1, 'question': q, 'mode': '내규'}]} for cid, q, _ in CASES]
grades = [{'id': cid, 'targets': [{**t, 'document_id': target[t['document']]} for t in targets]} for cid, _, targets in CASES]
put(DES/'criteria.json', criteria); put(DES/'grading-only.json', grades); put(DES/'live-cases.json', cases)
put(DES/'provider-policy.json', read(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json', {'request': criteria['authorization'], 'documents': sorted(docs), 'names': docs,
    'record_sha256': sha(ROOT/'01_DATA/RAW/internal/risk_team/EXPORT_AUTHORIZATION_PHOTO_RULES_20261111.json'),
    'scope': 'Photo-transcribed risk_team rules (user-authorized for external experiment models) and two synthetic mock rules'})
put(DES/'generation.json', {'path': str(GEN.relative_to(ROOT)), 'manifest_sha256': sha(GEN/'manifest.json'), 'manifest': manifest})
transport = ART/'transport'; transport.mkdir()
pins = read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
    t = transport/name; t.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name, t); pins['files'][name] = sha(t)
put(transport/'transport-pins.json', pins)
arms = {'baseline': {'code_root': rel['code_root'], 'files': base_files, 'label': ptr['release_id']},
        'candidate': {'code_root': stage['code_root'], 'files': cand_files, 'label': 'linked-documents-staged-r5'}}
put(DES/'arms.json', arms)
paths = [*Path(__file__).parent.glob('*.py'), *(DES/x for x in ('criteria.json', 'live-cases.json', 'authorization.json', 'provider-policy.json', 'arms.json', 'grading-only.json', 'generation.json'))]
put(DES/'freeze-live.json', {'files': {str(p.relative_to(ROOT)): sha(p) for p in paths}, 'selected_pointer': ptr, 'model_calls_before_freeze': 0,
    'isolation_note': 'Candidate code is the main_release staged tree, hash-pinned file by file (no adr_candidate snapshot); it is not modified during the run (checked per request).'})
print('Frozen MAIN196 baseline + linked-documents candidate, 3 questions x 2 arms; model 0')
