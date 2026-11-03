from common import *
import re
rows=[];calls=[]
for d in sorted((ART/'live').iterdir()):
 if (d/'result.json').exists():rows.append(read(d/'result.json'))
 if (d/'calls.json').exists():calls+=read(d/'calls.json')
result={'status':'NOT_PASSED','performance_improved':False,'conclusion':'4セルとも試験承認接続で未完了。ON/OFF性能向上は未評価。',
 'cells':rows,'physical_calls':len(calls),'unknown':sum(x['status']=='unknown' for x in calls),'reported_cost_usd':sum((x.get('usage') or {}).get('cost',0) for x in calls),'reported_tokens':sum((x.get('usage') or {}).get('total_tokens',0) for x in calls),
 'failure':'Experiment derive incorrectly required external session_id/use_llm inside the core, which legitimately translates to an internal investigation session and drops API-only fields. All4API422 are experiment failures, not product fault. No source output modified.',
 'supplement':{k:v for k,v in read(ART/'followup-supplement/result.json').items() if k not in ('reports','origins')},'main_product_changes':0,'quality_certified':False}
result['conclusion']='4개 실행 모두 시험기 승인 연결에서 미완료. 온톨로지 ON/OFF 성능 향상은 평가하지 못함.'
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');put(ART/'preregistered-manifest-before-final-accounting.json',m)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
reason='All4fixedcells failed experiment-derived-context authorization before source-selection completion. Original planned stage accounting retained; null final retrieval metrics unavailable, no efficiency/recall claim.'
m['design']['retrieval_stage_plan']['stages_by_arm']={};m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason);m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=reason)
m['results'].update(status='complete',by_arm={a:{'cells':[r for r in rows if r['arm']==a]} for a in ('baseline','ontology-on')},comparisons=[{'result':'NOT_EVALUABLE','reason':reason}],judge_disagreements=0,usage={k:result[k] for k in ('physical_calls','reported_cost_usd','reported_tokens')},latency={'request_seconds':sum(r['request_seconds'] for r in rows)},error_taxonomy=[{'type':'EXPERIMENT_INTERNAL_SESSION_GRANT','count':4}]);put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[result['conclusion'],'완료1294의파생질문승인수정. 제품MAIN133513파일동일.','design/criteria.json;완성된2쌍과품질보존후비용/시간/토큰/호출측정.','동일365/369교차순서한번씩·원문Oracle읽기전용/상태SQLite. RSS5GiB·가용3GiB·swap증가128MiB.','Qwen3.8-27b/Parasail우선·365OFF확정429후NearAI. 모든입력/코드design/freeze.json.',json.dumps(result,ensure_ascii=False,indent=2),
 '제품은외부session_id를내부investigation ID로정상전환하며corebody에는use_llm을보존하지않는다. 시험기derive가외부ID/use_llm완전일치를강제해4개422. 365OFF1421SQL/253.658초,다른셀17SQL/약10초는효율비교가아님. 파생질문등록전에실패. 후속사실보완보조검사1통과:고정문구만의미기준으로바꾸고같은사건/원문/주장/재조회검증유지.',
 f'실제{len(calls)}물리/보고${result["reported_cost_usd"]:.8f}/보고{result["reported_tokens"]}토큰/UNKNOWN{result["unknown"]}. 최종답변0. 실제모델응답과실패저널무손실보존.',
 '시험기승인실패로제품품질/온톨로지효과판정불가. 다음검증은실제원본응답재생으로native내부사건연결→두번째전송직전승인을모델0회로먼저검증해야한다.',
 '네셀모두미완료이며작은시간을ON향상으로간주하지않음. 공급자전환/자연계획차이도보존. 원문Oracle/상태SQLite의범위.',
 '제품/MAIN/Gold/원문/DB·DDL/게시변경0. 이전1293대사실패별도보존. 새ADR에서실험승인에검증된내부사건과외부세션연결만정정하며원문·모델제안·상태변경금지.',
 'prepare→preflight→freeze→run_all→supplement→finalize. 실제셀재실행0;원기록은artifacts/live.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 온톨로지 실험 승인 검증1296\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
for q in m['questions']:
 c=next(c for c in read(DES/'cases.json') if c['id']==q['case_id']);sections=[('실행 메타','run-001;design/freeze.json'),('사용자 질문 원문',c['question']),('기준답변 — 채점 전용, 제품 입력 비공개','design/scoring-only-originals.json. 제품입력비공개·평가모델0.'),('제품 입력을 구성한 원값','canonical과raw무손실보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n최종회수미평가. 사전계획은preregistered-manifest-before-final-accounting.json.'),('제품 모델 호출 — run·arm별 실제 원문','live/<case>-<arm>/raw/call-*;calls.json'),('중간 LLM 호출 — router/compiler/verifier/repair','request-entry만정상응답4회/확정4291회. 이후시험기승인실패.'),('채점 호출과 반복 판정','모델채점/재실행0. 내부오류근거로미완료판정.'),('사례 최종 판정','실험승인실패422/최종0/효과미평가.')]
 (ADR/'실험'/q['file']).write_text('# '+c['id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 기록\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1296','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved probe record','contains_raw_prompts_and_outputs':'raw' in p.parts or 'canonical' in p.parts} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json']})
print(json.dumps({k:result[k] for k in ('physical_calls','reported_cost_usd','unknown')},ensure_ascii=False))
