"""Freeze one accuracy run of a staged candidate (MAIN219 + 2026-11-12 fixes): financial CM 51 and risk_ext_edge v2 20.

User 2026-11-12: "아래 수정해서 전체 정답률 뽑아봐" (F1 entry quotes, F2 delegated lower rules, F3 law-name-less
article names in the question, F4 menu-title reads, F6 "용어(약칭)" abbreviations, F9 answer guidance, numbered
follow-up cards). Same data generation, scopes, modes, guard and provider fallback transport as ADR-1509/1516/1518;
only the code differs (the staged candidate tree, every file hash frozen here).

usage: ADR_TARGET=<n> setup.py <base_release_id> --code-root <staged dir> --candidate <name> [--parent ADR-xxxx]
"""
from common import *
import shutil,sqlite3,argparse
ap=argparse.ArgumentParser();ap.add_argument('release_id');ap.add_argument('--code-root',required=True);ap.add_argument('--candidate',required=True);ap.add_argument('--parent',default=None);a=ap.parse_args()
DES.mkdir(parents=True,exist_ok=True)
assert not (DES/'freeze.json').exists(),'already frozen'
rel=lambda p:str(Path(p).relative_to(ROOT))
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
manifest_path=ROOT/'08_DEPLOYMENT/RELEASES'/a.release_id/'release.json';release=read(manifest_path)
C=ROOT/a.code_root
files={str(f.relative_to(C)):sha(f) for f in sorted(C.rglob('*')) if f.is_file() and '__pycache__' not in f.parts}
base=release['files'];changed=sorted(n for n,h in files.items() if base.get(n)!=h)
put(DES/'code.json',{'release_id':'candidate:'+a.candidate,'base_release':a.release_id,'release_manifest':rel(manifest_path),'release_manifest_sha256':sha(manifest_path),
 'code_root':rel(C),'files':files,'changed_from_base':changed,'selected_pointer_at_freeze':pointer,'is_selected_main':False,
 'isolation':'staged candidate tree (main_release stage), every file hash checked before and after each request'})
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
# 1. financial CM 51 (standalone strings r2; same as ADR-1509/1516).
qpath=ROOT/'09_ARTIFACTS/AUDITS/20261109-cm-standalone-questions/질문_독립형_51_r2.json'
rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json'
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
fin=team_docs(GEN['main'],'financial_team')
for q in read(qpath)['cases']:
 r=registry[q['id']];assert q['source_question']==r['provenance']['source_question']
 cases.append({'id':q['id'],'kind':'cm','generation':'main','team':'financial_team','mode':'외규','question':q['standalone_question'],'document_ids':fin,'vector':True})
 grades.append({'id':q['id'],'kind':'cm','reference_answer':r['reference_answer'],'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','doc_id')} for t in r['targets']]})
# 2. risk_ext_edge v2 20 (same as ADR-1518).
risk=team_docs(GEN['main'],'risk_team')
for q in read(ROOT/'01_DATA/GOLDEN/risk_ext_edge/v2/questions.json')['cases']:
 assert all(e['document_id'] in risk for e in q['required_evidence']),('evidence outside the risk scope',q['id'])
 cases.append({'id':q['id'],'kind':'edge','generation':'main','team':'risk_team','mode':'외규','question':q['question'],'document_ids':risk,'vector':False})
 grades.append({'id':q['id'],'kind':'edge','reference_answer':q['reference_answer'],'answer_traps':q['answer_traps'],'target_weakness':q['target_weakness'],
                'connection_hops':q['connection_hops'],'connection_chain':q['connection_chain'],'required_evidence':q['required_evidence']})
