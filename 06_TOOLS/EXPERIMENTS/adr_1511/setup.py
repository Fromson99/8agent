"""Freeze ADR-1511 before any model call: 3 comparison (대사) questions x 1 arm (candidate r4), once each, real Qwen3.8.

candidate = compare-general-flow r4 (09_ARTIFACTS/AUDITS/20261112-compare-general-flow-r4/staged): r3 (ADR-1510) plus
            (8) a read the item review asks for (ITEM_RESEARCH follow-up in that side's chat) is made only when the calls
            left cover the remaining item reviews, comparison and finalization (the same gate as the pairing follow-up);
            otherwise it is held and named in the card ("비교할 몫을 남기려고 더 찾지 않음").
r3 was r2 plus (4) earlier side answer checked for owner/binding only, (5) one grouped follow-up per side under the
            budget gate, (6) a pairing packet still wrong after its correction skipped and named, (7) stop names.
r2 was the ADR-1507 candidate plus (1) pairing packets sized with what is sent, (2) each read unit once and at most
            8 parts of an article, (3) the unplaced-external card by article.
Comparison: ADR-1507 (MAIN219, first candidate), ADR-1508 (r2) and ADR-1510 (r3) cells of the same questions, data and
transport (earlier runs, not the same time; read from those ADRs' frozen artifacts).

User 2026-11-12: "싹다 진행해줘봐" (after ADR-1508; ADR-1510 showed item-review follow-ups using the comparison calls).
Targets go only to design/grading-only.json.

usage: setup.py"""
from common import *
import shutil,sqlite3
DES.mkdir(parents=True,exist_ok=True)
assert not (DES/'freeze.json').exists(),'already frozen'
rel=lambda p:str(Path(p).relative_to(ROOT))
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
BASE_ID='failure-answers-20261112-r1'
release=read(ROOT/'08_DEPLOYMENT/RELEASES'/BASE_ID/'release.json');files=release['files']
S=ROOT/'09_ARTIFACTS/AUDITS/20261112-compare-general-flow-r4/staged'
cand={n:sha(S/n) for n in files}
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.21.3'
cmanifest={'release_id':'candidate-compare-general-flow-r4','base_release':BASE_ID,'code_root':rel(S),'files':cand}
put(DES/'candidate-release.json',cmanifest)
put(DES/'code-candidate.json',{'release_id':'candidate-compare-general-flow-r4','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,
    'changed_from_baseline':sorted(n for n in files if cand[n]!=files[n]),'flow':'general-questions-v1 (r4)',
    'previous_candidate':'04_EXPERIMENTS/ADR/ADR-1510-compare-followup-budget-qwen/artifacts/design/code-candidate.json'})
