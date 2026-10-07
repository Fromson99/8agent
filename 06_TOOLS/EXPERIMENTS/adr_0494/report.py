"""Render exact single-arm question records and measured final summaries."""
from pathlib import Path
import json,hashlib,statistics
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0494-source-workflow-other-cm';ART=A/'artifacts'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.relative_to(R))
def block(x):return '```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```'
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 m=read(A/'실험/manifest.json');z=read(ART/'metrics.json');ledger=read(ART/'retrieval-stage-ledger-validated.json');fixture=read(A/'product-cases.json');gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']};c=z['by_arm']['repaired'];audit=read(ART/'execution-audit.json');mechanism=read(ART/'mechanism-audit.json')
 table='| 문항 | 발견 | 읽기 | 전달 | 선택 | 게시 원문 | 검토 주장 | 기준답 일치 | 필수 출처 | 호출 시도 |\n|---|---:|---:|---:|---:|---:|---:|---|---:|---:|\n';reviewed=0;usage_receipts=0;non_success=[]
 import sqlite3
 for x in z['by_case']:
  p=ART/'run-001'/x['case_id']/'repaired';r=read(p/'result.json');s=r['stages'];reviewed+=x['claims']>0;usage_receipts+=len(r['usage'])
  table+='| '+' | '.join(map(str,[x['case_id'],*[len(s[k]) for k in ['discovered','read','presented','selected','final_sources']],x['claims'],x['correct'],str(x['gold_final'])+'/'+str(x['gold_total']),x['calls']]))+' |\n'
  with sqlite3.connect('file:'+str(p/'journal.sqlite')+'?mode=ro',uri=True) as d:
   for phase,status,receipt in d.execute("SELECT v.phase,a.status,a.receipt_json FROM model_attempt a JOIN model_view v USING(view_id) WHERE a.status!='SUCCEEDED'"):
    non_success.append({'case_id':x['case_id'],'phase':phase,'status':status,'receipt':json.loads(receipt) if receipt else None})
 for run in m['runs']:run.update(status='complete',sha256=sha(R/run['artifact_path']))
 cases=ledger['runs'][0]['arms'][0]['cases'];counts=[x['stages'][-1]['after_count'] for x in cases]
 ra=m['retrieval_accounting'];ra.update(corpus_total=z['corpus_total'],before_filter={'repaired':z['corpus_total']},after_filter={'repaired':sum(counts)},presented_total={'repaired':sum(counts)},presented_mean={'repaired':statistics.mean(counts)},presented_p50={'repaired':statistics.median(counts)},presented_p95={'repaired':max(counts)},golden_recall={'repaired':c['gold_recall']},selectivity={'repaired':statistics.mean(counts)/z['corpus_total']})
 ra['stage_ledger'].update(summary_run_id='run-001',artifact_path=rel(ART/'retrieval-stage-ledger-validated.json'),sha256=sha(ART/'retrieval-stage-ledger-validated.json'))
 m['results']={'status':'complete','by_arm':z['by_arm'],'comparisons':[],'comparison_note':'Single unchanged candidate; no baseline or A/B delta','judge_disagreements':None,'judge_note':z['judge_note'],'criteria':z['criteria'],'verdicts':z['verdicts'],'usage':{'new_product_attempts':c['calls'],'product_usage_receipts':usage_receipts,'new_product_usage':c['usage'],'new_judge_calls':z['judge_calls'],'new_judge_usage':z['judge_usage']},'latency':{'repaired':{k:c[k] for k in ['latency_p50_seconds','latency_p95_seconds']}},'error_taxonomy':sorted({x['failure_type'] for x in z['by_case'] if x['correct'] is not True}),'reviewed_answer_count':reviewed,'non_success_attempts':non_success,'main_wiring':'unchanged','mechanism_audit':mechanism,'source_integrity_checks':all(all(x['evidence_was_delivered'] and x['span_hashes_valid'] and x['excerpt_equals_spans'] for x in row['source_checks']) for row in audit['rows'])}
 for q in m['questions']:
  cid=q['case_id'];case=next(c for c in fixture['cases'] if c['case_id']==cid);parts=[f'# {cid} 전체 입출력','## 1. 실행 메타','ADR0494/run-001/repaired 단일 후보 신규 실행. 제품99파일은 ADR0493과 동일하다. 이전 결과는 baseline으로 복제하거나 재채점하지 않았다.','## 2. 사용자 질문 원문',case['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',block(gold[cid]),'## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별',block(next(c for c in cases if c['case_id']==cid)),'## 5. 제품 모델 호출 — run·arm별 실제 원문']
  folder=ART/'run-001'/cid/'repaired'
  for f in sorted(folder.rglob('*.json')):parts+=['### '+str(f.relative_to(folder)),block(read(f))]
  parts+=['## 6. 중간 LLM 호출 — router/compiler/verifier/repair','investigate/select_sources/compose/review/repair의 실제 요청·원응답·usage·trace는 위 JSON 원문에 포함한다. 실행하지 않은 단계를 성공으로 표시하지 않는다.','## 7. 채점 호출과 반복 판정']
  for f in sorted((ART/'run-001/judge'/cid).rglob('*.json')):parts+=['### '+str(f.relative_to(ART)),block(read(f))]
  parts+=['### 평가 결과',block(read(ART/'run-001/judged-results.json')['cases'][cid]),'## 8. 사례 최종 판정',block(next(x for x in z['by_case'] if x['case_id']==cid))]
  p=A/'실험'/q['file'];p.write_text('\n\n'.join(parts)+'\n');q['sha256']=sha(p)
 write(A/'실험/manifest.json',m)
 all_pass=all(z['verdicts'].values());front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Proposed' if all_pass else 'status: Rejected')
 sections=[('결정 요약',f"제품 코드를 바꾸지 않고 CM003·CM038을 각각1회 Qwen 실행했다. 검토 답변{reviewed}/2, 기준답 일치{c['correct']}/2, 필수 조문 회수율{c['gold_recall']:.1%}, 출처 관련성 precision{c['source_precision']}. 신규 제품{c['calls']}회 시도 + 평가{z['judge_calls']}회. 이 소표본 재확인은 MAIN 승격 근거가 아니다.\n\n"+block(z['verdicts'])),
 ('문제와 변경 전 구조','ADR0493은 페이지 동작 제공 및 cursor 오류복구를 CM018에서 확인했다. 사용자 요청에 따라 다른 두 CM에도 같은 후보가 동작하는지 확인한다. 제품 코드 변경0개,99개 파일과 공통 runtime은 부모와 동일하다. CM003/038의 이전 결과를 수정하거나 새 실험 점수로 합산하지 않았다.'),
 ('가설과 사전 판정 기준',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+block(z['criteria'])),
 ('실험 설계','단일 repaired arm, CM003 다음 CM038 각1회. Qwen qwen/qwen3.5-122b-a10b FP8 thinking off,14model/56tool/controller300초·출력2800. 공개145문서와 원문 세대·전송승인 범위를 유지한다. 두 제품 실행 뒤 각 문항 답변-only/출처-only 평가를 별도로1회씩 실행했다. baseline이 없으므로 paired delta/신규정답·회귀 추정은 해당 없음. 후보28개 계약 통과 기록은 동일 코드 부모에서 상속했으며 이번에 재실행했다고 세지 않는다.'),
 ('데이터·모델·재현성','[코드 동일성](artifacts/code-identity.json), [고정 입력](artifacts/frozen-design.json), [계획](PLAN.md). 제품에는 질문과 허용 공개 원문만 제공하며 gold는 평가 호출에만 제공했다. 공통 runtime/config는 sealed 복사본이다. model/data/source authorization/코드 hash를 전송 전 검사했다. immutable 반출속성·기존 MAIN 포인터는 변경하지 않았다. frozen-design의 known_limitations 중 inherited control 문구1개는 부모 utility의 잔존 설명이며 이번 arms/order/run은 명시적으로 단일 후보다. 역사적 기준 실행은 없다.'),
 ('결과',table+'\n\n'+block(z['by_arm'])),
 ('사례별 오류 분석',block([{k:x[k] for k in ['case_id','correct','judge_reason','failure_type','execution_error','publication_error','semantic_errors','limitations','phases','gold_shown','gold_final']} for x in z['by_case']])+'\n\n'+block(non_success)+'\n\n'+block(mechanism)),
 ('비용·지연·회수 규모',block(m['results']['usage'])+'\n\n'+block(m['results']['latency'])+f"\n\ncorpus {z['corpus_total']}개. p95는2건의 최대 관측값이다. 전체 시간과 controller 시간을 별도 기록했다. 시도수와 반환된 usage 기록 수가 다르면 실패 시도 비용은 확정할 수 없으며 비용 합계는 반환된 usage 기준이다."),
 ('해석','원문 읽기/실제 모델전달/선택/게시, 독립 검토를 통과한 주장, 기준답 일치를 분리한다. source ID gold hit는 항·호 텍스트가 완전히 확보됐다는 인증이 아니다. 사례별 원문 span 해시·실제전달·선택 보존은 실행 감사에서 확인했다. 과거와 이번 결과가 다르더라도 단회·비동시 평가로 개선효과를 확정하지 않는다.'),
 ('한계와 일반화 가능 범위','2개 기존 인샘플 문항 단회다. 같은 Qwen evaluator이며 사람 calibration, 법령·기준답 버전 독립확인, 변동성 추정은 없다. CM018은 이번에 실행하지 않았다. 전체48설계 시나리오와 v5 journal/완전한 canonical page병합/resume/feedback/GENOS 검증은 남는다.'),
 ('운영 결정·롤백 조건','새 제품 수정·운영 등록·MAIN 승격 없이 연구 후보만 명시적으로 실행했다. 실패도 원본과 함께 보존한다. 결과를 본 뒤 새 수정/재실행은 새 ADR로 기록한다.'),
 ('재현 명령','완료 기록을 덮어쓰지 않는다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+rel(A)+' --final`\n\n[질문별 원문](실험/README.md) · [지표](artifacts/metrics.json) · [실행 감사](artifacts/execution-audit.json)')]
 (A/'README.md').write_text('---'+front+'---\n\n# ADR0494: 최신 후보 CM003·CM038 확인\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(sections,1))+'\n')
 (A/'실험/README.md').write_text('# CM003·CM038 신규 실행\n\n'+table+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']}) — 전체 입력·원응답·평가·원장" for q in m['questions'])+'\n')
 am=read(ART/'manifest.json');paths={p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json'};paths.update((R/'06_TOOLS/EXPERIMENTS/adr_0494').glob('*.py'));paths.update(A/x for x in ['PLAN.md','product-cases.json','gold-cases.json'])
 cand=R/'02_BACKEND/lawrag/research/candidates/adr_0494/repaired';paths.add(cand/'candidate.json');paths.update(R/f['frozen_path'] for f in read(cand/'candidate.json')['revisions'][0]['files'])
 am['files']=[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input or measured execution/evaluation/audit receipt'} for p in sorted(paths)];write(ART/'manifest.json',am)
 print(table)
if __name__=='__main__':main()
