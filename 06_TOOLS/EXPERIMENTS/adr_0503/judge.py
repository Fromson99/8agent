"""Two swapped anonymous offline assessments; no feedback enters product execution."""
import json,sys,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from run_probe import ROOT,ADR,read,write,pin,sha
DIMS=['demand_coverage','rule_scope','conditions_exceptions','appropriate_abstention','self_review']
def obj(p):return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}
STR={'type':'string'}
DIM=obj({'status':{'type':'string','enum':['pass','fail','not_observable']},'reason':STR})
SCHEMA=obj({'assessments':{'type':'array','minItems':2,'maxItems':2,'items':obj({'label':{'type':'string','enum':['A','B']},'correct':{'type':'boolean'},'reason':STR,'dimensions':obj({k:DIM for k in DIMS})})}})
SYSTEM='''제품 실행과 분리된 평가자다. 익명 A와 B를 독립 평가하고 우열을 강제로 만들지 마라. 저장 기준답의 핵심 결론과 조건을 실제 전달하면 correct=true. 기준답은 현행 법률 정당성 인증이 아니다. 필요한 부분을 유보하면 정답으로 처리하지 않는다. 추가 사실이 없으면 답할 수 없는 부분을 확정해도 실패다. 출처가 없다는 이유만으로 기준답과 일치하는 답을 오답 처리하지 마라. 답변에 실제 없는 단정이나 누락을 만들어 지적하지 마라. 조건의 AND/OR, 일반 규칙과 특례 범위, 재량 표현을 엄밀히 대조하라. dimensions는 질문 요구 충족, 규칙/적용 범위, 조건·예외 보존, 확정·유보의 적절성, 자기검토의 적절성이다. self_review는 제공된 초안 및 검토 흔적과 최종 답을 대조하고 관측 부족이면 not_observable. 기술적 오류, 게시 여부, 모델명은 품질 채점 대상이 아니다. 이유에 실제 답변의 짧은 문구와 기준 차이를 명시하라. 각 label을 한 번씩만 반환하라.'''
def main():
 pin();from lawrag.research.experiment_client import ExperimentClient
 result_path=ADR/'artifacts/run-001/results.json';products=read(result_path);assert products.get('finished_at')
 gold={x['case_id']:x for x in read(ADR/'gold-cases.json')['cases']};cases=read(ADR/'product-cases.json')['cases']
 target=ADR/'artifacts/run-001/judgment';target.mkdir(exist_ok=False)
 def evaluate(case):
  cid=case['case_id'];observed={};root=ADR/'artifacts/run-001'/cid
  for arm in ['baseline','obligations']:
   row=products['cases'][cid][arm];trace=read(root/arm/'trace.json')
   observed[arm]={'answer':row.get('result',{}).get('answer',{}),'claims':trace.get('claims',[]),'assessments':trace.get('assessments',[]),'sources':[{'text':e['text'],'metadata':e['metadata']} for e in trace.get('evidence',[]) if e['source_id'] in row.get('stages',{}).get('selected',[])]}
  calls=[];usage=[]
  for repeat,order in enumerate([['baseline','obligations'],['obligations','baseline']],1):
   labels=dict(zip(['A','B'],order));client=ExperimentClient(ROOT,target/cid/f'order-{repeat}',max_calls=1,max_output_tokens=4000)
   try:
    value=client.generate(SYSTEM,{'question':case['question'],'reference_answer':gold[cid]['reference_answer'],'variants':[{'label':label,**observed[arm]} for label,arm in labels.items()]},SCHEMA,phase='judgment')
    assert sorted(x['label'] for x in value['assessments'])==['A','B']
    entry={'labels':labels,'by_arm':{labels[x['label']]:x for x in value['assessments']},'error':None}
   except Exception as exc:entry={'labels':labels,'error':{'type':type(exc).__name__,'message':str(exc)}}
   calls.append(entry);usage+=client.usage
  out={'case_id':cid,'product_results_sha256':sha(result_path),'assessments':calls,'usage':usage,'technical_unevaluable':{a:bool(products['cases'][cid][a].get('error')) for a in ['baseline','obligations']}}
  write(target/cid/'judgment.json',out);print('JUDGED',cid,flush=True);return cid,out
 with ThreadPoolExecutor(max_workers=4) as pool:judged=dict(pool.map(evaluate,cases))
 write(target/'results.json',{'cases':judged,'finished_at':time.time()})
if __name__=='__main__':main()
