"""Auditable side-by-side view of the exact serving-selection plan; no JS."""
import csv,html,json
from pathlib import Path

def write_comparison(plan,out):
 out=Path(out);out.mkdir(exist_ok=True)
 all_rows=[{**loc,'document_id':doc['document_id'],'is_latest':doc['is_latest']} for doc in plan['latest_documents'] for loc in doc['locations']]
 retained=[r for r in all_rows if r['is_latest']]
 for name,rows in [('ALL_INTERNAL',all_rows),('RETAINED_INTERNAL',retained)]:
  with (out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.writer(f);w.writerow(['문서명','날짜'])
   for title,date in sorted({(r['title'],r['date']) for r in rows}):
    safe=lambda s:"'"+s if s.startswith(('=','+','-','@','\t','\r')) else s
    w.writerow([safe(title),safe(date)])
 esc=lambda x:html.escape(str(x))
 def table(rows):
  return '<table><tr><th>문서명</th><th>파일명 날짜</th><th>판정·근거</th></tr>'+''.join('<tr><td>'+esc(r['title'])+'</td><td>'+esc(r['date'] or '날짜 미확정')+'</td><td><details><summary>'+esc(r['status'])+' · is_latest='+str(r['is_latest']).lower()+'</summary>'+esc(r['reason'])+'<br>'+esc(r['path'])+'<br>ID: '+esc(r['document_id'])+'</details></td></tr>' for r in rows)+'</table>'
 page='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>최신 내규 선택 비교</title><style>body{font:15px system-ui;margin:24px;background:#f4f6f8;color:#182735}main{display:grid;grid-template-columns:1fr 1fr;gap:20px}section{padding:16px;background:white}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left;overflow-wrap:anywhere}summary{cursor:pointer}h1{font-size:24px}@media(max-width:900px){main{display:block}}</style><h1>전체 내규 ↔ 필터링 후 남은 내규</h1><p>같은 선택 계획의 전후 비교입니다. 실제 적용 상태는 STATUS.json의 phase와 selection_sha256으로 확인하세요. 날짜 미확정·검토 보존도 사유와 함께 유지하며 법률상 시행일 확인을 뜻하지 않습니다.</p>'''
 page+='<p>'+esc(json.dumps(plan['counts'],ensure_ascii=False))+'</p><p><a href="ALL_INTERNAL.csv">전체 문서명+날짜</a> · <a href="RETAINED_INTERNAL.csv">남은 문서명+날짜</a></p><main><section><h2>전체</h2>'+table(all_rows)+'</section><section><h2>남은 문서</h2>'+table(retained)+'</section></main></html>'
 (out/'COMPARE.html').write_text(page,encoding='utf-8');(out/'AUDIT.json').write_text(json.dumps({'counts':plan['counts'],'rows':all_rows,'exceptions':plan['exception_results']},ensure_ascii=False,indent=2)+'\n');return out/'COMPARE.html'
