"""Read-only independent audit of actual model choices and exact source text."""
import hashlib,json,sqlite3,sys
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0488-qwen-source-tiers-v4-paired'
def read(p):return json.loads(p.read_text())
def th(s):return hashlib.sha256(s.encode()).hexdigest()
def main():
 from run_probe import pin
 pin()
 from semantic_runtime.storage import Store
 from semantic_runtime.legal_agent.source_tiers_ui import SCRIPT
 store=Store(R/read(A/'product-cases.json')['generation'])
 audits=[]
 for run in ['run-001','run-002']:
  assert read(A/'artifacts'/run/'results.json').get('finished_at')
  for path in sorted((A/'artifacts'/run).glob('cm-*/source-tiers-v4/result.json')):
   row=read(path);bundle=row.get('result',{}).get('assembly',{}).get('term_agent',{}).get('source_bundle',{});trace=read(path.with_name('trace.json'));cards=[]
   with sqlite3.connect('file:'+str(path.with_name('journal.sqlite'))+'?mode=ro',uri=True) as db:
    for c in bundle.get('sources',[]):
     payload=db.execute("SELECT v.payload_json FROM entity_version v JOIN entity_head h USING(kind,entity_id,version) WHERE h.kind='source_selection' AND h.entity_id=? AND h.validity='CURRENT'",(c['selection_id'],)).fetchone()
     checks={'current_selection':payload is not None};payload=json.loads(payload[0]) if payload else {}
     view=db.execute('SELECT body_json FROM model_view WHERE view_id=?',(c['view_id'],)).fetchone();view=json.loads(view[0]) if view else {}
     checks['successful_model_view']=bool(db.execute("SELECT 1 FROM model_attempt WHERE view_id=? AND status='SUCCEEDED'",(c['view_id'],)).fetchone())
     offered={s['span_id']:s for s in view.get('selectable_spans',[])}
     for j,sp in enumerate(c['spans']):
      raw=store.source(c['document_id'],sp['block_id']);visible=offered.get(sp['span_id'],{})
      checks[f'span_{j}_actual_text']=raw['text'][sp['start_cp']:sp['end_cp']]==sp['text']
      checks[f'span_{j}_source_hash']=th(raw['text'])==sp['block_hash'] and th(sp['text'])==sp['span_hash'] and raw['source_artifact_sha256']==c['source_artifact_hash']
      checks[f'span_{j}_presented_range']=all(visible.get(k)==sp[k] for k in ['span_id','block_id','start_cp','end_cp']) and visible.get('evidence_id')==c['evidence_id']
     checks['explicit_model_choice']=all(payload.get(k)==c[k] for k in ['evidence_id','tier','interpretation_status','relevance_reason']) and [s['span_id'] for s in c['spans']]==payload.get('basis_span_ids')
     checks['exact_excerpt']=c['excerpt']=='\n'.join(s['text'] for s in c['spans'])
     actual=store.db.execute('SELECT name,source_artifact_sha256 FROM document WHERE document_id=?',(c['document_id'],)).fetchone();checks['exact_metadata']=tuple(actual)==(c['document_name'],c['source_artifact_hash'])
     cards.append({'selection_id':c['selection_id'],'document_name':c['document_name'],'coordinate':c['coordinate_label'],'tier':c['tier'],'interpretation_status':c['interpretation_status'],'checks':checks,'passed':all(checks.values())})
    views=[json.loads(x[0]) for x in db.execute("SELECT DISTINCT v.body_json FROM model_view v JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'")]
    menu_families=Counter(x.get('family') for v in views for x in v.get('relation_menu',[]));continuations=sum(bool(v.get('continuations')) for v in views)
   audit={'run_id':run,'case_id':row['case_id'],'cards':cards,'bundle_hash':bundle.get('bundle_hash'),'publication':row.get('publication_status'),'successful_view_menu_families':dict(menu_families),'views_with_continuations':continuations,'claims':len(row.get('result',{}).get('answer',{}).get('claims',[]))}
   audits.append(audit)
   # Explicitly labelled offline rendering, not a successful API response.
   result_json=json.dumps(bundle,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
   html='<!doctype html><html lang="ko"><meta charset="utf-8"><title>Qwen 내부 산출물 검토</title><style>body{font:16px sans-serif;max-width:1100px;margin:40px auto}article{border:1px solid #bbb;padding:18px;margin:12px 0}blockquote{white-space:pre-wrap}</style><h1>Qwen 내부 산출물 — '+run+' / '+row['case_id']+'</h1><p>실제 게시 상태: '+str(row.get('publication_status'))+' · 이 화면은 저장 결과의 로컬 오프라인 렌더링입니다. API 게시·원문 링크 성공을 뜻하지 않습니다.</p><div id="sources"></div><script>'+SCRIPT+'\nrenderSourceTiers('+result_json+');</script></html>'
   path.with_name('offline-payload-render.html').write_text(html)
 store.close()
 result={'schema_version':'qwen-source-independent-audit-v1','all_actual_cards_valid':all(c['passed'] for a in audits for c in a['cards']),'actual_card_count':sum(len(a['cards']) for a in audits),'rows':audits,'open_links':'Publication blocked sources have not passed API open; do not claim link success','gold_span_recall':'Not measured: frozen gold identifies article roots only'}
 p=A/'artifacts/source-integrity-audit.json';assert not p.exists();p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))
if __name__=='__main__':main()
