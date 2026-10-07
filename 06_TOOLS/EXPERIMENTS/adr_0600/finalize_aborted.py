"""Record a provider-aborted run without fabricating quality or retrieval scores."""
import hashlib,json,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0600-rag-chain-bounded-provider-retest'
REPORT=ROOT/'07_DOCS/REFERENCE/REPORTS/ADR-0600_RAG_CHAIN_STRICT_REPAIR_20261001.md'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def block(x):return '\n```json\n'+json.dumps(x,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'
def main():
 run=ADR/'artifacts/run-001';m=json.loads((ADR/'실험/manifest.json').read_text());rows=[];counter=collections.Counter();errors=collections.Counter();audits=0;usage=[]
 for q in m['questions']:
  cid=q['case_id'];items=[json.loads(p.read_text()) for p in sorted((run/cid/'RETEST').glob('turn-*.json'))]
  for i in items:
   counter[i['observed']['status']]+=1
   if i['observed']['status']=='ERROR':errors[i['observed'].get('error_type','unknown')]+=1
   audits+=bool(i.get('text_audits'))
  rows.append({'case_id':cid,'arms':{'RETEST':items}})
 for p in run.rglob('usage.json'):usage+=json.loads(p.read_text())
 events=json.loads((run/'transport-receipts.json').read_text());guard=json.loads((run/'guard-result.json').read_text())
 summary={'execution_aborted':True,'cause':'Parasail shared upstream pool HTTP429 persisted through one bounded retry; offline audit aborted','turns_attempted':sum(counter.values()),'turn_status':dict(counter),'error_type_counts':dict(errors),'completed_text_audits':audits,'functional_score':None,'calibration_this_run':'not_executed','guard_checks':{'passed':guard['passed'],'total':guard['total']},'transport_unit':json.loads((ADR/'artifacts/design/transport-unit.json').read_text()),'transport':{'request_attempts':sum(1 for p in run.rglob('request.json')),'http429_error_attempts':sum(x['status_code']==429 for x in events),'retry_scheduled':sum(x['retry_scheduled'] for x in events),'failed_request_usage':'unavailable, not imputed as zero'},'usage':{'successful_calls_with_usage':len(usage),'input_tokens':sum(x.get('input_tokens',0) or 0 for x in usage),'output_tokens':sum(x.get('output_tokens',0) or 0 for x in usage),'reported_successful_cost_usd':sum(x.get('usage',{}).get('cost',0) or 0 for x in usage)}}
 result={'schema_version':'rag-chain-aborted-provider-v1','run_id':'run-001','data_kind':'SYNTHETIC','products':rows,'guard_result':guard,'summary':summary,'scoring':'Frozen normal score was not reached; partial responses are not promoted to full sequence passes. Raw turn files and provider errors are unchanged.'}
 write(run/'execution-abort.json',result)
 for q,c in zip(m['questions'],rows):
  cid=q['case_id'];parts=['# '+cid,'','## 1. 실행 메타','ADR0600 / RETEST / run-001 / same Qwen3.8 Parasail FP8 / provider-aborted','## 2. 사용자 질문 원문',block(next(x for x in json.loads((ADR/'artifacts/design/inputs.json').read_text()) if x['case_id']==cid)),'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',block(json.loads((ADR/'artifacts/design/gold.json').read_text())[cid]),'## 4. 제품 입력을 구성한 원값',block(c),'### 회수·탈락 단계 원장 — run·arm별','전체 최종 소비 경로 계측은 제공자 중단으로 미완료. 각 턴의 실제 measurement를 위 원값으로 보존했다. 0점/0개로 대체하지 않았다.','## 5. 제품 모델 호출 — run·arm별 실제 원문']
  for folder in sorted(list((run/'provider'/cid).glob('call-*'))+list((run/'offline-evaluator'/cid).glob('call-*'))):
   parts+=['### '+str(folder.relative_to(run))]
   for name in ['request.json','validation-schema.json','binding.json','response.json','output.json']:
    p=folder/name
    if p.exists():parts+=['#### '+name,block(json.loads(p.read_text()))]
  parts+=['## 6. 중간 LLM 호출 — router/compiler/verifier/repair','실제 resolve/select/assess/compose/check 및 HTTP 재시도 원문은 위와 transport-receipts.json에 남겼다.','## 7. 채점 호출과 반복 판정','Offline audit가 HTTP429로 중단되어 계획한 최종 채점·calibration을 실행하지 못했다.','## 8. 사례 최종 판정','판정 미완료: 공급자 장애로 일반 기능 정확도를 결론내리지 않는다.']
  (ADR/'실험'/q['file']).write_text('\n'.join(parts)+'\n')
 m['runs'][0].update(status='failed',artifact_path=str((run/'execution-abort.json').relative_to(ROOT)),sha256=sha(run/'execution-abort.json'))
 m['results'].update(status='failed',by_arm={'RETEST':summary},comparisons=[],judge_disagreements=None,usage=summary['usage'],latency={'unavailable':'full run not completed'},error_taxonomy=[{'type':'other','cause':'provider_shared_pool_rate_limit','artifact':str((run/'execution-abort.json').relative_to(ROOT))}])
 for key in ['before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']:m['retrieval_accounting'][key]={'RETEST':None}
 m['retrieval_accounting']['stage_ledger'].update(artifact_path=None,sha256=None)
 write(ADR/'실험/manifest.json',m)
 headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
 texts=['제품 수정 후보는 유지한다. 전체 실모델 검증은 미완료이며 MAIN 승격 대상이 아니다.','앞선 ADR0599의 HTTP429 중단을 같은 제품 코드로 재검증했다.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],'49턴·17 calibration을 계획했으나 49턴 호출 시도 뒤 audit에서 중단됐다.','합성 자료·정확한 부모·동결 코드·Qwen3.8 Parasail FP8 유지.',block(summary),'공급자 오류와 초기 상태 미생성에 따른 후속 오류를 구분한다.','완료된 호출 사용량만 관측, 실패 호출 비용과 최종 회수 계측은 미확인.','부분 정상 답변을 전체 기능 통과로 채점하지 않는다.','실제 RAG API·온톨로지 적재기·GENOS·자연어 목표 검색·공유 세션 경합 미연결.','코드·원문·SQL·MAIN unchanged. 외부 호출 추가 중단.','기존 실패 산출물은 덮어쓰지 않는다. 공급자 복구 후 재실험은 새 ADR에서 한다.']
 front=(ADR/'README.md').read_text().split('---',2)[1];(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0600 — 제공자 중단 기록\n\n'+'\n\n'.join('## '+str(i)+'. '+h+'\n\n'+t for i,(h,t) in enumerate(zip(headings,texts),1))+'\n')
 (ADR/'실험/README.md').write_text('# 질문 인덱스\n\n| 사례 | 현재 판정 |\n|---|---|\n'+'\n'.join('| ['+q['case_id']+']('+q['file']+') | 공급자 장애로 전체 판정 미완료 |' for q in m['questions'])+'\n')
 REPORT.write_text('# 엄격 수정 프로토와 제공자 중단 기록\n\n**코드·32개 계약 검사·3개 HTTP 재시도 단위 검사는 완료했다. 전체 실제 모델 검증은 HTTP429로 미완료다.**\n\nADR0599와 제품 코드는 byte-exact하다. 모델·Parasail FP8·reasoning none·fallback 없음도 유지했다. 대기 5초 후 최대 1회 재시도했지만 공유 풀 제한이 계속되어 추가 호출을 중단했다.\n\n'+block(summary)+'\n동일 제품의 실제 모델 문장 검사 17/17은 [ADR0599](ADR-0599_RAG_CHAIN_STRICT_REPAIR_20261001.md)에서 확인했다. 이번 run의 calibration 통과로 바꾸어 말하지 않는다.\n\n원인별 구현 변경·함수 위치는 ADR0599 보고서를 따른다. 공통 온톨로지 DB 적재·의미 기반 wiki 검색·실제 RAG/GENOS는 미연결이다. 이번 SQLite 기록은 작업 상태/감사이며 지식 재사용은 현재 유효 route만 소비한다.\n\n[실제 턴·전체 모델 원문](../../../'+str((ADR/'실험/README.md').relative_to(ROOT))+')\n')
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
