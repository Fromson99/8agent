"""Freeze ADR-1528 before any model call: 문서 대사, external side found from the internal articles with the pick filters.

User 2026-11-13 after ADR-1527 ("외규 저거 필터 이런거 해야 되지 않을까 / 어떤 기능에서 어떤 게 나온 거냐" → origin trace:
of the 72 외규만 rows 62 came from server reads after the pick — word search 19, one link step 28, special search 25 —
while the picked candidates gave 17 of 21 pairs) → "싹다 진행해봐":
  linked articles (one reference step from the nearest candidates, both ways) and special/exception articles become
  UNREAD candidates the pick sees (found_by LINK), not server reads; the server reads only what the pick chose;
  supplementary provisions, attached forms are never candidates; a definitions article's candidates are not expanded;
  the word search runs only for an article whose pick took none, and reads a hit only when its title shares a content
  word (generic words left out); the question 대사's special-rule search is not run for a group.
candidate = 09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged5 (on MAIN226 compare-split-more-20261113-r1).
Arms as ADR-1527 (same document 위험관리기준시행세칙, liquidity generation, same vectors, same targets), each once.
Targets go only to design/grading-only.json.

usage: setup.py"""
from common import *
import shutil
DES.mkdir(parents=True,exist_ok=True)
assert not (DES/'freeze.json').exists(),'already frozen'
rel=lambda p:str(Path(p).relative_to(ROOT))
BASE_ID='compare-split-more-20261113-r1'
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['release_id']==BASE_ID
release=read(ROOT/'08_DEPLOYMENT/RELEASES'/BASE_ID/'release.json')
S=ROOT/'09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged5'
cand={str(p.relative_to(S)):sha(p) for p in sorted(S.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
assert read(S/'02_BACKEND/workflow/risk_team_document_compare_workflow/manifest.json')['version']=='2.0.0'
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.22.0'
put(DES/'candidate-release.json',{'release_id':'candidate-document-compare-pick-filters','base_release':BASE_ID,'code_root':rel(S),'files':cand})
put(DES/'code-candidate.json',{'release_id':'candidate-document-compare-pick-filters','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,
    'changed_from_base':sorted(n for n in set(cand)|set(release['files']) if cand.get(n)!=release['files'].get(n)),
    'flow':'document 2.0.0 = 대사 1.22.0 per reading group, external side from the internal articles; links/special as pick candidates, reads only of picks'})
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
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12); 내규 외부로 쏴도 됨 (2026-11-11); 싹다 진행해봐 (2026-11-13, this run)',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of the frozen generation; targets are never sent'})
criteria={
 'question':'With linked and special articles shown to the pick as unread candidates (read only when picked), forms and supplementary provisions excluded, and the word search only for unpicked articles, are there far fewer external-only rows than ADR-1527 while the expected external articles stay in the rows of their internal article?',
 'hypothesis':'vector arm: completed, 6/6 groups, 외규만 rows well under ADR-1527 (72), expected articles in the same row >= ADR-1527 (5/7), 제3-24조의4 now picked as a LINK candidate and paired; search arm finishes too.',
 'primary':['per arm: 외규만 (짝 미정) rows and their origin (PICK / WORDS / INTERNAL_CITES / SPECIAL); expected external articles in a row with their internal article (row level) and in the same group table',
            'per arm: rows with a comparison verdict; request seconds; groups finished; candidates by origin (VECTOR / SEARCH / LINK)'],
 'secondary':['physical calls, switched, unknown, cost, CPU, peak RSS; pick calls and corrections; reads per group'],
 'success':'vector arm: HTTP 200 completed, 6/6 groups, 외규만 rows <= 36 (half of ADR-1527), >= 5/7 expected articles in a row with their internal article; the same request again returns the same answer with 0 calls.',
 'refute':'any HTTP>=500, a group held for a code fault, fewer than 4/7 expected articles in a row in the vector arm, or 외규만 rows not lower than ADR-1527.',
 'comparison':'ADR-1527 (staged4, server reads after the pick): vector 324.7 s, 70 calls, 외규만 72, same row 5/7; search 290.2 s, 78 calls, 외규만 121, same row 3/7.',
 'transport':'provider fallback as ADR-1524/1525/1527 (same model, reasoning none, no output cap).',
 'limits':{'physical_total':400,'per_client':300,'per_physical_seconds':180,'reported_cost_usd':3,'time_box_minutes':60,
           'ram_start_gib':5,'wait_seconds':1800,'parallel_groups':3},
 'order':'one process per arm, sequential: vector then search; after no other experiment process has run for 2 minutes.',
 'stop':'An unknown provider outcome stops that group (no automatic resend); operator stop file, budget or time box stop the run.',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting); not used by a document group (no ordinary question).',
 'grading':'by script from each group run table rows (internal and external citation headings, origin of each external original from the group journal); verdict correctness read by hand as observation only.',
 'quality_certified':False,'in_sample':True,'repeats':1,'decision_eligible':False}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ('common.py','live.py','start_now.sh','resource_guard.py','pinned_imports.py','setup.py','collect.py')),
        *(DES/n for n in ('code-candidate.json','candidate-release.json','provider-policy.json','generations.json','cases.json','cells.json',
                          'authorization.json','criteria.json','grading-only.json','fallback-policy.json')),
        ART/'transport/transport-pins.json',ART/'vectors-external.json',ART/'vectors-external.npy',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
print('frozen: candidate document 2.0.0 / 대사 1.22.0 (pick filters);',len(cases),'cases;',{c['id']:len(c['document_ids']) for c in cases})
