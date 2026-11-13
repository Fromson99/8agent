"""Freeze ADR-1531 before any model call: 3 question 대사 x 2 arms (baseline MAIN226, candidate staged8), once each,
interleaved per question, real Qwen3.8, experiment transport with provider fallback (as ADR-1515/1524).

User 2026-11-13 "1,2 둘다해봐" after the review of ADR-1524 with the 문서 대사 lessons (ADR-1527..1530): of the 외규만
rows of the 위험관리위원회 question, 22 of 34 were externals the external ordinary answer only read (not cited) and 6
were special-rule title reads. candidate = 09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged8 (on MAIN226):
  (1) the pairing gets side_uses: per side, the points that side's answer made and the articles each cites, and is told
      to pair those of both sides about the same duty/standard first;
  (2) an unpaired external no side's answer cited (nor a 문서 대사 pick, nor the internal text) is not a numbered 외규만
      item but goes to the bottom list "읽었지만 대사표에 넣지 않은 외규 원문" with that reason (nothing dropped);
  (5) the pairing is told to put a special/exception rule that applies to the company with the general article, and an
      external article that fits several rows in each.
  (it also carries the 문서 대사 changes, which a question 대사 does not use.)
baseline = MAIN226 compare-split-more-20261113-r1 (current local MAIN).
Targets go only to design/grading-only.json.

usage: setup.py"""
from common import *
import shutil,sqlite3
DES.mkdir(parents=True,exist_ok=True)
assert not (DES/'freeze.json').exists(),'already frozen'
rel=lambda p:str(Path(p).relative_to(ROOT))
BASE_ID='compare-split-more-20261113-r1'
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['release_id']==BASE_ID
RM=ROOT/'08_DEPLOYMENT/RELEASES'/BASE_ID/'release.json'
release=read(RM);files=release['files']
put(DES/'code-baseline.json',{'release_id':BASE_ID,'release_manifest':rel(RM),'release_manifest_sha256':sha(RM),
    'code_root':release['code_root'],'files':files,'flow':'MAIN226 question 대사 (r14)'})
S=ROOT/'09_ARTIFACTS/AUDITS/20261113-document-compare-units/staged8'
cand={str(q.relative_to(S)):sha(q) for q in sorted(S.rglob('*')) if q.is_file() and '__pycache__' not in q.parts}
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.22.0'
cmanifest={'release_id':'candidate-compare-side-uses','base_release':BASE_ID,'code_root':rel(S),'files':cand}
put(DES/'candidate-release.json',cmanifest)
put(DES/'code-candidate.json',{'release_id':'candidate-compare-side-uses','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,
    'changed_from_baseline':sorted(n for n in set(cand)|set(files) if cand.get(n)!=files.get(n)),'flow':'question 대사 + side_uses, answer-unused externals to the bottom list, special-rule line'})
B=ROOT/release['code_root']
assert sha(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==sha(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')
shutil.copyfile(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
# Transport: the ADR-1524 pinned experiment client + provider fallback (bytes checked).
src=ROOT/'04_EXPERIMENTS/ADR/ADR-1524-compare-r11-followup-reads-qwen/artifacts/transport'
pins=read(src/'transport-pins.json')
for name,h in pins['files'].items():
    t=ART/'transport'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/name,t);assert sha(t)==h,name
put(ART/'transport/transport-pins.json',pins)
shutil.copyfile(ROOT/'04_EXPERIMENTS/ADR/ADR-1524-compare-r11-followup-reads-qwen/artifacts/design/fallback-policy.json',DES/'fallback-policy.json')
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
cells=[{'case':c['id'],'arm':arm} for c in cases for arm in ('baseline','candidate')]
put(DES/'cases.json',cases);put(DES/'cells.json',cells);put(DES/'grading-only.json',grades)
put(DES/'authorization.json',{'user_instruction':'1,2 둘다해봐 (2026-11-13, ADR-1531); 외부에 모든 문서를 쏴도 됨 (2026-11-12, ADR-1504..1506); 호출한도 더 늘려봐봐 (2026-11-12, r6); 지금 실험중지하고 이거 다 회수하게 수정하고 다시 돌려 (2026-11-12, r7); 대사만 설정값 우선 (2026-11-12, r8); r9 follows the same instructions (fix found in ADR-1520); 호출한도를 정해야 겠네 루프가 심한듯 -> 어어 그렇게 해줘 (2026-11-12, r10 shares); 테스트 괜찮으면 메인 반영, 심각한 결함이면 수정 기회 1번 (2026-11-13, r11); new providers in the fallback list receive the same documents',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of the request team scope in the frozen generations; targets are never sent'})
criteria={
 'question':'With each side answer\'s cited articles given to the pairing and answer-unused externals kept out of the numbered items, does the question 대사 make more comparison verdict rows and fewer numbered 외규만 items than MAIN226 on the same 3 questions, keeping the targets?',
 'hypothesis':'candidate vs baseline (same questions, interleaved): numbered 외규만 items lower in total; comparison verdict rows (not 짝 미정, not 미비 후보) equal or higher in total; targets in the table the same or more; no new STOP or HTTP>=500.',
 'primary':['per arm and case: comparison verdict rows; numbered 외규만 items (UNPAIRED with question words) and bottom-list externals; targets in the table on their side',
            'per arm and case: HTTP, STOP failure points, same repeated answer'],
 'secondary':['physical calls, switched, request/model seconds (provider speed differs per run), cost; side_uses size in the pairing input'],
 'success':'candidate: numbered 외규만 items lower than baseline in total; comparison verdict rows >= baseline in total; targets in table >= baseline; HTTP 200 and the same repeated answer in 3/3; no new STOP.',
 'refute':'candidate comparison verdict rows fewer than baseline by more than 2 in total, or fewer targets in the table, or any HTTP>=500 or STOP the baseline did not have.',
 'comparison':'ADR-1524 (r11 on MAIN220, earlier): 외규만 9/17/34, comparison verdict rows 4/10/6, targets 6/6. This run has its own baseline (MAIN226) under the same provider conditions.',
 'transport':'provider fallback: design/fallback-policy.json (same as ADR-1524; same model, reasoning none, no output cap).',
 'limits':{'physical_total':500,'per_request':100,'per_physical_seconds':180,'reported_cost_usd':5,'time_box_minutes':150,'workers':1,
           'ram_start_gib':4.5,'wait_seconds':1800},
 'order':'one process per cell, sequential, per question baseline then candidate, after no other experiment process has run for 2 minutes; a cell starts only with >=5GiB free RAM and yields below 3.4GiB. A cell whose every provider failed or that yielded runs once more at the end.',
 'stop':'An unknown provider outcome stops that request (no automatic resend). The run stops on the operator stop file, the budget or the time box.',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting); no local vector publication for these documents, so body search (no retriever).',
 'grading':'golden article match on the table by script (no model judge); numbered 외규만 items from the row placement and question words; semantic correctness read by hand as observation only.',
 'quality_certified':False,'in_sample':True,'repeats':1,'decision_eligible':False}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ('common.py','live.py','start_now.sh','resource_guard.py','pinned_imports.py','setup.py','collect.py','analyze_posthoc.py')),
        *(DES/n for n in ('code-baseline.json','code-candidate.json','candidate-release.json','provider-policy.json','generations.json','cases.json','cells.json',
                          'authorization.json','criteria.json','grading-only.json','fallback-policy.json')),
        ART/'transport/transport-pins.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
print('frozen: baseline MAIN226 / candidate staged8 (side_uses, answer-unused externals to bottom, special line);',len(cells),'cells; risk',len(risk),'liq',len(liq),'docs')
