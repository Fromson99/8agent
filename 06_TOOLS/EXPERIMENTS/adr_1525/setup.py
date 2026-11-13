"""Freeze ADR-1525 before any model call: 문서 대사 rebuilt as the ordinary 대사 run once per reading group.

User 2026-11-13: "문서대사는 일반대사를 그냥 그 구조단위로 실행한 거 아닌가 … 어어 싹다 교체해주고 일반대사의 한도를 좀
조정해서 필수만 좀 들고오고 보수적으로 최대한 1시간 정도에 끝내게 해봐".

candidate = 09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged3 (on MAIN226 compare-split-more-20261113-r1):
  document workflow 2.0.0 = select the document, cut it into the stored reading groups, run each group as one ordinary
  대사 (risk_team_compare_workflow 1.22.0 with input.document_unit: internal side = the group's own text read whole,
  external side asked as an ordinary question, then linked/special reads, pairing, item review, comparison, report)
  under the lighter unit policy (30 calls, external side 10, no follow-up, one review per item), three groups at a time,
  about one hour per run (a group starts with its share of the time left, 150-600 s; none starts with less).
Cases (each once, sequential):
  doc-liquidity  : the real internal 위험관리기준시행세칙 (photo transcription, 6 reading groups) in the liquidity generation.
  doc-model-code : the large public stand-in of ADR-1440/1447/1460 (금융투자회사의 리스크관리 모범규준 as internal, about 32
                   groups) to check the one-hour bound. ADR-1447 (old document flow) needed 639 calls for 22 of 32 groups.
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
S=ROOT/'09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged3'
cand={str(p.relative_to(S)):sha(p) for p in sorted(S.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
assert read(S/'02_BACKEND/workflow/risk_team_document_compare_workflow/manifest.json')['version']=='2.0.0'
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.22.0'
put(DES/'candidate-release.json',{'release_id':'candidate-document-compare-units','base_release':BASE_ID,'code_root':rel(S),'files':cand})
put(DES/'code-candidate.json',{'release_id':'candidate-document-compare-units','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,
    'changed_from_base':sorted(n for n in set(cand)|set(release['files']) if cand.get(n)!=release['files'].get(n)),
    'flow':'document 2.0.0 = ordinary 대사 1.22.0 per reading group'})
B=ROOT/release['code_root']
assert sha(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==sha(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')
shutil.copyfile(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
# Transport: the same pinned experiment client and provider fallback as ADR-1524 (bytes checked).
src=ROOT/'04_EXPERIMENTS/ADR/ADR-1524-compare-r11-followup-reads-qwen/artifacts/transport'
pins=read(src/'transport-pins.json')
for name,h in pins['files'].items():
    t=ART/'transport'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/name,t);assert sha(t)==h,name
put(ART/'transport/transport-pins.json',pins)
shutil.copyfile(ROOT/'04_EXPERIMENTS/ADR/ADR-1524-compare-r11-followup-reads-qwen/artifacts/design/fallback-policy.json',DES/'fallback-policy.json')
GEN={'liquidity':'01_DATA/TERM_RELEASES/liquidity-compare-20261111-r1/generation',
     'model-code':'04_EXPERIMENTS/ADR/ADR-1440-document-compare-mode-qwen/artifacts/corpus/indexed'}
gens={}
for k,p in GEN.items():
    m=read(ROOT/p/'manifest.json');gens[k]={'path':p,'manifest_sha256':sha(ROOT/p/'manifest.json'),'generation_id':m['generation_id'],'store_sha256':m['store_sha256']}
put(DES/'generations.json',gens)
import sqlite3
def docs(gpath):
    db=sqlite3.connect((ROOT/gpath/'store.sqlite').as_uri()+'?mode=ro',uri=True)
    return sorted(r[0] for r in db.execute('SELECT document_id FROM document'))
cases=[{'id':'doc-liquidity','kind':'document','generation':'liquidity','team':'risk_team','mode':'문서 대사',
        'question':'위험관리기준시행세칙 전체를 외규와 대사해 주세요.','document_ids':docs(GEN['liquidity']),'vector':False},
       {'id':'doc-model-code','kind':'document','generation':'model-code','team':'risk_team','mode':'문서 대사',
        'question':'금융투자회사의 리스크관리 모범규준 문서 전체를 외규와 대사해 주세요.','document_ids':docs(GEN['model-code']),'vector':False}]
grades=[{'id':'doc-liquidity','targets':[
            {'internal':{'document':'위험관리기준시행세칙','article':'제6-4조'},'external':{'document':'금융투자업규정','article':'제3-24조의4'}},
            {'internal':{'document':'위험관리기준시행세칙','article':'제2-1조'},'external':{'document':'금융투자업규정','article':'제3-6조'}}]},
        {'id':'doc-model-code','targets':[]}]
put(DES/'cases.json',cases);put(DES/'cells.json',[{'case':c['id'],'arm':'candidate'} for c in cases]);put(DES/'grading-only.json',grades)
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12); 내규 외부로 쏴도 됨 (2026-11-11); '
    '어어 싹다 교체해주고 … 보수적으로 최대한 1시간 정도에 끝내게 해봐 (2026-11-13, this run)',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of each frozen generation; targets are never sent'})
criteria={
 'question':'Does the 문서 대사 rebuilt on the ordinary 대사 (one run per reading group, lighter limits, three at a time) finish a whole document within about one hour, with comparison tables per group?',
 'hypothesis':'doc-liquidity finishes all groups (no group held or waiting) with a 대사 table in each group; doc-model-code ends within 3700 s of request time (one hour plus the report) and its report names every group that did not start; no HTTP>=500; the same request again returns the same answer with 0 model calls.',
 'primary':['per case: request seconds; groups finished / held / waiting; per group: status, rows, verdict labels, model calls, allotted seconds',
            'doc-liquidity: each target pair (internal article and external article) in the same group section of the answer'],
 'secondary':['physical calls, switched attempts, unknown outcomes, cost, CPU, peak RSS; groups with no comparison verdict row'],
 'success':'doc-liquidity: completed, every group finished, >=1 of 2 target pairs in the same group section; doc-model-code: request <= 3700 s and either completed or partial with the waiting groups named; HTTP 200 and the same repeated answer in both.',
 'refute':'any request over 3700 s, any HTTP>=500, a group of doc-liquidity held for a code fault, a different repeated answer.',
 'comparison':'ADR-1447 (old document flow, same stand-in document): 639 calls for 22 of 32 groups over two requests, 90% of units deferred. ADR-1460: 15/32 groups before an external stop. Not the same code or time; observation only.',
 'transport':'provider fallback as ADR-1524 (design/fallback-policy.json; same model, reasoning none, no output cap).',
 'limits':{'physical_total':1400,'per_client':600,'per_physical_seconds':180,'reported_cost_usd':8,'time_box_minutes':150,
           'ram_start_gib':5,'wait_seconds':1800,'parallel_groups':3},
 'order':'one process per case, sequential, after no other experiment process has run for 2 minutes; doc-liquidity first; doc-model-code only if doc-liquidity returned HTTP 200.',
 'stop':'An unknown provider outcome stops that group (its run ends; no automatic resend); the operator stop file, budget or time box stop the run.',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting); no vector publication for these documents (body search).',
 'grading':'by script on the answer text (no model judge); verdict correctness read by hand as observation only.',
 'quality_certified':False,'in_sample':True,'repeats':1,'decision_eligible':False}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ('common.py','live.py','start_now.sh','resource_guard.py','pinned_imports.py','setup.py','collect.py')),
        *(DES/n for n in ('code-candidate.json','candidate-release.json','provider-policy.json','generations.json','cases.json','cells.json',
                          'authorization.json','criteria.json','grading-only.json','fallback-policy.json')),
        ART/'transport/transport-pins.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
print('frozen: candidate document 2.0.0 / 대사 1.22.0;',len(cases),'cases;',{c['id']:len(c['document_ids']) for c in cases})
