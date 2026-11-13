"""Freeze ADR-1507 before any model call: 3 comparison (대사) questions x 2 arms, once each, real Qwen3.8.

baseline  = selected MAIN219 release (failure-answers-20261112-r1): internal first -> concepts -> external (source-return children)
candidate = compare-general-flow candidate (staged7 of 09_ARTIFACTS/AUDITS/20261112-compare-failure-points, the bytes of the
            named changes compare-general-flow + -manifest-basis + -manifest-docflow): each side asked as an ordinary question,
            rows paired from both sides, only unpaired rows asked again.

User 2026-11-12: "실험한번해줘" (after "기존 내규 외규 타는 일반 로직을 그대로 들고와야해 … 수정해봐").
Same questions, generations, scope and transport as ADR-1504..1506 대사 cases. Targets go only to design/grading-only.json.

usage: setup.py"""
from common import *
import shutil,sqlite3
DES.mkdir(parents=True,exist_ok=True)
assert not (DES/'freeze.json').exists(),'already frozen'
rel=lambda p:str(Path(p).relative_to(ROOT))
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
BASE_ID='failure-answers-20261112-r1'
manifest_path=ROOT/'08_DEPLOYMENT/RELEASES'/BASE_ID/'release.json';release=read(manifest_path)
B=ROOT/release['code_root'];files=release['files']
bad=[n for n,h in files.items() if sha(B/n)!=h];assert not bad,('release code changed',bad[:5])
put(DES/'code-baseline.json',{'release_id':BASE_ID,'release_manifest':rel(manifest_path),'release_manifest_sha256':sha(manifest_path),'code_root':rel(B),
    'files':files,'selected_pointer_at_freeze':pointer,'is_selected_main':pointer['release_id']==BASE_ID,'flow':'internal-first (legacy)'})
S=ROOT/'09_ARTIFACTS/AUDITS/20261112-compare-failure-points/staged7'
cand={n:sha(S/n) for n in files}
changes=['compare-general-flow','compare-general-flow-manifest-basis','compare-general-flow-manifest-docflow']
for name in changes:
    for row in read(ROOT/'09_ARTIFACTS/CODE_CHANGES'/name/'change.json')['files']:
        assert cand[row['path']]==row['sha256'],('candidate differs from the named change',name,row['path'])
cmanifest={'release_id':'candidate-compare-general-flow','base_release':BASE_ID,'code_root':rel(S),'files':cand,'named_changes':changes}
put(DES/'candidate-release.json',cmanifest)
put(DES/'code-candidate.json',{'release_id':'candidate-compare-general-flow','release_manifest':rel(DES/'candidate-release.json'),
    'release_manifest_sha256':sha(DES/'candidate-release.json'),'code_root':rel(S),'files':cand,'named_changes':changes,
    'changed_from_baseline':sorted(n for n in files if cand[n]!=files[n]),'flow':'general-questions-v1'})
assert read(S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['comparison_flow']=='general-questions-v1'
assert 'comparison_flow' not in read(B/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')
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
cells=[{'case':c['id'],'arm':arm} for c in cases for arm in ('baseline','candidate')]
put(DES/'cases.json',cases);put(DES/'cells.json',cells);put(DES/'grading-only.json',grades)
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12, ADR-1504..1506); 실험한번해줘 (2026-11-12)',
    'earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json'],'generations':gens,
    'scope':'every document of the request team scope in the frozen generations; targets are never sent'})
criteria={
 'question':'Does the general-question 대사 put the right external articles into the comparison table more often than the internal-first flow, at what cost?',
 'hypothesis':'candidate (each side an ordinary question, rows paired from both sides) places the target articles in the table at least as often as baseline and leaves fewer read external originals out of the table, within its own limits (48 model calls, 1200 s).',
 'primary':['per case: each grading target (document + article) appears in a table row on its side (row internal/external sources)',
            'per case: read external originals left out of every table row (UNPLACED failure point count)',
            'per case: rows with both sides, rows marked related/gap candidate; final status (completed/partial/failed) and HTTP status'],
 'secondary':['physical calls, unknown outcomes, request seconds, model seconds, non-model seconds, process CPU seconds',
              'failure points (kinds, titles) and duplicate request: same answer, no extra model call'],
 'success':'candidate places >= baseline targets in total and has fewer unplaced external originals in total, with no case where it ends failed/HTTP>=500 that baseline answered, and every candidate request within 48 model calls and 1200 s.',
 'refute':'candidate places fewer targets in total, or ends failed/HTTP>=500 where baseline answered, or exceeds its limits.',
 'limits':{'physical_total':320,'per_request':64,'per_physical_seconds':180,'reported_cost_usd':6,'time_box_minutes':150,'workers':1,
           'ram_start_gib':4.5,'wait_seconds':1800},
 'order':'cells interleaved per case (baseline then candidate), one process each, sequential (no other heavy work).',
 'stop':'An unknown provider outcome stops that request (no automatic resend). The run stops on the operator stop file, two consecutive runner/resource failures before an answer, the budget or the time box.',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting); no local vector publication for these documents, so body search (no retriever).',
 'grading':'golden article match on the table by the experiment script (no model judge); semantic correctness of verdicts is read by hand and reported as observation only.',
 'quality_certified':False,'in_sample':True,'repeats':1,'decision_eligible':False}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ('common.py','live.py','run_all.sh','resource_guard.py','pinned_imports.py','setup.py','collect.py')),
        *(DES/n for n in ('code-baseline.json','code-candidate.json','candidate-release.json','provider-policy.json','generations.json','cases.json','cells.json',
                          'authorization.json','criteria.json','grading-only.json')),
        ART/'transport/transport-pins.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
print('frozen: baseline',BASE_ID,'candidate staged7;',len(cells),'cells; risk',len(risk),'liq',len(liq),'docs')
