from pathlib import Path
import json,sqlite3,gzip
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0876-original-coverage-scope-probe';O=A/'artifacts/run-001';read=lambda p:json.loads(p.read_text())
for case in ('committee-comparison','withdrawal'):
 P=O/case
 if not (P/'result.json').exists():continue
 calls=[]
 for p in sorted((P/'raw').glob('*/request.json')):
  req=read(p);response=p.with_name('response.json');value={}
  if response.exists():
   rv=read(response);value=json.loads(rv['choices'][0]['message']['content'])
  messages=req['messages'];text=messages[-1]['content'];view=json.loads(text).get('view',{})
  calls.append({'call':p.parent.name,'reading_progress':view.get('reading_progress'),'next_action':value.get('next_action'),'target_id':value.get('target_id'),
   'reason':value.get('reason'),'has_article8_items':'위험관리조직 구조 및 업무 분장' in text,
   'has_article8_proviso':'제4호 및 제5호' in text,'focused_issue':view.get('comparison_focus',{}).get('issue'),
   'field_review_count':len(view.get('comparison_focus',{}).get('field_reviews',[]))})
 body=read(P/'response.json').get('body',{});result=read(P/'result.json')
 out={'case':case,'status':result.get('status'),'http_status':result.get('http_status'),'model_calls':result['model_calls'],'calls':calls,'report_rows':body.get('report',{}).get('rows',[]),'error_code':body.get('error_code'),'answer':body.get('answer')}
 (P/'flow-observation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in out.items() if k not in ('answer','report_rows')},ensure_ascii=False));print(json.dumps(out['report_rows'],ensure_ascii=False))