B=ROOT/release['code_root']
assert sha(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==sha(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')
shutil.copyfile(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
# Transport (experiment client) pins: the same bytes as ADR-1503..1506.
src=ROOT/'04_EXPERIMENTS/ADR/ADR-1503-main212-special-external-liquidity-qwen/artifacts/transport'
pins=read(src/'transport-pins.json')
for name,h in pins['files'].items():
    t=ART/'transport'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/name,t);assert sha(t)==h==sha(ROOT/name),name
shutil.copyfile(src/'transport-pins.json',ART/'transport/transport-pins.json')
GEN={'main':'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation',
     'liquidity':'01_DATA/TERM_RELEASES/liquidity-compare-20261111-r1/generation'}
gens={}
for k,p in GEN.items():
    m=read(ROOT/p/'manifest.json');gens[k]={'path':p,'manifest_sha256':sha(ROOT/p/'manifest.json'),'generation_id':m['generation_id'],'store_sha256':m['store_sha256']}
assert gens['main']['manifest_sha256']==release['data_manifest_sha256']
put(DES/'generations.json',gens)
def team_docs(gpath,team):
    db=sqlite3.connect((ROOT/gpath/'store.sqlite').as_uri()+'?mode=ro',uri=True);out=[]
    for did,raw in db.execute("SELECT document_id,json_extract(json,'$.document_metadata') FROM document"):
        md=json.loads(raw) if raw else {};ts={l.get('team') for l in [md,*md.get('aliases',[])] if isinstance(l,dict)}
        if team is None or team in ts:out.append(did)
    return sorted(out)
risk=team_docs(GEN['main'],'risk_team');liq=team_docs(GEN['liquidity'],None)
cmp=[('cmp-liquidity','liquidity','유동성비율 관련한 외부규정과 내부 규정은 어떻게 되나요?',liq,
      [{'side':'external','document':'금융투자업규정','article':'제3-24조의4'},{'side':'internal','document':'위험관리기준시행세칙','article':'제6-4조'}]),
     ('cmp-soundness','liquidity','건전성비율(순자본비율 등) 관련 외부규정과 내부규정을 비교해줘',liq,
      [{'side':'internal','document':'위험관리기준시행세칙','article':'제2-1조'},{'side':'external','document':'금융투자업규정','article':'제3-6조'}]),
     ('cmp-riskcommittee','main','위험관리위원회의 구성과 운영에 관한 외부규정과 내부규정을 비교해줘',risk,
      [{'side':'internal','document':'위험관리위원회운영준칙','article':None},{'side':'external','document':'금융회사의 지배구조에 관한 법률','article':'제21조'}])]
cases=[];grades=[]
for cid,g,question,docs,targets in cmp:
    cases.append({'id':cid,'kind':'compare','generation':g,'team':'risk_team','mode':'대사','question':question,'document_ids':docs,'vector':False})
    grades.append({'id':cid,'kind':'compare','targets':targets})
cells=[{'case':c['id'],'arm':'candidate'} for c in cases]
put(DES/'cases.json',cases);put(DES/'cells.json',cells);put(DES/'grading-only.json',grades)
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12, ADR-1504..1506); 싹다 진행해줘봐 (2026-11-12)',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of the request team scope in the frozen generations; targets are never sent'})
criteria={
 'question':'With item-review follow-ups held when the calls left are needed for comparison, does the general-question 대사 reach comparison verdicts?',
 'hypothesis':'r4 ends no question with HTTP>=500 (also the repeated request), stops no question at pairing, reaches item review in 3/3 and has comparison verdict rows (not counting 미비 후보) in at least 2 of 3, keeping 6/6 targets in the table.',
 'primary':['per case: workflow stages reached (workflow-items, workflow-compare), STOP failure point stage',
            'per case: table rows with a comparison verdict other than 미비 후보 (comparison rows), rows with both sides',
            'per case: grading targets (document + article) in a table row on their side',
            'per case: HTTP status of the request and of the repeated request (same answer, no extra model call)'],
 'secondary':['physical calls, unknown outcomes, request seconds, model/non-model seconds, CPU seconds, cost; follow-ups asked; pairing calls and input chars',
              'model call number of the first comparison call; item-review reads held for comparison (card count)',
              'external articles read but in no table row (analyze_posthoc.py, by article)'],
 'success':'no HTTP>=500 (first or repeated); no pairing stop; item review reached 3/3; comparison verdict rows in >=2 of 3; targets in table 6/6; every request within 48 model calls and 1200 s.',
 'refute':'any HTTP>=500, or a pairing stop, or comparison verdict rows in fewer than 2 questions, or fewer than 6 targets in the table.',
 'comparison':'ADR-1507 (MAIN219, first candidate), ADR-1508 (r2) and ADR-1510 (r3) cells: same questions, generations, scope, transport pins and provider; earlier runs, not the same time.',
 'limits':{'physical_total':200,'per_request':64,'per_physical_seconds':180,'reported_cost_usd':4,'time_box_minutes':90,'workers':1,
           'ram_start_gib':4.5,'wait_seconds':1800},
 'order':'one process per cell, sequential (no other heavy work); a cell with a provider failure runs once more at the end. start.sh starts nothing (not even the model-free preflight) while a driver, batch or live process of another experiment runs (ADR-1509 of another session was running at freeze time), waits until none has run for 10 minutes, then runs the preflight and the cells.',
 'stop':'An unknown provider outcome stops that request (no automatic resend). The run stops on the operator stop file, two consecutive runner/resource failures before an answer, the budget or the time box.',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting); no local vector publication for these documents, so body search (no retriever).',
 'grading':'golden article match on the table by script (no model judge); semantic correctness of verdicts read by hand and reported as observation only.',
 'quality_certified':False,'in_sample':True,'repeats':1,'decision_eligible':False}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ('common.py','live.py','run_all.sh','start.sh','resource_guard.py','pinned_imports.py','setup.py','collect.py','analyze_posthoc.py')),
        *(DES/n for n in ('code-candidate.json','candidate-release.json','provider-policy.json','generations.json','cases.json','cells.json',
                          'authorization.json','criteria.json','grading-only.json')),
        ART/'transport/transport-pins.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
print('frozen: candidate r4;',len(cells),'cells; risk',len(risk),'liq',len(liq),'docs')
