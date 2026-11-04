from common import *
rows=[]
for d in sorted((ART/'public-live').glob('*')):
 if not (d/'result.json').exists():continue
 r=read(d/'result.json');calls=read(d/'calls.json');turns=r.get('turns',[])
 row={'cell':d.name,'case_id':r['case_id'],'provider':d.name.rsplit('-',1)[1],'semantic_pass':False,'http_status':turns[0]['http_status'] if turns else None,'status':turns[0]['status'] if turns else None,'claims':sum(t['claims'] for t in turns),'physical_calls':len(calls),'seconds':sum(t['request_seconds'] for t in turns),'unknown':r.get('unknown',0)}
 if row['status']=='CLARIFY':
  raw=read(d/'raw/call-001/response.json.gz');out=json.loads(raw['choices'][0]['message']['content']);scope=out['search']['scope_decision']
  selection=scope['targets'][0]['selection'];row.update(error='MODEL_OMITTED_ARTICLE_PARENT',selection=selection,explanation='명시된 제365조 제1항을 unit항/include1/parent_path[]로 제안하여 범위 고유해석 실패; 보완 없이 CLARIFY 반환')
 elif row['unknown']:
  failed=next(c for c in calls if c['status']=='unknown');diag=failed.get('transport_diagnostics',{});row.update(error='PROVIDER_UNKNOWN_BEFORE_READ',failed_stage=failed.get('stage'),received_bytes=diag.get('received_bytes'),received_chunks=diag.get('received_chunks'),whitespace_only=diag.get('whitespace_only'),worker_reaped=diag.get('worker_reaped'),explanation='명시434 탐색에서 원문 선택 모델 호출 미완료. 로컬 worker회수, 원격취소/원인/미보고비용 미확인')
 else:row.update(error='MANUAL_REVIEW_REQUIRED',explanation='Actual answer must be separately reviewed; no token-match legal score')
 rows.append(row)
put(ART/'semantic-review.json',{'rows':rows,'all_passed':False,'judging_model_calls':0,'product_response_rewritten':False,'conclusion':'제공자 변경만으로 첫 질문 조항 경로 누락과 두번째 질문 공백 응답을 해소하지 못함. 모수 전체 정답률·장기 안정성 인증 아님.'})
print(json.dumps(rows,ensure_ascii=False,indent=2))
