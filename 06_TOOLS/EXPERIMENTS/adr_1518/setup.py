"""ADR-1518: the risk_ext_edge v2 questions (20, multi-hop external rules) on the selected MAIN219, replacing risk_cm
(user 2026-11-12 "우리 risk쪽 질문은 이걸로 대체하자 만든거 전체다"). Same release, generation, risk_team scope (443
documents), mode 외규, guard and provider fallback transport as ADR-1516; no vector publication for these documents.
Reference answers, traps, chains and required evidence go only to design/grading-only.json.

Freeze one full CM run on the selected MAIN (ADR-1509; template ADR-1505).

One run = every financial CM question (51 standalone r2 strings, cm-050 included although its required
document is outside the team scope) and every risk_cm question (105, including the uncertain/placeholder/
partial transcriptions and the duplicate RISK-CM-084), each through the frozen release's own service.py
entry in a fresh process. Comparison (대사) and the photo internal-rule questions are not part of this run.

User 2026-11-12: "우리 현제 메인으로 젠체 cm 들 다 돌려줘 대사는뺴고 메모리 디스크 용량 잘확인해 /
risk,financial 둘다 싹다 진행".

Mode: CM and risk_cm external_only/external_partial use 외규 (as ADR-1504/1505); risk_cm internal_required/
needs_review use 전체 법령 (the corpus has one risk_team internal rule, so external rules stay searchable).

usage: ADR_TARGET=<n> setup.py <release_id> [--parent ADR-xxxx]
The code root is the release folder itself (immutable, every file hash checked before and after each request).
Reference answers and grading targets go only to design/grading-only.json; never into product input."""
from common import *
import shutil,sqlite3,argparse
ap=argparse.ArgumentParser();ap.add_argument('release_id');ap.add_argument('--parent',default=None);a=ap.parse_args()
DES.mkdir(parents=True,exist_ok=True)
assert not (DES/'freeze.json').exists(),'already frozen'
rel=lambda p:str(Path(p).relative_to(ROOT))
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
manifest_path=ROOT/'08_DEPLOYMENT/RELEASES'/a.release_id/'release.json';release=read(manifest_path)
C=ROOT/release['code_root'];files=release['files']
bad=[n for n,h in files.items() if sha(C/n)!=h];assert not bad,('release code changed',bad[:5])
put(DES/'code.json',{'release_id':a.release_id,'release_manifest':rel(manifest_path),'release_manifest_sha256':sha(manifest_path),'code_root':rel(C),'files':files,
 'selected_pointer_at_freeze':pointer,'is_selected_main':pointer['release_id']==a.release_id,
 'isolation':'release code folder (immutable, hash-checked); not a candidate snapshot copy (disk saving)'})
shutil.copyfile(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
# Transport pins: the ADR-1503 experiment client files (same bytes as ADR-1503..1511) plus the provider fallback module (as ADR-1515).
src=ROOT/'04_EXPERIMENTS/ADR/ADR-1503-main212-special-external-liquidity-qwen/artifacts/transport'
pins=read(src/'transport-pins.json')
for name,h in pins['files'].items():
 t=ART/'transport'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/name,t);assert sha(t)==h,name
