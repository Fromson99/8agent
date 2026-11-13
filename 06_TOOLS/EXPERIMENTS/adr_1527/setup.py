"""Freeze ADR-1527 before any model call: 문서 대사 with the external side found from the internal articles.

User 2026-11-13: "내규에 해당하는 외규 문서를 먼저 찾겠다 / 현업은 외규 조사 → 우리는 이렇게 / 내규 내용 보면 어디로 갈지
유추 / vector도" → ADR-1526 probe → "진행해봐".
candidate = 09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged4 (on MAIN226 compare-split-more-20261113-r1):
  document 2.0.0 runs each reading group as a 대사 1.22.0 run whose external side is NOT an ordinary question: per internal
  article the nearest external articles (vectors; without vectors a body search with its title), one model pick per group
  (articles, documents, words in external terms), server reads of the picks, of those words inside the picked documents and
  one reference step both ways; then pairing, item review, comparison, report (unit policy v2, three groups at a time).
Arms on the same document (위험관리기준시행세칙, liquidity generation, 6 reading groups), each once:
  vector : the experiment retriever (bge-m3 vectors of the generation's 1,157 external articles, prep_vectors.py) behind the
           product's matcher.initial_vector interface.
  search : no retriever (as the local generation and any field scope without published vectors): body search by title.
Comparison (not the same code): ADR-1525 (ordinary external question per group): 12.6 min, 104 calls, 외규만 84 rows,
the key group paired 8 rows but ran out of time before item review.
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
S=ROOT/'09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged4'
cand={str(p.relative_to(S)):sha(p) for p in sorted(S.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
assert read(S/'02_BACKEND/workflow/risk_team_document_compare_workflow/manifest.json')['version']=='2.0.0'
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.22.0'
put(DES/'candidate-release.json',{'release_id':'candidate-document-compare-units','base_release':BASE_ID,'code_root':rel(S),'files':cand})
put(DES/'code-candidate.json',{'release_id':'candidate-document-compare-units','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,
    'changed_from_base':sorted(n for n in set(cand)|set(release['files']) if cand.get(n)!=release['files'].get(n)),
    'flow':'document 2.0.0 = 대사 1.22.0 per reading group, external side from the internal articles'})
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
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12); 내규 외부로 쏴도 됨 (2026-11-11); 진행해봐 (2026-11-13, this run)',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of the frozen generation; targets are never sent'})
criteria={
 'question':'With the external side found from the internal articles (candidates, one pick per group, reads, one link step), does the whole-document 대사 pair the expected external articles in the same table rows, with fewer external-only rows and in less time than ADR-1525?',
 'hypothesis':'vector arm: completed, 6/6 groups, >=4 of the 7 expected external articles in a table row with their internal article (ADR-1526: 5 of 7 reached), 외규만 rows well under ADR-1525 (84), the key group (제2-1조~제6-7조) gets comparison verdict rows; search arm finishes too (fewer targets expected).',
 'primary':['per arm: request seconds; groups finished; expected external articles in a row with their internal article (row level) and in the same group table',
            'per arm: rows with a comparison verdict vs 외규만 (짝 미정) rows; per group: pick documents, vector status, reads'],
 'secondary':['physical calls, switched, unknown, cost, CPU, peak RSS; pick calls and corrections'],
 'success':'vector arm: HTTP 200 completed, 6/6 groups, >=4/7 expected articles in a row with their internal article, 외규만 rows < 42 (half of ADR-1525); the same request again returns the same answer with 0 calls.',
 'refute':'any HTTP>=500, a group held for a code fault, fewer than 3/7 expected articles in a row in the vector arm.',
 'comparison':'ADR-1525 (ordinary external question per group, staged3): 756.6 s, 104 calls, 외규만 84, key group 0 verdicts. ADR-1526 probe: 5/7 expected reached by vectors+pick+one step.',
 'transport':'provider fallback as ADR-1524/1525 (same model, reasoning none, no output cap).',
 'limits':{'physical_total':400,'per_client':300,'per_physical_seconds':180,'reported_cost_usd':3,'time_box_minutes':60,
           'ram_start_gib':5,'wait_seconds':1800,'parallel_groups':3},
 'order':'one process per arm, sequential: vector then search; after no other experiment process has run for 2 minutes.',
 'stop':'An unknown provider outcome stops that group (no automatic resend); operator stop file, budget or time box stop the run.',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting); not used by a document group (no ordinary question).',
 'grading':'by script from each group run table rows (internal and external citation headings); verdict correctness read by hand as observation only.',
 'quality_certified':False,'in_sample':True,'repeats':1,'decision_eligible':False}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ('common.py','live.py','start_now.sh','resource_guard.py','pinned_imports.py','setup.py','collect.py','prep_vectors.py')),
        *(DES/n for n in ('code-candidate.json','candidate-release.json','provider-policy.json','generations.json','cases.json','cells.json',
                          'authorization.json','criteria.json','grading-only.json','fallback-policy.json')),
        ART/'transport/transport-pins.json',ART/'vectors-external.json',ART/'vectors-external.npy',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
print('frozen: candidate document 2.0.0 / 대사 1.22.0;',len(cases),'cases;',{c['id']:len(c['document_ids']) for c in cases})
