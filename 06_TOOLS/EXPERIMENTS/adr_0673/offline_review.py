"""Post-selection local gold coverage; no model calls or changes to answers."""
from pathlib import Path
import hashlib,json,sqlite3,statistics
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0673-investigation-chain-cm-six'
D=R/'09_ARTIFACTS/AUDITS/20261006-investigation-chain-cm-six'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
binding=read(A/'artifacts/design/bindings.json')
n=sqlite3.connect((R/binding['source_generation']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
sources={sid:json.loads(raw) for sid,raw in n.execute('select id,json from source')}
ledger=read(A/'artifacts/stage-ledger.json');m=read(A/'실험/manifest.json')
gold=read(A/'artifacts/offline-only/gold.json')['cases']
cases=[]
for c in gold:
 cid=c['id'];p=A/'artifacts/run-001'/cid;result=read(p/'result.json');diag=read(p/'diagnostic.json');audit=read(p/'chain-audit.json')
 acquired_ids=set()
 db=sqlite3.connect(next((p/'runtime/legal-agent').rglob('journal.sqlite')).resolve().as_uri()+'?mode=ro',uri=True)
 acquired_ids.update(x[0] for x in db.execute('select distinct source_id from evidence_unit'))
 acquired=[sources[x] for x in acquired_ids if x in sources]
 active_ids={x['source_id'] for x in result.get('output',{}).get('assembly',{}).get('term_agent',{}).get('law_navigation',{}).get('branches',[]) if x.get('status')=='ACTIVE'}
 spans={}
 for sid,bid,start,end in db.execute('select e.source_id,s.block_id,s.start_cp,s.end_cp from evidence_unit e join evidence_span s on s.evidence_id=e.evidence_id'):
  spans.setdefault((sid,str(bid)),[]).append((start,end))
 def covered(v):
  expected_chars=sum(len(b['text']) for b in v['blocks']);seen=0
  for b in v['blocks']:
   end=0
   for lo,hi in sorted(spans.get((v['id'],str(b['block_id'])),[])):
    hi=min(hi,len(b['text']));lo=max(lo,end,0)
    seen+=max(0,hi-lo);end=max(end,hi)
  return {'source_id':v['id'],'original_chars':expected_chars,'read_chars':seen,'full_original_covered':expected_chars>0 and seen==expected_chars}
 expected=c['expected_articles']+c.get('required_companions',[])
 checks=[]
 for e in expected:
  exact=[v for v in acquired if v['document_id']==e['doc_id'] and str(v['unit_id'])==str(e['node'])]
  same=[v for v in acquired if v['document_name']==e['law'] and v['heading'].split()[0]==e['article']]
  catalogue=[v for v in sources.values() if v['document_id']==e['doc_id'] and str(v['unit_id'])==str(e['node'])]
  checks.append({'law':e['law'],'article':e['article'],'gold_document_id':e['doc_id'],'gold_node':e['node'],
   'gold_version_available':bool(catalogue),'gold_version_text_matches':any(v.get('text_sha256')==e.get('source_text_sha256') for v in catalogue),
   'exact_gold_original_acquired':bool(exact),'same_law_article_original_acquired':bool(same),
   'same_law_article_full_original_covered':any(covered(v)['full_original_covered'] for v in same),
   'same_law_article_adopted':any(v['id'] in active_ids for v in same),
   'read_coverage':[covered(v) for v in same],
   'acquired_document_ids':sorted({v['document_id'] for v in same}),
   'version_note':'Same law/article coverage is separate from exact gold version; no current-law or quality certification.'})
 gold_identities=[{'doc_id':e['doc_id'],'node':int(e['node'])} for e in expected]
 gold_identities=sorted({canon(x):x for x in gold_identities}.values(),key=canon)
 lc=next(x for x in ledger['runs'][0]['arms'][0]['cases'] if x['case_id']==cid)
 lc.update(gold_total=len(gold_identities),gold_identities=gold_identities)
 g={canon(x) for x in gold_identities}
 for st in lc['stages']:
  before=[x for x in st['before'] if canon(x) in g];added=[x for x in st['added'] if canon(x) in g]
  discarded=[x for x in st['discarded'] if canon(x) in g];after=[x for x in st['after'] if canon(x) in g]
  receipts={canon(x['identity']):x['reason'] for x in st['discard_receipts']}
  st.update(gold_total=len(g),gold_before=len(before),gold_added=len(added),gold_discarded=len(discarded),gold_after=len(after),
   golden_recall=len(after)/len(g) if g else None,gold_before_identities=before,gold_added_identities=added,
   discarded_gold=[{'identity':x,'reason':receipts[canon(x)]} for x in discarded],gold_after_identities=after)
 row={'case_id':cid,'question':c['question'],'http_status':result['http_status'],'status':diag['status'],
  'request_seconds':diag['request_seconds'],'model_calls':diag['model_calls'],'decision_retries':diag['decision_retries'],
  'natural_return_actions':audit['natural_return_actions'],'history_preserved':audit['history_reasons_preserved_in_every_later_input'],
  'all_steps_visible_in_final_input':audit['all_steps_visible_in_final_input'],
  'exact_required_acquired':sum(x['exact_gold_original_acquired'] for x in checks),
  'same_law_article_required_acquired':sum(x['same_law_article_original_acquired'] for x in checks),'required_total':len(checks),
  'same_law_article_full_original_covered':sum(x['same_law_article_full_original_covered'] for x in checks),
  'same_law_article_adopted':sum(x['same_law_article_adopted'] for x in checks),
  'required_sources':checks,'reference_answer':c['reference_answer'],'actual_answer':diag['answer_text'],
  'answer_quality':'Not independently scored; inspect full answer against frozen reference and preserved source versions.'}
 put(p/'offline-review.json',row);cases.append(row)
 qp=A/'실험'/next(x['file'] for x in m['questions'] if x['case_id']==cid)
 with qp.open('a') as f:f.write('\n## 9. 실행 완료 후 로컬 기준 근거 대조 — 제품 입력 비공개\n\n```json\n'+json.dumps(row,ensure_ascii=False,indent=2)+'\n```\n')
 next(x for x in m['questions'] if x['case_id']==cid)['sha256']=sha(qp)
arm=ledger['runs'][0]['arms'][0]
total_gold=sum(x['gold_total'] for x in arm['cases']);present_gold=sum(x['stages'][-1]['gold_after'] for x in arm['cases'])
arm['aggregate']['gold_total']=total_gold
ledger['audit']['gold']='Frozen CMv3 exact document+article coordinates joined locally after every product selection completed; drift separately reported.'
ledger['audit']['present']='All original previews/pages delivered to navigation; presence is not full-original acquisition or adoption.'
ledger.pop('artifact_sha256');ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(A/'artifacts/stage-ledger.json',ledger)
m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'artifacts/stage-ledger.json')
m['retrieval_accounting']['golden_recall']={'chain-cm-six':present_gold/total_gold if total_gold else None}
m['results']['by_arm']['chain-cm-six']['offline_required_coverage']=cases
m['results']['by_arm']['chain-cm-six']['answer_quality']=None
m['results']['latency']['p50_request_seconds']=statistics.median(x['request_seconds'] for x in cases)
m['results']['latency']['p95_request_seconds']=max(x['request_seconds'] for x in cases)
put(A/'실험/manifest.json',m)
put(A/'artifacts/offline-review.json',{'gold_visible_to_product':False,'offline_model_calls':0,'cases':cases})
put(D/'offline-review.json',{'cases':cases,'main_wiring':'unchanged','genos_deployed':False})
lines=['CM 추가 6사례 실제 실행 및 로컬 근거 대조','', '기준답변과 좌표는 제품 입력에서 제외. 독립 모델 정답 채점 없음. MAIN/GENOS 불변.',
 '일부 원문 접촉은 해당 조문에 속한 원문 span이 확보됐다는 뜻이며, 전체 조문 읽기나 최종 채택을 뜻하지 않는다. 전체 확보는 저장된 모든 원문 block의 span 합집합으로 별도 계산한다.','']
for x in cases:
 lines += [x['case_id']+' '+x['question'],f"HTTP {x['http_status']} / {x['request_seconds']:.1f}초 / 모델{x['model_calls']}회 / 선택 보정{x['decision_retries']}회",
  f"필수 조문 일부 원문 접촉(동일 법령·조문): {x['same_law_article_required_acquired']}/{x['required_total']}; 전체 원문 확보: {x['same_law_article_full_original_covered']}/{x['required_total']}; 최종 근거 채택: {x['same_law_article_adopted']}/{x['required_total']}; 정확 골든 버전 일부 접촉: {x['exact_required_acquired']}/{x['required_total']}",
  f"행동 이유 유지: {x['history_preserved']} / 실제 복귀: {x['natural_return_actions']}회",'', '실제 답변:',x['actual_answer'] or '[답변 생성 실패]','', '동결 기준답변:',x['reference_answer'],'']
(D/'사례별답변과근거대조.txt').write_text('\n'.join(lines)+'\n')
print(json.dumps([{k:x[k] for k in ['case_id','http_status','request_seconds','model_calls','same_law_article_required_acquired','required_total','history_preserved','natural_return_actions']} for x in cases],ensure_ascii=False))
