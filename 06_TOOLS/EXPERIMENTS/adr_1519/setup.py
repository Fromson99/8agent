"""Freeze ADR-1519 before any model call: 3 comparison (대사) questions x 1 arm (candidate r7), once each, real Qwen3.8,
experiment transport with provider fallback (same as ADR-1515).

candidate = compare-general-flow r7 (09_ARTIFACTS/AUDITS/20261112-compare-general-flow-r7/staged, workflow 1.21.6): r6
            (80 model calls, 1800 s) plus: (12) a pairing packet whose rows stay wrong after the one correction keeps the
            rows of the rejected proposal that pass every row check on their own (was: the whole packet left out), and
            (13) every external article read in the 대사 that no row holds is put in the table as its own
            "외규만 — 짝 미정" row with its read text and the reason (was: only named in a card; ADR-1515: 24/16/14).
Comparison: ADR-1515 (r5, same transport, same questions; earlier run, not the same time). ADR-1517 (r6) was frozen
            and stopped before its first answer (user: stop and fix this first).

User 2026-11-12: "호출한도 더 늘려봐봐" (r6) and "지금 실험중지하고 이거 다 회수하게 수정하고 다시 돌려" (r7).
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
S=ROOT/'09_ARTIFACTS/AUDITS/20261112-compare-general-flow-r7/staged'
cand={n:sha(S/n) for n in files}
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.21.6'
cmanifest={'release_id':'candidate-compare-general-flow-r7','base_release':BASE_ID,'code_root':rel(S),'files':cand}
put(DES/'candidate-release.json',cmanifest)
put(DES/'code-candidate.json',{'release_id':'candidate-compare-general-flow-r7','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,
    'changed_from_baseline':sorted(n for n in files if cand[n]!=files[n]),'flow':'general-questions-v1 (r7)',
    'previous_candidate':'04_EXPERIMENTS/ADR/ADR-1517-compare-r6-call-limit-qwen/artifacts/design/code-candidate.json'})
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
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12, ADR-1504..1506); 호출한도 더 늘려봐봐 (2026-11-12, r6); 지금 실험중지하고 이거 다 회수하게 수정하고 다시 돌려 (2026-11-12, r7); new providers in the fallback list receive the same documents',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of the request team scope in the frozen generations; targets are never sent'})
criteria={
 'question':'Does every external article read in the 대사 end up in the table (in a paired row or as its own 외규만 row), and do the rows of a pairing packet left out after correction survive?',
 'hypothesis':'r7 leaves no read external article outside the table (UNPLACED card count = 외규만 rows, no external article read only in the card), keeps HTTP 200 and the same repeated answer 3/3, ends no question by the call or time limit, reaches comparison 3/3 with comparison verdict rows (not counting 미비 후보 and 외규만 rows) in >=2 of 3 and >= 8 in total, and keeps targets 6/6.',
 'primary':['per case: external articles read but in no table row (paired rows + 외규만 rows) = 0; 외규만 rows and the UNPLACED card name the same count',
            'per case: pairing packets left out after correction and the rows kept from them (pair_skips.kept_rows)',
            'per case: STOP failure point (budget/time), comparison verdict rows (not 미비 후보, not 외규만), targets in a row on their side; HTTP of the request and the repeat'],
 'secondary':['physical calls, switched attempts, request/model/non-model seconds, CPU, cost; first comparison call; follow-ups asked',
              '외규만 rows by reason (pairing left out / no row took it / item review disposition); hand reading of which 외규만 articles matter (observation only)'],
 'success':'0 read external articles outside the table in 3/3 and card count = 외규만 rows; HTTP 200 and same repeated answer 3/3; no budget/time STOP; comparison reached 3/3; comparison verdict rows in >=2 of 3 and >= 8 in total; targets 6/6; every request within 80 model calls and 1800 s.',
 'refute':'any read external article only in the card or nowhere, or any HTTP>=500 or a different repeated answer, or a budget/time STOP, or comparison verdict rows in fewer than 2 questions or fewer than 8 in total, or fewer than 6 targets.',
 'comparison':'ADR-1515 (r5, 48 calls/1200 s): unplaced external articles named in the card 24/16/14 (not in the table), verdict rows 3/2/3 (8), liquidity budget STOP with 3 items uncompared, physical 41/30/29.',
 'transport':'provider fallback: design/fallback-policy.json (same model, reasoning none, no output cap); streamed; switch on non-200, transport error, stream error, no non-blank content in 60 s, only blank content for 60 s, finish not stop, empty answer, reasoning output, echo mismatch; a complete answer with wrong JSON is not switched.',
 'limits':{'physical_total':320,'per_request':100,'per_physical_seconds':180,'reported_cost_usd':5,'time_box_minutes':90,'workers':1,
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
print('frozen: candidate r7 (kept rows + 외규만 rows, 80 calls) + provider fallback;',len(cells),'cells; risk',len(risk),'liq',len(liq),'docs')
