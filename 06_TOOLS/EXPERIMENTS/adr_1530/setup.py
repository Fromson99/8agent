"""Freeze ADR-1530 before any model call: ADR-1529 candidate plus the pick's per-article pairs given to the pairing.

ADR-1529 (staged6): the pick took the company's special rules (제2-8조의3·제3-24조의4) and 제3-24조의4 was paired with 제6-4조
for the first time (vector same-row 3/7→4/7), but the pairing did not know which internal article each picked external was
read for: 제3-40조·제2-8조의3 picked for 제2-1조 stayed 외규만 rows and 제2-1조's rows had no external. User "진행해봐":
find_external keeps (internal article, external article, evidence IDs) for every read; the pairing of a reading group
gets them as internal_picks and is told to review those externals first as the pair of that internal article's row.
candidate = 09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged7 (= staged6 + unit.py pairs + concepts.py internal_picks, MAIN226).
Arms as ADR-1527/1528/1529 (same document, vectors, targets), each once. Targets go only to design/grading-only.json.

usage: setup.py"""
from common import *
import shutil
DES.mkdir(parents=True,exist_ok=True)
assert not (DES/'freeze.json').exists(),'already frozen'
rel=lambda p:str(Path(p).relative_to(ROOT))
BASE_ID='compare-split-more-20261113-r1'
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['release_id']==BASE_ID
release=read(ROOT/'08_DEPLOYMENT/RELEASES'/BASE_ID/'release.json')
S=ROOT/'09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged7'
cand={str(p.relative_to(S)):sha(p) for p in sorted(S.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
assert read(S/'02_BACKEND/workflow/risk_team_document_compare_workflow/manifest.json')['version']=='2.0.0'
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.22.0'
put(DES/'candidate-release.json',{'release_id':'candidate-document-compare-pairing-picks','base_release':BASE_ID,'code_root':rel(S),'files':cand})
put(DES/'code-candidate.json',{'release_id':'candidate-document-compare-pairing-picks','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,
    'changed_from_base':sorted(n for n in set(cand)|set(release['files']) if cand.get(n)!=release['files'].get(n)),
    'flow':'document 2.0.0 = 대사 1.22.0 per reading group, external side from the internal articles; links/special as pick candidates, reads only of picks; applicable special rules picked with the general article; the pairing gets the pick per internal article'})
B=ROOT/release['code_root']
assert sha(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==sha(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')
shutil.copyfile(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
# Transport: the same pinned experiment client and provider fallback as ADR-1524 (bytes checked).
src=ROOT/'04_EXPERIMENTS/ADR/ADR-1525-document-compare-units-qwen/artifacts/transport'
pins=read(src/'transport-pins.json')
for name,h in pins['files'].items():
    t=ART/'transport'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/name,t);assert sha(t)==h,name
put(ART/'transport/transport-pins.json',pins)
shutil.copyfile(ROOT/'04_EXPERIMENTS/ADR/ADR-1525-document-compare-units-qwen/artifacts/design/fallback-policy.json',DES/'fallback-policy.json')
GEN={'liquidity':'01_DATA/TERM_RELEASES/liquidity-compare-20261111-r1/generation'}
gens={}
for k,p in GEN.items():
    m=read(ROOT/p/'manifest.json');gens[k]={'path':p,'manifest_sha256':sha(ROOT/p/'manifest.json'),'generation_id':m['generation_id'],'store_sha256':m['store_sha256']}
put(DES/'generations.json',gens)
# The same vectors as ADR-1527 (bytes checked).
V=ROOT/'04_EXPERIMENTS/ADR/ADR-1527-document-compare-internal-driven-qwen/artifacts'
for n in ('vectors-external.json','vectors-external.npy'):
    shutil.copyfile(V/n,ART/n);assert sha(ART/n)==sha(V/n),n
vec=read(ART/'vectors-external.json');assert vec['generation']==GEN['liquidity'] and vec['count']==1157
import sqlite3
def docs(gpath):
    db=sqlite3.connect((ROOT/gpath/'store.sqlite').as_uri()+'?mode=ro',uri=True)
    return sorted(r[0] for r in db.execute('SELECT document_id FROM document'))
q='위험관리기준시행세칙 전체를 외규와 대사해 주세요.'
cases=[{'id':'doc-liquidity-vector','kind':'document','generation':'liquidity','team':'risk_team','mode':'문서 대사','question':q,'document_ids':docs(GEN['liquidity']),'vector':True},
       {'id':'doc-liquidity-search','kind':'document','generation':'liquidity','team':'risk_team','mode':'문서 대사','question':q,'document_ids':docs(GEN['liquidity']),'vector':False}]
targets=[{'internal':'제6-4조','external':['제3-24조의4','별표 10','제2-8조의3']},
         {'internal':'제2-1조','external':['제3-24조의4','제3-6조']},
         {'internal':'제11-6조','external':['제2-15조','제3-48조']}]
grades=[{'id':c['id'],'targets':targets} for c in cases]
put(DES/'cases.json',cases);put(DES/'cells.json',[{'case':c['id'],'arm':'candidate'} for c in cases]);put(DES/'grading-only.json',grades)
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12); 내규 외부로 쏴도 됨 (2026-11-11); 진행해봐 (2026-11-13, ADR-1530 run)',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of the frozen generation; targets are never sent'})
criteria={
 'question':'With the pick per internal article given to the pairing, are the picked externals paired with their internal article (fewer 외규만 rows from PICK, more expected pairs in the same row) without more noise?',
 'hypothesis':'vector arm: 제2-1조 rows get the externals picked for 제2-1조 (e.g. 제2-8조의3, 제3-24조의4, 제3-40조); same-row >= 5/7; 외규만 rows from PICK fewer than ADR-1529 (9).',
 'primary':['per arm: expected external articles in a row with their internal article (row level, 별표 10 title false positive removed by hand); 외규만 rows and origin',
            'per arm: rows with a comparison verdict; request seconds with output tokens (provider speed differs per run); groups finished'],
 'secondary':['physical calls, switched, unknown, cost, CPU, peak RSS'],
 'success':'vector arm: HTTP 200 completed, 6/6 groups, >= 5/7 expected articles in a row with their internal article, 외규만 rows <= 10; the same request again returns the same answer with 0 calls.',
 'refute':'any HTTP>=500, a group held for a code fault, vector same-row <= 3/7, or 외규만 rows > 36.',
 'comparison':'ADR-1529 (staged6): vector 424.2 s (slow provider), 69 calls, 외규만 11 (9 from PICK), same row 4/7; search 302.4 s, 71 calls, 외규만 6, 3/7. ADR-1527: vector 5/7 / 외규만 72.',
 'transport':'provider fallback as ADR-1524/1525/1527/1528/1529 (same model, reasoning none, no output cap).',
 'limits':{'physical_total':400,'per_client':300,'per_physical_seconds':180,'reported_cost_usd':3,'time_box_minutes':60,
           'ram_start_gib':5,'wait_seconds':1800,'parallel_groups':3},
 'order':'one process per arm, sequential: vector then search; after no other experiment process has run for 2 minutes.',
 'stop':'An unknown provider outcome stops that group (no automatic resend); operator stop file, budget or time box stop the run.',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting); not used by a document group (no ordinary question).',
 'grading':'by script from each group run table rows (internal and external citation headings, origin of each external original); verdict correctness read by hand as observation only.',
 'quality_certified':False,'in_sample':True,'repeats':1,'decision_eligible':False}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ('common.py','live.py','start_now.sh','resource_guard.py','pinned_imports.py','setup.py','collect.py')),
        *(DES/n for n in ('code-candidate.json','candidate-release.json','provider-policy.json','generations.json','cases.json','cells.json',
                          'authorization.json','criteria.json','grading-only.json','fallback-policy.json')),
        ART/'transport/transport-pins.json',ART/'vectors-external.json',ART/'vectors-external.npy',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
print('frozen: candidate document 2.0.0 / 대사 1.22.0 (pick filters + special rule line + pairing picks);',len(cases),'cases;',{c['id']:len(c['document_ids']) for c in cases})
