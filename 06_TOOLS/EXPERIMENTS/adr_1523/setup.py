"""Freeze ADR-1523 before any model call: 3 comparison (대사) questions x 1 arm (candidate r10), once each, real Qwen3.8,
experiment transport with provider fallback (same as ADR-1515).

candidate = compare-general-flow r10 (09_ARTIFACTS/AUDITS/20261112-compare-general-flow-r10/staged, workflow 1.21.9): r9
            (외규 회수, the 대사's own call limit, relation-store errors by name, review limit ends only that item) plus
            (17) call shares for the question 대사 (user 2026-11-12 "호출한도를 정해야겠네 루프가 심한듯" -> "어어 그렇게
            해줘"): 60 calls in all; item review and the reads it asks for share 16 calls from the start of the item
            stage; at least 12 calls (or one per paired row + the finalization reserve) are always left for comparison
            and finalization; after 60% of the request time no read, re-review or side follow-up starts; a first item
            review gives way only to the comparison of items already reviewed (ADR-1521: liquidity 21 item reviews and
            0 comparisons until the time limit; soundness/riskcommittee 80/80 calls used during comparison).
Comparison: ADR-1521 (r9), ADR-1520 (r8), ADR-1519 (r7), ADR-1515 (r5) (earlier runs, not the same time).

User 2026-11-12: "호출한도 더 늘려봐봐", "지금 실험중지하고 이거 다 회수하게 수정하고 다시 돌려", "대사만 설정값 우선",
"호출한도를 정해야 겠네 루프가 심한듯?" -> "어어 그렇게 해줘".
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
S=ROOT/'09_ARTIFACTS/AUDITS/20261112-compare-general-flow-r10/staged'
cand={n:sha(S/n) for n in files}
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.21.9'
cmanifest={'release_id':'candidate-compare-general-flow-r10','base_release':BASE_ID,'code_root':rel(S),'files':cand}
put(DES/'candidate-release.json',cmanifest)
put(DES/'code-candidate.json',{'release_id':'candidate-compare-general-flow-r10','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,
    'changed_from_baseline':sorted(n for n in files if cand[n]!=files[n]),'flow':'general-questions-v1 (r10)',
    'previous_candidate':'04_EXPERIMENTS/ADR/ADR-1521-compare-r9-review-limit-skip-qwen/artifacts/design/code-candidate.json'})
B=ROOT/release['code_root']
assert sha(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==sha(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')
shutil.copyfile(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
# Transport pins: the ADR-1503 experiment client files (same bytes as ADR-1503..1511) plus the provider fallback module.
src=ROOT/'04_EXPERIMENTS/ADR/ADR-1503-main212-special-external-liquidity-qwen/artifacts/transport'
pins=read(src/'transport-pins.json')
for name,h in pins['files'].items():
    t=ART/'transport'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/name,t);assert sha(t)==h,name
fb='02_BACKEND/lawrag/research/provider_fallback.py'
shutil.copyfile(ROOT/fb,ART/'transport'/fb)
pins['modules']['lawrag.research.provider_fallback']=fb;pins['files'][fb]=sha(ART/'transport'/fb)
put(ART/'transport/transport-pins.json',pins)
shutil.copyfile(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_FALLBACK.json',DES/'fallback-policy.json')
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
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12, ADR-1504..1506); 호출한도 더 늘려봐봐 (2026-11-12, r6); 지금 실험중지하고 이거 다 회수하게 수정하고 다시 돌려 (2026-11-12, r7); 대사만 설정값 우선 (2026-11-12, r8); r9 follows the same instructions (fix found in ADR-1520); 호출한도를 정해야 겠네 루프가 심한듯 -> 어어 그렇게 해줘 (2026-11-12, r10 shares); new providers in the fallback list receive the same documents',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of the request team scope in the frozen generations; targets are never sent'})
criteria={
 'question':'With call shares (60 in all, item review + reads 16, comparison + finalization >= 12 kept, no new read after 60% of the time), does the question 대사 reach comparison and compare its items instead of looping on reads and re-reviews?',
 'hypothesis':'r10 ends no question with a budget/time STOP, reaches comparison 3/3 with comparison verdict rows (not 미비 후보, not 외규만) in >=2 of 3 and >= 8 in total, keeps 0 read external articles outside the table, HTTP 200 and the same repeated answer 3/3, targets 6/6, effective limit 60 (response usage), and spends fewer calls and less time than ADR-1521.',
 'primary':['per case: STOP failure points (any); comparison verdict rows (not 미비 후보, not 외규만); first comparison call; items held by the shares (ITEM_SHARE cards), reads held (BUDGET/TIME), follow-ups not asked (TIME/BUDGET)',
            'per case: external articles outside the table (0), targets in a row on their side; HTTP of the request and the repeat',
            'per case: effective budget from the response (model_limit 60, model_reserved); calls by stage (item review, item research, comparison, finalization)'],
 'secondary':['physical calls, switched attempts, request/model/non-model seconds, CPU, cost; 외규만 rows and kept rows of rejected pairing packets'],
 'success':'no budget/time STOP in 3/3; comparison reached 3/3; comparison verdict rows in >=2 of 3 and >= 8 in total; 0 external articles outside the table in 3/3; HTTP 200 and same repeated answer 3/3; targets 6/6; effective limit 60; every request within 60 model calls and 1800 s.',
 'refute':'any budget/time STOP, or comparison not reached in a question, or comparison verdict rows in fewer than 2 questions or fewer than 8 in total, or an external article outside the table, or any HTTP>=500 or a different repeated answer, or fewer than 6 targets.',
 'comparison':'ADR-1521 (r9, limit 80): liquidity time STOP before comparison with 0 table rows (70/80 calls: item review 21, source choice 18, answer writing 15, follow-ups 10, comparison 0); soundness/riskcommittee 80/80 calls used during comparison, verdict rows 4/5; targets 4/6; physical 230; 4055.8 s request time. ADR-1515 (r5, limit 40): verdict rows 3/2/3 (8).',
 'transport':'provider fallback: design/fallback-policy.json (same model, reasoning none, no output cap); streamed; switch on non-200, transport error, stream error, no non-blank content in 60 s, only blank content for 60 s, finish not stop, empty answer, reasoning output, echo mismatch; a complete answer with wrong JSON is not switched.',
 'limits':{'physical_total':330,'per_request':100,'per_physical_seconds':180,'reported_cost_usd':5,'time_box_minutes':120,'workers':1,
           'ram_start_gib':4.5,'wait_seconds':1800},
 'order':'one process per cell, sequential, after no other experiment process has run for 2 minutes (start_now.sh); a cell starts only with >=5GiB free RAM and yields below 3.4GiB. A cell whose every provider failed (STOP_EXTERNAL) or that yielded runs once more at the end.',
 'stop':'An unknown provider outcome stops that request (no automatic resend). The run stops on the operator stop file, two consecutive runner/resource failures before an answer, the budget or the time box.',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting); no local vector publication for these documents, so body search (no retriever).',
 'grading':'golden article match on the table by script (no model judge); semantic correctness of verdicts read by hand and reported as observation only.',
 'quality_certified':False,'in_sample':True,'repeats':1,'decision_eligible':False}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ('common.py','live.py','start_now.sh','resource_guard.py','pinned_imports.py','setup.py','collect.py','analyze_posthoc.py')),
        *(DES/n for n in ('code-candidate.json','candidate-release.json','provider-policy.json','generations.json','cases.json','cells.json',
                          'authorization.json','criteria.json','grading-only.json','fallback-policy.json')),
        ART/'transport/transport-pins.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
print('frozen: candidate r10 (call shares 60/16/12, 60% time, 외규 회수) + provider fallback;',len(cells),'cells; risk',len(risk),'liq',len(liq),'docs')