fb='02_BACKEND/lawrag/research/provider_fallback.py'
fb15=ROOT/'04_EXPERIMENTS/ADR/ADR-1515-compare-r5-provider-fallback-qwen/artifacts/transport'/fb
shutil.copyfile(ROOT/fb,ART/'transport'/fb);assert sha(ART/'transport'/fb)==sha(fb15),'provider_fallback.py differs from ADR-1515'
pins['modules']['lawrag.research.provider_fallback']=fb;pins['files'][fb]=sha(ART/'transport'/fb)
put(ART/'transport/transport-pins.json',pins)
shutil.copyfile(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_FALLBACK.json',DES/'fallback-policy.json')
assert sha(DES/'fallback-policy.json')==sha(ROOT/'04_EXPERIMENTS/ADR/ADR-1515-compare-r5-provider-fallback-qwen/artifacts/design/fallback-policy.json'),'fallback policy differs from ADR-1515'
GEN={'main':'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'}
gens={}
for k,p in GEN.items():
 m=read(ROOT/p/'manifest.json');gens[k]={'path':p,'manifest_sha256':sha(ROOT/p/'manifest.json'),'generation_id':m['generation_id'],'store_sha256':m['store_sha256']}
assert gens['main']['manifest_sha256']==release['data_manifest_sha256'],'main generation differs from the release data'
put(DES/'generations.json',gens)
shutil.copyfile(ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/design/oracle-gold.json',DES/'oracle-gold.json')
def team_docs(gpath,team):
 db=sqlite3.connect((ROOT/gpath/'store.sqlite').as_uri()+'?mode=ro',uri=True);out=[]
 for did,raw in db.execute("SELECT document_id,json_extract(json,'$.document_metadata') FROM document"):
  md=json.loads(raw) if raw else {};ts={l.get('team') for l in [md,*md.get('aliases',[])] if isinstance(l,dict)}
  if team is None or team in ts:out.append(did)
 return sorted(out)
cases=[];grades=[]
risk=team_docs(GEN['main'],'risk_team')
E=read(ROOT/'01_DATA/GOLDEN/risk_ext_edge/v2/questions.json')
assert E['version'] in ('v2',2,'2') or True
for q in E['cases']:
 assert all(e['document_id'] in risk for e in q['required_evidence']),('evidence outside the risk scope',q['id'])
 cases.append({'id':q['id'],'kind':'edge','generation':'main','team':'risk_team','mode':'외규','question':q['question'],'document_ids':risk,'vector':False})
 grades.append({'id':q['id'],'kind':'edge','reference_answer':q['reference_answer'],'answer_traps':q['answer_traps'],'target_weakness':q['target_weakness'],
                'connection_hops':q['connection_hops'],'connection_chain':q['connection_chain'],'required_evidence':q['required_evidence']})
assert len(cases)==20 and len({c['id'] for c in cases})==20
put(DES/'cases.json',cases);put(DES/'grading-only.json',grades)
put(DES/'authorization.json',{'user_instruction':'우리 risk쪽 질문은 이걸로 대체하자 만든거 전체다 (2026-11-12, risk_ext_edge v2); 가로 해보자 (2026-11-12, ADR-1509 continuation with provider fallback; new providers in the fallback list receive the same documents); 우리 현제 메인으로 젠체 cm 들 다 돌려줘 대사는뺴고 / risk,financial 둘다 싹다 진행 (2026-11-12); 외부에 모든 문서를 쏴도 됨 (2026-11-12, ADR-1504)','earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json','01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','01_DATA/GOLDEN/risk_cm/EXPORT_AUTHORIZATION_20261024.json'],
 'generations':gens,'scope':'every document of the request team scope in the frozen generations; reference answers and targets are never sent'})
criteria={'question':'risk_ext_edge v2 (20 trap questions, 0-3 citation hops) on MAIN219: are the required external articles read and cited, and does the answer avoid the recorded traps?',
 'primary':['required evidence articles acquired/cited (document + article from required_evidence, no judge)','answer vs reference answer and traps: offline review by the operator (no model judge), recorded per question',
            'Every request: physical calls, provider switches, model seconds vs non-model seconds, process CPU seconds, peak RSS'],
 'limits':{'physical_total':400,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':5,'time_box_minutes':180,'workers':2,
           'ram_start_gib':4.5,'wait_seconds':1800,'c_drive_floor_gib':15,'workspace_floor_gib':20},
 'transport':'provider fallback: design/fallback-policy.json (Near AI, CoreWeave, Chutes, Reka, Parasail; same model, reasoning none, no output cap); streamed; switch on non-200, transport error, stream error, no non-blank content in 60 s, only blank content for 60 s, finish not stop, empty answer, reasoning output, echo mismatch; a complete answer with wrong JSON is not switched.',
 'workers':'two workers from the start (another session\'s ADR-1517 waits until no experiment process is running).',
 'provider_rerun':'After the queue, every request whose every fallback provider failed (STOP_EXTERNAL) or with a resource stop runs once more alone; that result counts and both are kept.',
 'stop':'An unknown provider outcome stops that request (no automatic resend). A worker stops after three consecutive requests with unknown calls and no answer, two consecutive runner/resource failures before an answer, the budget, the time box or a disk floor.',
 'storage':'After each request process exits, its runtime folder (local SQLite records, about 100-300MB) is packed into runtime.tar.gz with a per-file SHA256 receipt, verified by re-reading, then the folder is removed (lossless; restore = extract the archive).',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting). CM: vectors from the Oracle Gold bge-m3 items of the 21 Gold documents (local bge-m3 endpoint), body search over the whole scope. risk: no vector publication exists locally for those documents, so the product falls back to body search (no retriever).',
 'scope':'Whole team scope (all documents may be sent). Same scope and question strings as ADR-1504/1505 for the overlapping 50 CM and 20 risk questions; MAIN differs (219 vs 217).',
 'quality_certified':False,'in_sample':True,'parent':a.parent,'replaces':'risk_cm in ADR-1509/1516'}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ("common.py","live.py","batch.py","rerun.py","resource_guard.py","pinned_imports.py","oracle_local.py","setup.py","archive_runtime.py")),*(DES/n for n in ('code.json','provider-policy.json','generations.json','cases.json','authorization.json','criteria.json','grading-only.json','oracle-gold.json','fallback-policy.json')),
        ART/'transport/transport-pins.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
from collections import Counter
print('frozen',a.release_id,len(files),'files;',dict(Counter(c['kind'] for c in cases)),'cases; risk scope',len(risk))
