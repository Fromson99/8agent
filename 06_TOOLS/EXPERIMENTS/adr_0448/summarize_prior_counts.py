"""Summarize already completed ADR0447 payloads; never rerun/regrade or change gold."""
import json
from binding_runtime import R,A,read,sha
P=R/'04_EXPERIMENTS/ADR/ADR-0447-template-bound-tool-handles/artifacts'
def walk(v):
 if isinstance(v,dict):
  yield v
  for x in v.values():yield from walk(x)
 elif isinstance(v,list):
  for x in v:yield from walk(x)
def main():
 if (A/'prior-counts.json').exists():raise ValueError('report exists')
 results=read(P/'results.json');gold={g['id']:g for g in read(P/'grading/gold.json')['cases']};sources={s['id']:s for s in read(P/'dataset/synthetic-sources.json')};cases=read(P/'dataset/product-cases.json');rows=[];proof={};allgold=set();allselected=set();allread=set()
 for case in cases:
  cid=case['id'];state=results['cases'][cid]['bound']['output']['retrieval']['term_agent'];aliases=state['id_aliases'];offered=set();bodies=set();per_call=[]
  for p in sorted((P/'calls'/cid/'bound').glob('call-*/request.json')):
   req=read(p);proof[str(p.relative_to(R))]=sha(p);cards=set();readids=set()
   for msg in req['contents']:
    for part in msg['parts']:
     data=json.loads(part['text'])
     for v in walk(data):
      if v.get('read_handle') and isinstance(v.get('read_action'),dict):
       sid=aliases.get(v.get('source_id'),v.get('source_id'))
       if sid in sources:cards.add(sid)
      if v.get('segment_sha256') and isinstance(v.get('text'),str):
       sid=aliases.get(v.get('source_id'),v.get('source_id'))
       if sid in sources:readids.add(sid)
   offered|=cards;bodies|=readids;per_call.append({'request':str(p.relative_to(R)),'candidate_source_ids':sorted(cards),'body_source_ids':sorted(readids)})
  needed=set(gold[cid]['required_source_ids']);selected=set(state['selected_ids']);assert bodies==set(state['read_source_ids']),(cid,bodies,state['read_source_ids'])
  assert offered==set(state['known_source_ids']),(cid,offered,state['known_source_ids'])
  scoped={sid for sid,s in sources.items() if s['document_id'] in case['scope_document_ids']}
  rows.append({'case_id':cid,'scope_articles':len(scoped),'candidate_metadata_offered':len(offered),'bodies_delivered':len(bodies),'gold_articles':len(needed),'selected_articles':len(selected),'correct_selected':len(selected&needed),'irrelevant_selected':len(selected-needed),'metadata_source_ids':sorted(offered),'read_source_ids':sorted(bodies),'selected_source_ids':sorted(selected),'gold_source_ids':sorted(needed),'per_call':per_call})
  allgold|=needed;allselected|=selected;allread|=bodies
 totals={k:sum(x[k] for x in rows) for k in ['scope_articles','candidate_metadata_offered','bodies_delivered','gold_articles','selected_articles','correct_selected','irrelevant_selected']}
 out={'basis':'Completed ADR0447/bound run-001 actual saved requests and outputs; no rerun/regrade','corpus_articles':len(sources),'corpus_documents':len({s['document_id'] for s in sources.values()}),'questions':len(cases),'answer_questions':sum(x['gold_articles']>0 for x in rows),'totals_case_article':totals,'unique_gold_articles':len(allgold),'unique_selected_articles':len(allselected),'unique_read_articles':len(allread),'cases':rows,'input_hashes':{**proof,**{str(p.relative_to(R)):sha(p) for p in [P/'results.json',P/'grading/gold.json',P/'dataset/product-cases.json',P/'dataset/synthetic-sources.json']}}}
 (A/'prior-counts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 table='| 질문 | 검색 대상 | 제시 후보 | 실제 읽음 | 정답 조문 | 최종 선택 | 정답 선택 |\n|---|---:|---:|---:|---:|---:|---:|\n'
 for x in rows:table+='| '+x['case_id']+' | '+' | '.join(str(x[k]) for k in ['scope_articles','candidate_metadata_offered','bodies_delivered','gold_articles','selected_articles','correct_selected'])+' |\n'
 text='# 기존 실행의 후보·원문·정답 조문 수\n\nADR0447/bound 완료 실행. 이번 연결 보완 후보0448의 새 답변 평가가 아니다. 총7문서9조문, 12질문 중 근거답변10·목록/정답없음2. 후보는 실제 모델 요청에 포함된 원문 메타데이터 카드, 읽음은 실제 전달된 본문으로 집계했다. 질문별 누적 고유 조문이며 같은 조문을 여러 호출에 반복 제시해도 한 번 센다.\n\n'+table+'\n답변형10질문 모두 정답1개짜리이며 복수 정답 조문 조합 문제는 없다. 9질문은 후보1개, 복구1질문만 후보2개. 최종10개 중 정답10개는 질문×조문 집계이고 실제 고유 정답 조문은8개다. corpus9개를 모두 한 번에 모델에 던진 실험이 아니다.\n\n구현은 채택한 원문 ID 전체를 중복 제거해 선택하므로 최종 조문1개 고정 제한은 없다. 실제 관측된1개 선택은 이 평가 데이터 구성이다. 조문 선택 성공과 답변 전체 채점11/12는 다른 지표이며 전환 과정 서술 누락은 선택 오류가 아니다. 다수 유사후보 판별·복수 조문 종합·대규모 실제 corpus 품질은 이 기록으로 확인할 수 없다.\n\n[정확한 ID·호출별 집계·해시](prior-counts.json).\n'
 (A/'PRIOR_COUNTS.md').write_text(text);print(json.dumps({k:v for k,v in out.items() if k not in ['cases','input_hashes']},ensure_ascii=False))
if __name__=='__main__':main()
