"""Readable 61-case review, alongside complete machine/raw records."""
import json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0498-gemma4-fp8-compatible-schema-cm51-fsc10';ART=A/'artifacts'
def read(p):return json.loads(p.read_text())
def main():
 f=read(A/'product-cases.json');gold={x['case_id']:x for x in read(A/'gold-cases.json')['cases']};metrics={x['case_id']:x for x in read(ART/'metrics.json')['by_case']};diag={x['case_id']:x for x in read(ART/'workflow-diagnostics.json')['by_case']};questions={x['case_id']:x for x in read(A/'실험/manifest.json')['questions']}
 with sqlite3.connect('file:'+str(R/f['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
  names={sid:(name,article) for sid,name,article in db.execute("SELECT id,json_extract(json,'$.document_name'),article FROM source")}
 sections=['# 61문항별 읽기 쉬운 진단','검토 답변과 원문 패키지 게시를 분리한다. 기준답은 보존된 채점 기준이며 현행 법률의 독립 검증 결과가 아니다. 모든 요청·응답·도구 원문은 각 항목 끝의 상세 기록에 있다.','[종합 리포트](README.md)']
 stage_names={'discovered':'발견 전','read':'발견 후 읽기 전','presented':'읽기 후 모델 전달 전','selected':'전달 후 선택 전','payload_sources':'선택 후 저장 전','final_sources':'저장 후 게시 전','delivered':'게시됨'}
 for case in f['cases']:
  cid=case['case_id'];x=metrics[cid];d=diag[cid];r=read(ART/'run-001'/cid/'gemma/result.json');t=read(ART/'run-001'/cid/'gemma/trace.json')
  status='검토 답변 기준답 일치' if x['correct'] is True else '채점 실패/미확인' if x['correct'] is None else '검토 답변 미완성' if not x['claims'] else '검토 답변 기준답 불일치'
  s=d['stage_counts'];texts=[f'## {cid}: {status}',case['question'],f"발견 {s.get('discovered',0)} → 읽기 {s.get('read',0)} → 전달 {s.get('presented',0)} → 선택 {s.get('selected',0)} → 게시 {s.get('final_sources',0)}조문. 검토 주장 {x['claims']}개. 모델 {x['calls']}회, 전체 {x['seconds']:.1f}초.",'### 실제 검토 답변',r.get('result',{}).get('answer',{}).get('text','') if x['claims'] else '검토를 통과해 결과에 남은 주장이 없다. 원문 패키지가 게시되었더라도 답변 성공으로 세지 않는다.','### 보존 기준답',gold[cid]['reference_answer'],'### 평가 이유',x['judge_reason'],'### 필수 원문 경로']
  for sid in gold[cid]['decisive_source_ids']:
   name,article=names[sid];last=d['required_source_first_missing_stage'][sid];texts.append(f'- {name} {article}: {stage_names[last]} (조문 ID 단위. 전체 항·호 확보를 뜻하지 않음).')
  texts+=['### 실제 게시 원문']
  cards=t.get('source_bundle',{}).get('sources',[])
  if not cards or x['publication_status']!='PUBLISHED':texts.append('게시된 원문 없음.')
  else:
   texts+=list(dict.fromkeys(f"- {c['document_name']} — {c['coordinate_label']} ({c['tier']})" for c in cards))
  texts+=['### 실패와 복구 기록']
  for err in d['workflow_errors']:
   a=err['actual'];texts.append(f"- {err['message']} / 동작 `{a.get('tool')}` / 오류가 다음 입력에 반환됨={err['next_successful_view_received_error']} / 다음 응답에서 같은 인자 반복={err['same_tool_args_in_next_proposal']} / 수정 동작 제공={bool(err['corrective_actions'])}.")
  sem=list(dict.fromkeys(e.get('message','') for e in d['semantic_events'] if not e.get('message','').startswith('workflow operations rejected')))
  texts += ['- '+s for s in sem]
  if not d['workflow_errors'] and not sem:texts.append('도구·의미 검증 거부 기록 없음. 이것이 법률 판단의 정확성을 보증하지는 않는다.')
  if x['execution_error']:texts.append('- 서버 실행 오류: '+x['execution_error']['type']+' / '+x['execution_error']['message'])
  texts+=['- 종료/한계: '+str(v) for v in d['limitations']]
  texts.append(f"[전체 입력·원응답·원문·채점 기록](실험/{questions[cid]['file']})")
  sections.append('\n\n'.join(texts))
 (A/'CASE_REVIEW.md').write_text('\n\n'.join(sections)+'\n');print('61 readable case reviews')
if __name__=='__main__':main()
