from common import *
import re
m=read(ADR/'실험/manifest.json');cells=[];physical=[]
audit=read(ART/'source-wire-audit.json')
for case in read(DES/'live-cases.json'):
 d=ART/'public-live'/(case['id']+'-selected')
 if not (d/'result.json').exists():
  cells.append({'case_id':case['id'],'executed':False,'reason':'Frozen stop after prior unknown/resource failure','physical_calls':0});continue
 calls=read(d/'calls.json') if (d/'calls.json').exists() else [];physical+=calls
 raw=read(d/'result.json');answer=(d/'turn-1/answer.txt').read_text() if (d/'turn-1/answer.txt').exists() else ''
 menus=[];decisions=[]
 for p in sorted((d/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  view=read(p)['view'];out=p.with_name(p.name.replace('.json.gz','-output.json.gz'))
  if view.get('tool_menu'):menus.append({'canonical':p.name,'menu':view['tool_menu'],'read_candidates':len(view.get('read_candidates',[]))})
  if out.exists():
   value=read(out)
   if isinstance(value,dict) and value.get('choice'):decisions.append({'canonical':p.name,'choice':value['choice']})
 cell={'case_id':case['id'],'executed':True,'result':raw,'answer':answer,'menus':menus,'navigation_choices':decisions,
  'physical_calls':len(calls),'unknown':sum(x['status']=='unknown' for x in calls),
  'responses429':sum(x.get('http_status')==429 for x in calls),'reported_cost_usd':sum((x.get('usage') or {}).get('cost',0) for x in calls),
  'new_model_reply_replay':0,'errors':[x for x in read(d/'generations.json') if x.get('status')=='rejected']}
 cells.append(cell)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');selected=read(DES/'baseline.json')
assert active==selected['pointer']
r=selected['release'];assert all(sha(ROOT/r['code_root']/n)==h for n,h in r['files'].items())
assert all(not a[k] for a in audit['cells'] for k in ('source_mismatches','acl_violations','wire_mismatches'))
unknown=sum(x['status']=='unknown' for x in physical)
result={'status':'INCOMPLETE_PROVIDER_UNKNOWN' if unknown else 'EXECUTED_REVIEW_REQUIRED','selected_MAIN':150,'serving_files_unchanged':530,
 'cells':cells,'physical_calls':len(physical),'unknown':unknown,'reported_cost_usd':sum((x.get('usage') or {}).get('cost',0) for x in physical),
 'source_checks':sum(a['source_checks'] for a in audit['cells']),'delivered_checks':sum(a['delivered_checks'] for a in audit['cells']),
 'source_acl_wire_mismatches':0,'budget_matches':all(a['budget_matches'] for a in audit['cells']),
 'new_product_modifications':0,'response_replay':0,'external_sends_after_unknown':0 if unknown and physical[-1]['status']=='unknown' else None,
 'quality_certified':False,'model_policy':'Qwen3.8 Parasail FP8 none; confirmed429 permits existing NearAI FP8 transition once; no output cap',
 'limits':['In-sample CM cases, not holdout or full legal-quality certification.','Unknown remote completion/cancellation and unreported cost cannot be established locally.','Current Risk CM restriction honored; ADR1407 admission403/model0 is separate.']}
if unknown:
 result['observed_failure']={'completed_responses':sum(x.get('http_status')==200 for x in physical),
  'confirmed429':sum(x.get('http_status')==429 for x in physical),'unknown_diagnostics':physical[-1].get('transport_diagnostics'),
  'navigation_choice_completed':any(c.get('navigation_choices') for c in cells),
  'final_answers':0,'assessment':'Entry and common memory review completed. First navigation choice received429 on Parasail, then NearAI HTTP200 headers with60 whitespace chunks660bytes; absolute deadline stopped at179.477s. Actual request219.467s/504. No selected action response, common navigation review or final answer; effects of dispatch repair remain unmeasured in this live run.'}
put(ART/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'selected':result},comparisons=[],judge_disagreements=0,
 usage={k:result[k] for k in ('physical_calls','unknown','reported_cost_usd')},latency={'per_case':[{k:t.get(k) for k in ('case_id','request_seconds')} for c in cells if c['executed'] for t in c['result']['turns']]},
 error_taxonomy=['Provider outcomes and navigation outcomes recorded separately; no case retry after unknown.'])
for q in m['questions']:
 p=ADR/'실험'/q['file'];value=next(c for c in cells if c['case_id']==q['case_id'])
 p.write_text(p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\n'+json.dumps(value,ensure_ascii=False,indent=2)+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
summary='MAIN150 기존 CM 실제 Qwen: '+result['status']+' / 물리'+str(len(physical))+' / UNKNOWN'+str(unknown)+'.'
text=summary+'\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n'
(ART/'실제_CM_결과.txt').write_text(text)
front=(ADR/'README.md').read_text().split('---',2)[1]
headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[summary,'1405의 도구 선택·목표 계약과 문서별 표시 수정을 실제 선택 메인으로 확인한다. 1407 Risk CM은 현행 사용자 정책에 따라 모델 전송 전403 차단되었으므로 허용된 기존CM으로 새로 동결했다.',
 json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'기존CM018 구조 질문, CM043 인용 연결 질문을 financial팀 공개 허용 문서로 독립1회씩. UNKNOWN이면 이후 전송 중단. 결과를 보고 제품코드·질문·선택 기준을 바꾸지 않았다.',
 '선택 MAIN150 동일530·등록 원문 SQLite·격리 상태 DB. 제품 입력에는 질문과 실제 허용 원문만, 기준답변·좌표 주입0. 기존 Qwen3.8/none·출력상한 없음·40회 예산. 문항은 알려진 인샘플이다.',
 json.dumps(result,ensure_ascii=False,indent=2),'호출별 raw/finished와 canonical/generations로 정상·429·UNKNOWN 및 모델 검증 거절을 구분한다. 미완료 탐색을 완성답변이나 코드 수정 실패로 단정하지 않는다.',
 '원문확보·실전달은 source-wire-audit의 원문 span 대조 및 retrieval-stage-ledger 조문 단위로 기록한다. 작은 표본의 지연·회수 수는 일반 성능 개선율로 쓰지 않는다.',
 '계약 검사와 실제 의미 품질은 별개다. 모델의 선택 응답이 완료되지 않은 단계는 선택 실행의 효과를 판정할 수 없다.',
 '\n'.join(result['limits']),'MAIN150 유지·추가 제품수정/GENOS배포/Oracle연결/운영DB/메일0. UNKNOWN 재전송 없이 원기록 보존. 구조 반영 결과는 ADR1405.',
 'setup.py → live.py cm-018 --preflight → live.py cm-018 → (stop 없을 때만 cm-043) → audit.py → ledger.py → finalize.py. 모든 실제 요청/응답은 artifacts/public-live의 raw와 canonical.']
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN150 기존 CM 실모델 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(headings,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 기존 CM 실제 질문\n\n현행 허용 질문과 financial팀 공개 원문. 실제 결과와 미실행은 artifacts/result.json, 회수·전달 대조는 source-wire-audit.json에 기록한다.\n')
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'};paths.update(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1408','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact code, current-policy admission, actual model and source audit evidence','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in sorted(paths)]})
print(summary)
