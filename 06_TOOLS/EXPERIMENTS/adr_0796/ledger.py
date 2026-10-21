"""Measured synthetic canonical-unit visibility ledger, never a product input."""
from pathlib import Path
import json,hashlib,gzip,sys,tempfile,subprocess,os,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0796-latest-document-pipeline-search';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');sys.path[:0]=[str(R/f['code_root']/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS')];sys.dont_write_bytecode=True
from test_search_selection import metadata_generation
from lawrag.pipeline.search_selection import plan,activate
from semantic_runtime.storage import Store
m=read(A/'실험/manifest.json');plans=m['design']['retrieval_stage_plan']['stages_by_arm']
with tempfile.TemporaryDirectory() as t:
 g=metadata_generation(Path(t),[('a','internal/모의준칙_20200101.docx',{}),('b','internal/모의준칙_20260101.docx',{})])
 with sqlite3.connect(g/'store.sqlite') as db:db.executemany('INSERT INTO source_unit VALUES (?,?)',[('a','1'),('b','1')])
 manifest=read(g/'manifest.json');manifest['store_sha256']=sha(g/'store.sqlite');put(g/'manifest.json',manifest)
 before=sha(g/'store.sqlite');base=R/read(D/'baseline.json')['manifest']['code_root']
 code="import json;from semantic_runtime.storage import Store;s=Store("+repr(str(g))+");print(json.dumps([dict(doc_id=r[0],node=int(r[1])) for r in s.db.execute('SELECT document_id,unit_id FROM source_unit ORDER BY document_id')]));s.close()"
 b=json.loads(subprocess.check_output([str(R/'.venv/bin/python'),'-c',code],env={**os.environ,'PYTHONPATH':str(base/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1'},text=True))
 p=plan(g,latest=True);activate(p)
 with Store(g) if hasattr(Store,'__enter__') else __import__('contextlib').closing(Store(g)) as s:
  s.selection.require_latest();c=[dict(doc_id=r[0],node=int(r[1])) for r in s.db.execute('SELECT document_id,unit_id FROM source_unit ORDER BY document_id')]
 assert b==[{'doc_id':'a','node':1},{'doc_id':'b','node':1}] and c==[{'doc_id':'b','node':1}] and sha(g/'store.sqlite')==before
 put(A/'artifacts/run-001/visibility.json',{'synthetic':True,'baseline':b,'selected':c,'source_unchanged':True,'code_root':f['code_root'],'baseline_code_root':str(base.relative_to(R)),'actual_selection_counts':p['counts'],'model_calls':0})
G=[{'doc_id':'b','node':1}];arms=[];metrics={k:{} for k in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')}
for arm,selected in [('baseline',b),('selected',c)]:
 before=[];stages=[]
 for i,after in enumerate([b,selected,selected]):
  bm={canon(x):x for x in before};am={canon(x):x for x in after};gm={canon(x):x for x in G};added=[am[k] for k in sorted(am.keys()-bm.keys())];discard=[bm[k] for k in sorted(bm.keys()-am.keys())];gb=[x for x in before if x in G];ga=[x for x in after if x in G];gain=[x for x in added if x in G];loss=[x for x in discard if x in G];reason='Superseded filename version'
  stages.append({**plans[arm][i],'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discard,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discard),'after_count':len(after),'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reason} for x in discard],'discard_reason_counts':{reason:len(discard)} if discard else {},'gold_total':1,'gold_before':len(gb),'gold_added':len(gain),'gold_discarded':len(loss),'gold_after':len(ga),'golden_recall':len(ga),'gold_before_identities':gb,'gold_added_identities':gain,'discarded_gold':[{'identity':x,'reason':reason} for x in loss],'gold_after_identities':ga});before=after
 case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':'S01','gold_total':1,'gold_identities':G,'stages':stages};arms.append({'arm_id':arm,'declared_stage_ids':[x['stage_id'] for x in plans[arm]],'cases':[case],'aggregate':{'cases':1,'presented_total':len(selected),'gold_total':1}})
 metrics['before_filter'][arm]=2;metrics['after_filter'][arm]=len(selected)
 for k in ('presented_total','presented_mean','presented_p50','presented_p95'):metrics[k][arm]=len(selected)
 metrics['golden_recall'][arm]=1;metrics['selectivity'][arm]=len(selected)/2
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'synthetic_technical_fixture':True,'legal_quality_gate':False,'presentation_means':'API-visible document source units, no LLM answer'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();p=A/'artifacts/run-001/retrieval-ledger.json.gz';p.write_bytes(gzip.compress(canon(ledger).encode(),mtime=0))
m['retrieval_accounting'].update(changed=True,corpus_total=2,not_applicable_reason=None,**metrics,stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(p.relative_to(R)),'sha256':sha(p),'not_applicable_reason':None})
headings=['1. 실행 메타','2. 사용자 질문 원문','3. 기준답변 — 채점 전용, 제품 입력 비공개','4. 제품 입력을 구성한 원값','5. 제품 모델 호출 — run·arm별 실제 원문','6. 중간 LLM 호출 — router/compiler/verifier/repair','7. 채점 호출과 반복 판정','8. 사례 최종 판정'];body=['S01 합성 문서 두 개의 기술 검사. 실제 규정/법률 정답 평가 아님.','최신으로 선택된 문서만 검색·탐색에 사용한다.','2026 문서 b는 유지, 2020 문서 a는 제외. 후처리 검증에만 사용.','파일명과 저장 문서 ID, source_unit 실제 좌표.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json.gz. 원문 2개 → 기준2/후보1개.','모델 호출 0건. 실제 MAIN72 Store와 동결 후보 Store의 SQL 가시성 결과를 비교.','호출 없음.','LLM 평가 없음. 결정적 포함 여부와 원본 해시를 검증.','최신 b 유지, 구버전 a 제외, DB 원본 불변. 실제 GENOS 수치는 미확인.']
p=A/'실험/질문-001-S01.md';p.write_text('\n\n'.join('## '+h+'\n\n'+v for h,v in zip(headings,body))+'\n');m['questions']=[{'number':1,'case_id':'S01','file':p.name,'sha256':sha(p)}];put(A/'실험/manifest.json',m);print(metrics)
