"""Freeze ADR-1524 before any model call: 3 comparison (대사) questions x 1 arm (candidate r11), once each, real Qwen3.8,
experiment transport with provider fallback (same as ADR-1515).

candidate = compare-general-flow r11 on MAIN220 (09_ARTIFACTS/AUDITS/20261113-compare-general-flow-r11/staged, workflow
            1.21.10): r10 (call shares 60/16/12, 60% time) plus the one fix the user allowed after ADR-1523 (user 11-13
            "성능의 심각한 결함이 있으면 수정할 기회 1번"): (18) a side follow-up's read list is kept once
            (state['followup_reads']) and not copied into every row asked together (ADR-1523 liquidity: 4 rows x 22 KB
            made the item list 104 KB, over the 94 KB input limit, and item review stopped the whole 대사), (19) the
            evidence check reads each document once and checks completeness once per source (1,244 originals: the
            report's original check ran past its 30 s window), (20) that stop is named for legal users.
Comparison: ADR-1523 (r10 on MAIN219), ADR-1521 (r9), ADR-1515 (r5) (earlier runs, not the same time).

User 2026-11-13: "테스트 괜찮으면 메인 반영해줘 ... 성능의 심각한 결함이 있으면 그것도 수정할 기회를 줄게 1번 ... 꼼꼼하게
검토한 이후에 메인에 반영후 삼성메일로 쏴줘". This run is the real-model check of that fix before MAIN.
Targets go only to design/grading-only.json.

usage: setup.py"""
from common import *
import shutil,sqlite3
DES.mkdir(parents=True,exist_ok=True)
assert not (DES/'freeze.json').exists(),'already frozen'
rel=lambda p:str(Path(p).relative_to(ROOT))
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
BASE_ID='followup-cards-20261113-r1'
release=read(ROOT/'08_DEPLOYMENT/RELEASES'/BASE_ID/'release.json');files=release['files']
S=ROOT/'09_ARTIFACTS/AUDITS/20261113-compare-general-flow-r11/staged'
cand={n:sha(S/n) for n in files}
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.21.10'
cmanifest={'release_id':'candidate-compare-general-flow-r11','base_release':BASE_ID,'code_root':rel(S),'files':cand}
put(DES/'candidate-release.json',cmanifest)
put(DES/'code-candidate.json',{'release_id':'candidate-compare-general-flow-r11','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,
    'changed_from_baseline':sorted(n for n in files if cand[n]!=files[n]),'flow':'general-questions-v1 (r11)',
    'previous_candidate':'04_EXPERIMENTS/ADR/ADR-1523-compare-r10-call-shares-qwen/artifacts/design/code-candidate.json'})
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
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12, ADR-1504..1506); 호출한도 더 늘려봐봐 (2026-11-12, r6); 지금 실험중지하고 이거 다 회수하게 수정하고 다시 돌려 (2026-11-12, r7); 대사만 설정값 우선 (2026-11-12, r8); r9 follows the same instructions (fix found in ADR-1520); 호출한도를 정해야 겠네 루프가 심한듯 -> 어어 그렇게 해줘 (2026-11-12, r10 shares); 테스트 괜찮으면 메인 반영, 심각한 결함이면 수정 기회 1번 (2026-11-13, r11); new providers in the fallback list receive the same documents',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of the request team scope in the frozen generations; targets are never sent'})
criteria={
 'question':'With the one fix after ADR-1523 (follow-up reads kept once, evidence check reuses document and completeness), does the question 대사 finish all 3 questions with comparison and keep the r10 call shares?',
 'hypothesis':'r11 ends no question with a STOP, reaches comparison 3/3 with comparison verdict rows (not 미비 후보, not 외규만) in >=2 of 3 and >= 8 in total, keeps 0 read external articles outside the table, HTTP 200 and the same repeated answer 3/3, targets 6/6, effective limit 60, and the row list in every input stays under the input limit.',
 'primary':['per case: STOP failure points (any); comparison verdict rows (not 미비 후보, not 외규만); first comparison call; targets in a row on their side',
            'per case: external articles outside the table (0); HTTP of the request and the repeat; scope size (bytes) at the end',
            'per case: effective budget from the response (model_limit 60, model_reserved); calls by stage'],
 'secondary':['physical calls, switched attempts, request/model/non-model seconds, CPU, cost; 외규만 rows; items held by the shares'],
 'success':'no STOP in 3/3; comparison reached 3/3; comparison verdict rows in >=2 of 3 and >= 8 in total; 0 external articles outside the table in 3/3; HTTP 200 and same repeated answer 3/3; targets 6/6; effective limit 60; every request within 60 model calls and 1800 s.',
 'refute':'any STOP, or comparison not reached in a question, or comparison verdict rows in fewer than 2 questions or fewer than 8 in total, or an external article outside the table, or any HTTP>=500 or a different repeated answer, or fewer than 6 targets.',
 'comparison':'ADR-1523 (r10): liquidity stopped at item review (input limit, item list 104 KB from 4 x 22 KB follow-up read lists) and the report check ran past 30 s, 0 rows; soundness and riskcommittee no STOP, comparison verdict rows 8 and 8, targets 4/6, physical 138, 1964 s request time.',
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
print('frozen: candidate r11 (r10 + follow-up reads once, evidence check reuse) + provider fallback;',len(cells),'cells; risk',len(risk),'liq',len(liq),'docs')
