"""Freeze one full experiment run before any model call (ADR-1504 and its repeats).

One run = the financial CM 50 standalone questions (r2, cm-050 out of scope), 20 risk_cm questions the
external rules can answer, the 4 photo internal-rule questions and 3 comparison (대사) questions, each
through the frozen release's own service.py entry in a fresh process.

User 2026-11-12: "127에서 전체 financial team cm 질문 돌릴꺼야 / 공백만 준다거나 공급자쪽 문제는 다시
실험해야해 / 대사쪽도 실험해보고 / risk_team쪽도 실험해 / 외부에 모든 문서를 쏴도 됨 / 3번정도 실험을
하고 구조적으로 문제있는것들을 선별해서 코드를 알아서 수정해".

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
GEN={'main':'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation',
     'linked':'01_DATA/TERM_RELEASES/linked-documents-20261111-r1/generation',
     'liquidity':'01_DATA/TERM_RELEASES/liquidity-compare-20261111-r1/generation'}
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
# 1. financial CM 50 (standalone strings r2; same strings as ADR-1478/1481/1482).
qpath=ROOT/'09_ARTIFACTS/AUDITS/20261109-cm-standalone-questions/질문_독립형_51_r2.json'
rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json'
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
fin=team_docs(GEN['main'],'financial_team')
for q in read(qpath)['cases']:
 if q['id']=='cm-050':continue
 r=registry[q['id']];assert q['source_question']==r['provenance']['source_question']
 cases.append({'id':q['id'],'kind':'cm','generation':'main','team':'financial_team','mode':'외규','question':q['standalone_question'],'document_ids':fin,'vector':True})
 grades.append({'id':q['id'],'kind':'cm','reference_answer':r['reference_answer'],'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','doc_id')} for t in r['targets']]})
# 2. risk_cm questions the current external rules can answer (external_only 3 + external_partial 18, minus RISK-CM-101 whose transcription is incomplete).
risk=team_docs(GEN['main'],'risk_team')
for q in read(ROOT/'01_DATA/GOLDEN/risk_cm/v2/questions.json')['cases']:
 st=q['scope_assessment']['status']
 if st not in ('external_only','external_partial') or q['id']=='RISK-CM-101':continue
 cases.append({'id':q['id'],'kind':'risk','generation':'main','team':'risk_team','mode':'외규','question':q['question'],'document_ids':risk,'vector':False})
 grades.append({'id':q['id'],'kind':'risk','scope_assessment':q['scope_assessment'],'team':q['team']})
# 3. photo internal rules (ADR-1485/1487 questions, risk_team 내규).
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1487-main203-search-units-qwen/artifacts/design'
pg={g['id']:g for g in read(P/'grading-only.json')}
for c in read(P/'live-cases.json'):
 cases.append({'id':'photo-'+c['id'],'kind':'photo','generation':'linked','team':'risk_team','mode':'내규','question':c['steps'][0]['question'],'document_ids':sorted(c['document_ids']),'vector':False})
 grades.append({'id':'photo-'+c['id'],'kind':'photo','targets':pg[c['id']]['targets']})
# 4. comparison (대사).
liq=team_docs(GEN['liquidity'],None)
cmp=[('cmp-liquidity','liquidity','유동성비율 관련한 외부규정과 내부 규정은 어떻게 되나요?',liq,
      [{'side':'external','document':'금융투자업규정','article':'제3-24조의4'},{'side':'internal','document':'위험관리기준시행세칙','article':'제6-4조'}]),
     ('cmp-soundness','liquidity','건전성비율(순자본비율 등) 관련 외부규정과 내부규정을 비교해줘',liq,
      [{'side':'internal','document':'위험관리기준시행세칙','article':'제2-1조'}]),
     ('cmp-riskcommittee','main','위험관리위원회의 구성과 운영에 관한 외부규정과 내부규정을 비교해줘',risk,
      [{'side':'internal','document':'위험관리위원회운영준칙','article':None},{'side':'external','document':'금융회사의 지배구조에 관한 법률','article':'제21조'}])]
for cid,g,question,docs,targets in cmp:
 cases.append({'id':cid,'kind':'compare','generation':g,'team':'risk_team','mode':'대사','question':question,'document_ids':docs,'vector':False})
 grades.append({'id':cid,'kind':'compare','targets':targets})
assert len({c['id'] for c in cases})==len(cases)
# Long comparisons first so the queue does not end on a 7-minute request.
order={'compare':0,'photo':1,'cm':2,'risk':3};cases.sort(key=lambda c:order[c['kind']])
put(DES/'cases.json',cases);put(DES/'grading-only.json',grades)
put(DES/'authorization.json',{'user_instruction':'외부에 모든 문서를 쏴도 됨 (2026-11-12)','earlier':['01_DATA/RAW/internal/EXPORT_AUTHORIZATION_INTERNAL_20261111.json','01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','01_DATA/GOLDEN/risk_cm/EXPORT_AUTHORIZATION_20261024.json'],
 'generations':gens,'scope':'every document of the request team scope in the frozen generations; reference answers and targets are never sent'})
criteria={'question':'Full run on the frozen code: what fails structurally (errors, unknown provider outcomes, unanswered requests, wrong/unread required articles, abnormal non-model time/CPU)?',
 'primary':['CM: registered required articles acquired/cited (golden article match, no judge) and requests without an answer',
            'risk/photo: answered or clarified, targets read (photo), error codes','대사: completed/partial/failed, target articles in the table',
            'Every request: physical calls, unknown outcomes, model seconds vs non-model seconds, process CPU seconds'],
 'limits':{'physical_total':900,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':10,'time_box_minutes':300,'workers':3,
           'ram_start_gib':4.5,'wait_seconds':1800},
 'provider_rerun':'After the queue, every request whose run had a provider failure (unknown/blank/5xx, STOP file in the case folder) runs once more alone; that result counts and both are kept.',
 'stop':'An unknown provider outcome stops that request (no automatic resend). A worker stops after three consecutive requests with unknown calls and no answer, two consecutive runner/resource failures before an answer, the budget or the time box.',
 'initial_search':'GENOS_RAG_INITIAL_SEARCH=hybrid (field setting). CM: vectors from the Oracle Gold bge-m3 items of the 21 Gold documents (local bge-m3 endpoint), body search over the whole scope. risk/photo/대사: no vector publication exists locally for those documents, so the product falls back to body search (no retriever).',
 'scope':'Whole team scope (all documents may be sent, user 2026-11-12); earlier CM runs used the 44-document public grant, so CM numbers are not like-for-like with ADR-1478/1482.',
 'quality_certified':False,'in_sample':True,'parent':a.parent}
put(DES/'criteria.json',criteria)
frozen=[*(TOOLS/n for n in ('common.py','live.py','batch.py','rerun.py','resource_guard.py','pinned_imports.py','oracle_local.py','setup.py')),*(DES/n for n in ('code.json','provider-policy.json','generations.json','cases.json','authorization.json','criteria.json','grading-only.json','oracle-gold.json')),
        ART/'transport/transport-pins.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
put(DES/'freeze.json',{'files':{rel(p):sha(p) for p in frozen},'model_calls_before_freeze':0})
from collections import Counter
print('frozen',a.release_id,len(files),'files;',dict(Counter(c['kind'] for c in cases)),'cases; fin',len(fin),'risk',len(risk),'liq',len(liq))
