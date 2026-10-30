"""Read-only per-case analysis and final report; no product/model invocation."""
from common import *
import csv,io,statistics,sqlite3,tarfile,tempfile,shutil,collections,sys,math
progress=read(RUN/'progress.json');cases=read(DES/'cases.json');questions={c['id']:c['request']['json']['question'] for c in cases}
rows=[]
for case in cases:
 P=RUN/case['id']
 if not (P/'audit.json').exists():continue
 a=read(P/'audit.json');body=(read(P/'response.json').get('body') or {}) if (P/'response.json').exists() else {};gs=read(P/'generations.json') if (P/'generations.json').exists() else []
 row={**a,'question':questions[case['id']],'failure_reason':body.get('failure_reason'),'gateway_message':body.get('message'),'generation_errors':[{'stage':g.get('stage'),'error':g.get('error')} for g in gs if not g.get('accepted',True)],'assessment_errors':[],'read_coordinates':[],'final_coordinates':[]}
 # Stream one archived journal at a time, never restore all51 runtimes together.
 arc=P/'runtime.tar.gz'
 if arc.exists():
  with tempfile.TemporaryDirectory(prefix='cm3-audit-',dir=ART) as tmp,tarfile.open(arc,'r:gz') as t:
   members=[m for m in t if m.name.endswith('/journal.sqlite')]
   for i,m in enumerate(members):
    dest=Path(tmp)/str(i);dest.mkdir();dbpath=dest/'journal.sqlite'
    with t.extractfile(m) as src,dbpath.open('wb') as out:shutil.copyfileobj(src,out)
    for suffix in ('-wal','-shm'):
     try:side=t.getmember(m.name+suffix)
     except KeyError:continue
     with t.extractfile(side) as src,(dest/('journal.sqlite'+suffix)).open('wb') as out:shutil.copyfileobj(src,out)
    db=sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True)
    for kind,payload in db.execute("SELECT kind,payload_json FROM event WHERE kind='COMPLETION_ASSESSMENT_REJECTED' OR kind='FINAL_REVIEW_INDEPENDENT_RESEARCH'"):
     row['assessment_errors'].append({'kind':kind,'payload':json.loads(payload)})
    sourceids=[x[0] for x in db.execute('SELECT DISTINCT source_id FROM evidence_unit')];db.close()
    nav=sqlite3.connect((ROOT/read(DES/'baseline.json')['release']['data_path']/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
    for sid in sourceids:
     found=nav.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()
     if found:
      src=json.loads(found[0]);coord=src.get('article_coordinate') or {};did=coord.get('doc_id',src.get('document_id'));node=coord.get('node',src.get('unit_id'))
      if did and str(node).isdigit():row['read_coordinates'].append({'doc_id':did,'node':int(node)})
    ids={s for c in (body.get('answer') or {}).get('claims',[]) for s in c.get('source_ids',[])}
    for sid in ids:
     found=nav.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()
     if found:
      src=json.loads(found[0]);coord=src.get('article_coordinate') or {};did=coord.get('doc_id',src.get('document_id'));node=coord.get('node',src.get('unit_id'))
      if did and str(node).isdigit():row['final_coordinates'].append({'doc_id':did,'node':int(node)})
    nav.close()
 for key in ('read_coordinates','final_coordinates'):row[key]=[json.loads(x) for x in sorted({json.dumps(v,sort_keys=True) for v in row[key]})]
 if a['response_with_claims']:row['outcome']='LIMITED_ANSWER' if (a.get('accepted_outcome') or {}).get('disposition')=='LIMITED_ANSWER' else 'ANSWER_WITH_CLAIMS'
 elif a['http_status']==200:row['outcome']='CLARIFY_OR_NO_CLAIMS'
 elif a['http_status']==422:row['outcome']='REVIEW_INCOMPLETE'
 elif a['status']=='interrupted':row['outcome']='INTERRUPTED_OR_UNKNOWN'
 else:row['outcome']='TECHNICAL_FAILURE'
 put(P/'analysis.json',row);rows.append(row)
counts=dict(collections.Counter(r['outcome'] for r in rows));lat=[r['elapsed_seconds'] for r in rows if r.get('elapsed_seconds') is not None];usage=[u for r in rows for u in r.get('usage',[])];total={'total':3,'completed':len(rows),'active':progress.get('active'),'outcomes':counts,'model_calls':sum(r['model_calls'] for r in rows),'source_mismatches':sum(r['source_mismatches'] for r in rows),'acl_violations':sum(r['acl_violations'] for r in rows),'claim_ref_violations':sum(not x['valid_refs'] for r in rows for x in r['final_claim_links']),'legal_accuracy':'not_scored','quality_certified':False,'elapsed_sum_seconds':sum(lat),'p95_method':'nearest_rank','p50_seconds':statistics.median(lat) if lat else None,'p95_seconds':sorted(lat)[math.ceil(.95*len(lat))-1] if lat else None,'usage':{k:sum(u.get(k) or 0 for u in usage) for k in ('input_tokens','output_tokens','total_tokens','cost_usd')},'MAIN':'isolated ADR1167 (MAIN112 base)' ,'source_documents':len(read(DES/'corpus.json')['document_ids']),'reference_answers_in_product':False,'risk_cm_excluded':True}
put(RUN/'summary.json',total)
with (RUN/'결과목록.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['문항','질문','상태','HTTP','주장수','모델호출','전체초','모델초','실패이유','원문불일치','답변파일'])
 for r in rows:w.writerow([r['case_id'],r['question'],r['outcome'],r['http_status'],r['claim_count'],r['model_calls'],r['elapsed_seconds'],r['model_seconds'],r['failure_reason'],r['source_mismatches'],str((RUN/r['case_id']/'answer.txt').relative_to(ROOT))])
text=['ADR1168 CM3 Qwen 수정본 실행 결과',json.dumps(total,ensure_ascii=False,indent=2),'MAIN112 후보의 공개원문65개 허용범위를 유지했다. CM질문은 사용자반출승인으로만 전송했고 공개질문으로 표시하지 않았다. 정답좌표/기준답변은 제품입력에 넣지 않았다. ADR1167 보완 감시 코드을 실행했고 모델·데이터·예산은 유지했다. 법률정답률은 이번 실행에서 채점하지 않았다.']
for r in rows:
 P=RUN/r['case_id'];answer=(P/'answer.txt').read_text() if (P/'answer.txt').exists() else ''
 text += ['\n'+r['case_id']+' | '+r['outcome']+' | 모델'+str(r['model_calls'])+'회',r['question'],'답변: '+(answer or r['gateway_message'] or str(r['error'])),'원기록: '+str(P)]
(RUN/'전체답변과_실행결과.txt').write_text('\n\n'.join(text)+'\n')
print(json.dumps(total,ensure_ascii=False))
