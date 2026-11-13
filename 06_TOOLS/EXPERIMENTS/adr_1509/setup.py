"""Freeze one full CM run on the selected MAIN (ADR-1509; template ADR-1505).

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
# Transport (experiment client) pins: the same bytes as ADR-1503.
src=ROOT/'04_EXPERIMENTS/ADR/ADR-1503-main212-special-external-liquidity-qwen/artifacts/transport'
pins=read(src/'transport-pins.json')
for name,h in pins['files'].items():
 t=ART/'transport'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/name,t);assert sha(t)==h==sha(ROOT/name),name
shutil.copyfile(src/'transport-pins.json',ART/'transport/transport-pins.json')
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
# 1. financial CM 51 (standalone strings r2; same strings as ADR-1478/1481/1482/1504/1505; cm-050 now included).
qpath=ROOT/'09_ARTIFACTS/AUDITS/20261109-cm-standalone-questions/질문_독립형_51_r2.json'
rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json'
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
fin=team_docs(GEN['main'],'financial_team')
for q in read(qpath)['cases']:
 r=registry[q['id']];assert q['source_question']==r['provenance']['source_question']
 cases.append({'id':q['id'],'kind':'cm','generation':'main','team':'financial_team','mode':'외규','question':q['standalone_question'],'document_ids':fin,'vector':True})
 grades.append({'id':q['id'],'kind':'cm','reference_answer':r['reference_answer'],'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','doc_id')} for t in r['targets']]})
# 2. every risk_cm question (105). Mode by the recorded scope assessment.
risk=team_docs(GEN['main'],'risk_team')
for q in read(ROOT/'01_DATA/GOLDEN/risk_cm/v2/questions.json')['cases']:
 st=q['scope_assessment']['status']
 mode='외규' if st in ('external_only','external_partial') else '전체 법령'
 cases.append({'id':q['id'],'kind':'risk','generation':'main','team':'risk_team','mode':mode,'question':q['question'],'document_ids':risk,'vector':False})
 grades.append({'id':q['id'],'kind':'risk','scope_assessment':q['scope_assessment'],'team':q['team'],'transcription':q['transcription'],'duplicate_of':q['duplicate_of']})
assert len({c['id'] for c in cases})==len(cases)
# risk first: its requests have the longest tail, so the queue does not end on one of them.
order={'risk':0,'cm':1};cases.sort(key=lambda c:order[c['kind']])
put(DES/'cases.json',cases);put(DES/'grading-only.json',grades)
put(DES/'authorization.json',{'user_instruction':'우리 현제 메인으로 젠체 cm 들 다 돌려줘 대사는뺴고 / risk,financial 둘다 싹다 진행 (2026-11-12); 외부에 모든 문서를 쏴도 됨 (2026-11-12, ADR-1504)','earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json','01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','01_DATA/GOLDEN/risk_cm/EXPORT_AUTHORIZATION_20261024.json'],
 'generations':gens,'scope':'every document of the request team scope in the frozen generations; reference answers and targets are never sent'})
criteria={'question':'Every CM question (financial 51, risk_cm 105) on the selected MAIN: what fails structurally (errors, unknown provider outcomes, unanswered requests, unread required articles, abnormal non-model time/CPU)?',
 'primary':['financial CM: registered required articles acquired/cited (golden article match, no judge) and requests without an answer',
            'risk_cm: answered / clarified / error, error codes (no approved answers exist; question_only)',
            'Every request: physical calls, unknown outcomes, model seconds vs non-model seconds, process CPU seconds, peak RSS'],
 'limits':{'physical_total':2000,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':15,'time_box_minutes':600,'workers':2,
           'ram_start_gib':4.5,'wait_seconds':1800,'c_drive_floor_gib':15,'workspace_floor_gib':20},
 'provider_rerun':'After the queue, every request whose run had a provider failure (unknown/blank/5xx, STOP file in the case folder) runs once more alone; that result counts and both are kept.',
 'stop':'An unknown provider outcome stops that request (no automatic resend). A worker stops after three consecutive requests with unknown calls and no answer, two consecutive runner/resource failures before an answer, the budget, the time box or a disk floor.',
 'storage':'After each request process exits, its runtime folder (local SQLite records, about 100-300MB) is packed into runtime.tar.gz with a per-file SHA256 receipt, verified by re-reading, then the folder is removed (lossless; restore = extract the archive).',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting). CM: vectors from the Oracle Gold bge-m3 items of the 21 Gold documents (local bge-m3 endpoint), body search over the whole scope. risk: no vector publication exists locally for those documents, so the product falls back to body search (no retriever).',
 'scope':'Whole team scope (all documents may be sent). Same scope and question strings as ADR-1504/1505 for the overlapping 50 CM and 20 risk questions; MAIN differs (219 vs 217).',
 'quality_certified':False,'in_sample':True,'parent':a.parent}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ("common.py","live.py","batch.py","rerun.py","resource_guard.py","pinned_imports.py","oracle_local.py","setup.py","archive_runtime.py")),*(DES/n for n in ('code.json','provider-policy.json','generations.json','cases.json','authorization.json','criteria.json','grading-only.json','oracle-gold.json')),
        ART/'transport/transport-pins.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
from collections import Counter
print('frozen',a.release_id,len(files),'files;',dict(Counter(c['kind'] for c in cases)),dict(Counter(c['mode'] for c in cases)),'cases; fin',len(fin),'risk',len(risk))
