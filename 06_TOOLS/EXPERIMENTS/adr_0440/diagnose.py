"""Post-run read-only diagnosis; no regrading or model calls."""
import json,hashlib
from pathlib import Path
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0440-task-harness-flash-medium';A=D/'artifacts';OLD=R/'04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation/artifacts'
def read(p):return json.loads(p.read_text())
def main():
 results=read(A/'results.json');prior=read(OLD/'results.json');cases={c['id']:c for c in read(A/'dataset/product-cases.json')};diagnosis=[]
 for cid,arms in results['cases'].items():
  r=arms['flash-medium'];s=(r.get('output') or {}).get('retrieval',{}).get('term_agent',{});concepts=s.get('task_state',{}).get('concepts',[]);calls=[]
  assert arms['baseline']['output']==prior['cases'][cid]['harness']['output']
  for p in sorted((A/'calls'/cid/'flash-medium').glob('call-*-task_interpret/output.json')):
   v=read(p);spans=v['concepts'];q=cases[cid]['question'];calls.append({'task_type':v['task_type'],'valid_spans':all(0<=i['start']<i['end']<=len(q) and q[i['start']:i['end']]==i['text'] for i in spans),'spans':spans})
  row={'id':cid,'interpretation_calls':calls,'calls':r['calls'],'phase':s.get('task_state',{}).get('phase'),'concepts_count':len(concepts),'concept_question_spans':list({c['question_span']['text'] for c in concepts}),'candidate_labels':[c['term']['label'] for c in concepts],'read':s.get('read_source_ids',[]),'question_for_user':s.get('question_for_user'),'answer':(r.get('output')or{}).get('answer',{}).get('text'),'failure':r.get('failure') or s.get('failure')}
  diagnosis.append(row)
 data={'cases':diagnosis,'historical_baseline_outputs_identical':True,'new_calls_model_versions':sorted({u['model'] for a in results['cases'].values() for u in a['flash-medium']['usage']})};(A/'diagnosis.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 positive=[r for r in diagnosis if not r['id'].startswith('guard-')];valid=sum(all(c['valid_spans'] for c in r['interpretation_calls']) and bool(r['interpretation_calls']) for r in positive);cap=sum(r['concepts_count']==24 and r['phase']=='WAITING_USER' for r in positive)
 text=f'모델 상향 후 설명 질문{valid}/6에서 모든 반환 구간이 원문과 정확히 일치했다. 하지만{cap}/6이 후보24개 상한에 걸려 원문을 읽기 전에 확인 요청으로 종료했다.\n\n'
 text+='실제 trace에서 문서명 자본시장법 → 검색 label 자본시장과 금융투자업에 관한 법률 → 자본/equity/capital 등 부분문자열 후보가 포함된다. `TaskSession.interpret`는 문서명과 목표 개념을 구분하지 않고 순서대로 `ReverseMatcher.starts`에 보낸다. 24개를 모으면 바로 ASK_USER로 종료해 뒤의 목표 개념을 검토하지 못한다. 이는 해석 좌표 오류 다음에 드러난 하네스 후보 처리 결함이다.\n\n'
 for r in diagnosis[-2:]:text+=f"- {r['id']}: {r['phase']}, {r['calls']}회, 확인 안내: {r['question_for_user']}\n"
 text+='\n상향 모델의 해석 개선과 최종 답변 성공은 다르다. 이 실험은 원래 하네스를 수정하지 않았다. 구조를 고치지 않고 모델만 더 올려 해결된다고 주장할 수 없다. 비용·지연은 초기화와 조기 종료의 영향을 포함한다. 과거 Lite 출력과 동일함을 직접 비교했다.\n'
 (A/'diagnosis.md').write_text(text);print(text)
if __name__=='__main__':main()