assert len(cases)==71 and len({c['id'] for c in cases})==71
# edge first (no vectors; longest tail), then CM.
order={'edge':0,'cm':1};cases.sort(key=lambda c:order[c['kind']])
put(DES/'cases.json',cases);put(DES/'grading-only.json',grades)
put(DES/'authorization.json',{'user_instruction':'아래 수정해서 전체 정답률 뽑아봐 (2026-11-12, staged candidate); 우리 risk쪽 질문은 이걸로 대체하자 만든거 전체다 (2026-11-12, risk_ext_edge v2); 가로 해보자 (2026-11-12, ADR-1509 continuation with provider fallback; new providers in the fallback list receive the same documents); 우리 현제 메인으로 젠체 cm 들 다 돌려줘 대사는뺴고 / risk,financial 둘다 싹다 진행 (2026-11-12); 외부에 모든 문서를 쏴도 됨 (2026-11-12, ADR-1504)','earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json','01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','01_DATA/GOLDEN/risk_cm/EXPORT_AUTHORIZATION_20261024.json'],
 'generations':gens,'scope':'every document of the request team scope in the frozen generations; reference answers and targets are never sent'})
criteria={'question':'Staged candidate (MAIN219 + 2026-11-12 fixes) on financial CM 51 and risk_ext_edge v2 20: required articles acquired/cited and answers vs ADR-1509/1516/1518 on MAIN219.',
 'primary':['CM: required articles acquired/cited (golden article match, no judge); MAIN219 baseline 83/98 acquired, 65/98 cited (ADR-1509+1516)',
            'risk_ext_edge: required evidence articles acquired/cited and operator review against reference/traps; MAIN219 baseline correct 7/20, acquired 28/56, cited 21/56 (ADR-1518)',
            'Every request: physical calls, provider switches, model vs non-model seconds, CPU, peak RSS; follow-up cards (unused originals with reasons, numbered unread connections)'],
 'success_hint':'Set before the run (user plan): edge correct >=10/20, CM cited >=75/98 (acquired >=88/98), at most one previously correct question regresses, extra physical calls <= +2 per question on average.',
 'limits':{'physical_total':1200,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':10,'time_box_minutes':360,'workers':2,
           'ram_start_gib':4.5,'wait_seconds':1800,'c_drive_floor_gib':15,'workspace_floor_gib':20},
 'transport':'provider fallback: design/fallback-policy.json (Near AI, CoreWeave, Chutes, Reka, Parasail; same model, reasoning none, no output cap); streamed; switch on non-200, transport error, stream error, no non-blank content in 60 s, only blank content for 60 s, finish not stop, empty answer, reasoning output, echo mismatch; a complete answer with wrong JSON is not switched.',
 'workers':'two workers.',
 'provider_rerun':'After the queue, every request whose every fallback provider failed (STOP_EXTERNAL) or with a resource stop runs once more alone; that result counts and both are kept.',
 'stop':'An unknown provider outcome stops that request (no automatic resend). A worker stops after three consecutive requests with unknown calls and no answer, two consecutive runner/resource failures before an answer, the budget, the time box or a disk floor.',
 'storage':'After each request process exits, its runtime folder (local SQLite records, about 100-300MB) is packed into runtime.tar.gz with a per-file SHA256 receipt, verified by re-reading, then the folder is removed (lossless; restore = extract the archive).',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting). CM: vectors from the Oracle Gold bge-m3 items of the 21 Gold documents (local bge-m3 endpoint), body search over the whole scope. risk: no vector publication exists locally for those documents, so the product falls back to body search (no retriever).',
 'scope':'Whole team scope (all documents may be sent). Same scope and question strings as ADR-1504/1505 for the overlapping 50 CM and 20 risk questions; MAIN differs (219 vs 217).',
 'quality_certified':False,'in_sample':True,'parent':a.parent,'baseline_adrs':['ADR-1509','ADR-1516','ADR-1518']}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ("common.py","live.py","batch.py","rerun.py","resource_guard.py","pinned_imports.py","oracle_local.py","setup.py","archive_runtime.py")),*(DES/n for n in ('code.json','provider-policy.json','generations.json','cases.json','authorization.json','criteria.json','grading-only.json','oracle-gold.json','fallback-policy.json')),
        ART/'transport/transport-pins.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
from collections import Counter
print('frozen candidate',a.candidate,len(files),'files',len(changed),'changed;',dict(Counter(c['kind'] for c in cases)),'cases; fin',len(fin),'risk',len(risk))
