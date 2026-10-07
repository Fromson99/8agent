"""Read-only matched-case comparison after both independent runs are scored."""
import json,hashlib,statistics,math
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0497-gemma4-fp8-source-workflow-cm51-fsc10';B=R/'04_EXPERIMENTS/ADR/ADR-0496-qwen-source-workflow-cm51-fsc10'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def table(headers,rows):return '| '+' | '.join(headers)+' |\n| '+' | '.join('---' for _ in headers)+' |\n'+'\n'.join('| '+' | '.join(map(str,x))+' |' for x in rows)
def main():
 if not (B/'artifacts/metrics.json').is_file():
  print('Qwen scoring incomplete; comparison pending');return
 assert sha(A/'product-cases.json')==sha(B/'product-cases.json') and sha(A/'gold-cases.json')==sha(B/'gold-cases.json')
 a=read(A/'artifacts/metrics.json');b=read(B/'artifacts/metrics.json');aa={x['case_id']:x for x in a['by_case']};bb={x['case_id']:x for x in b['by_case']};assert set(aa)==set(bb) and len(aa)==61
 pairs={k:[] for k in ['gemma_only_correct','qwen_only_correct','both_correct','both_incorrect','ungraded']};rows=[]
 for cid,x in aa.items():
  y=bb[cid];key='ungraded' if x['correct'] is None or y['correct'] is None else 'both_correct' if x['correct'] and y['correct'] else 'gemma_only_correct' if x['correct'] else 'qwen_only_correct' if y['correct'] else 'both_incorrect';pairs[key].append(cid)
  row={'case_id':cid}
  for label,v in [('gemma',x),('qwen',y)]:
   for k in ['correct','claims','gold_final','gold_payload','seconds','calls']:row[label+'_'+k]=v[k]
  rows.append(row)
 cohorts={}
 for name,ids in [('CM51',[c for c in aa if c.startswith('cm-')]),('FSC hard10',[c for c in aa if c.startswith('fsc-')]),('all61',list(aa))]:
  cohort={}
  for label,source in [('gemma',aa),('qwen',bb)]:
   v=[source[c] for c in ids];ss=[s for x in v if x['publication_status']=='PUBLISHED' for s in x['sources']]
   cohort[label]={'correct':sum(x['correct'] is True for x in v),'total':len(v),'ungraded':sum(x['correct'] is None for x in v),'reviewed_answers':sum(x['claims']>0 for x in v),'source_recall':sum(x['gold_final'] for x in v)/sum(x['gold_total'] for x in v),'payload_source_recall':sum(x['gold_payload'] for x in v)/sum(x['gold_total'] for x in v),'source_precision':sum(s['relevant'] for s in ss)/len(ss) if ss else None,'calls':sum(x['calls'] for x in v),'p50_seconds':statistics.median(x['seconds'] for x in v),'p95_seconds':sorted(x['seconds'] for x in v)[math.ceil(.95*len(v))-1]}
  cohort['delta_correct']=cohort['gemma']['correct']-cohort['qwen']['correct'];cohorts[name]=cohort
 artifacts=[A/'artifacts/metrics.json',B/'artifacts/metrics.json',A/'artifacts/run-001/judged-results.json',B/'artifacts/run-001/judged-results.json']
 result={'schema_version':'adr0497-model-comparison-v1','comparison_type':'descriptive matched questions; different providers/start times; not randomized','inputs':{str(p.relative_to(R)):sha(p) for p in artifacts},'cohorts':cohorts,'pairs':pairs,'rows':rows,'observed_superiority_gate':cohorts['all61']['delta_correct']>0 and cohorts['all61']['gemma']['source_recall']>=cohorts['all61']['qwen']['source_recall'] and a['verdicts']['budget'],'gemma_product_usage':a['by_arm']['gemma']['usage'],'qwen_product_usage':b['by_arm']['repaired']['usage'],'main_wiring':'unchanged'}
 p=A/'artifacts/model-comparison.json'
 if p.exists():raise RuntimeError('Comparison already exists')
 p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 lines=['# Gemma4 FP8와 Qwen 동일 RAG 비교','Gemma4 31B FP8(DeepInfra) 대 Qwen3.5 122B A10B FP8. 동일61문항·원문·검색/답변/검토 로직·예산, thinking off. Gemma 호출·게시 승인 설정 연결만 격리 변경했다. 두 결과 모두 동일 Qwen 채점 기준을 사용했다.',table(['문항군','Gemma 정답','Qwen 정답','차이'],[[n,f"{c['gemma']['correct']}/{c['gemma']['total']}",f"{c['qwen']['correct']}/{c['qwen']['total']}",c['delta_correct']] for n,c in cohorts.items()]),table(['지표','Gemma','Qwen'],[[k,cohorts['all61']['gemma'][k],cohorts['all61']['qwen'][k]] for k in ['reviewed_answers','ungraded','source_recall','payload_source_recall','source_precision','calls','p50_seconds','p95_seconds']]),table(['동일 문항 판정','수','사례'],[[k,len(v),', '.join(v) or '없음'] for k,v in pairs.items()]),'## 비용','반환 usage 기준 제품 비용: Gemma $'+str(result['gemma_product_usage']['cost_usd'])+', Qwen $'+str(result['qwen_product_usage']['cost_usd'])+'. 누락 usage의 비용은 미확인이다.','## 해석 제한','인샘플61건 각1회다. provider·호출 시점·로컬 자원 경쟁이 달라 순수 모델 효과나 서버 속도 우열을 확정하지 않는다. Qwen 자기평가 편향과 미보정 채점기의 false pass/false fail은 미측정이다. 게시·답변 완성·기준답 일치는 별개 지표다. GENOS 성능을 측정한 것이 아니며 MAIN 변경 없음.','[Gemma 상세](README.md) · [Qwen 상세](../'+B.name+'/README.md) · [비교 원장](artifacts/model-comparison.json)']
 (A/'COMPARISON.md').write_text('\n\n'.join(lines)+'\n');print(json.dumps(cohorts,ensure_ascii=False))
if __name__=='__main__':main()
