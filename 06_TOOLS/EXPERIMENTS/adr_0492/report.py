"""Render sealed paired evidence and final status; no model calls or product edits."""
import hashlib,json,sqlite3,statistics
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0492-source-article-read-scope';ART=A/'artifacts';ARMS=['baseline','repaired']
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.relative_to(R))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def block(x):return '```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```'
def main():
 m=read(A/'실험/manifest.json');metric=read(ART/'metrics.json');ledger=read(ART/'retrieval-stage-ledger-validated.json');prod=read(A/'product-cases.json');gold={x['case_id']:x for x in read(A/'gold-cases.json')['cases']}
 table='| 반복 | 문항 | 방식 | 기준답 일치 | 내부/게시 gold | 카드 | 게시 | 호출 | 전체 초 |\n|---|---|---|---|---:|---:|---|---:|---:|\n'
 for x in metric['by_case']:
  table+=f"| {x['run_id']} | {x['case_id']} | {'상속 기준' if x['arm']=='baseline' else '신규 후보'} | {x['correct']} | {x['gold_payload']}/{x['gold_final']} (분모{x['gold_total']}) | {x['card_count']} | {x['publication_status']} | {x['calls']} | {x['seconds']:.1f} |\n"
 for run in m['runs']:
  run.update(status='complete',sha256=sha(R/run['artifact_path']))
 la={x['arm_id']:x for x in ledger['runs'][-1]['arms']};counts={a:[c['stages'][-1]['after_count'] for c in la[a]['cases']] for a in ARMS}
 r=m['retrieval_accounting'];r.update(corpus_total=metric['corpus_total'],before_filter={a:metric['corpus_total'] for a in ARMS},after_filter={a:sum(counts[a]) for a in ARMS},presented_total={a:sum(counts[a]) for a in ARMS},presented_mean={a:round(statistics.mean(counts[a]),4) for a in ARMS},presented_p50={a:statistics.median(counts[a]) for a in ARMS},presented_p95={a:max(counts[a]) for a in ARMS},golden_recall={a:sum(c['stages'][-1]['gold_after'] for c in la[a]['cases'])/sum(c['gold_total'] for c in la[a]['cases']) for a in ARMS},selectivity={a:statistics.mean(counts[a])/metric['corpus_total'] for a in ARMS})
 r['stage_ledger'].update(summary_run_id='run-001',artifact_path=rel(ART/'retrieval-stage-ledger-validated.json'),sha256=sha(ART/'retrieval-stage-ledger-validated.json'))
 m['results']={'status':'complete','by_arm':metric['by_arm'],'comparisons':[{'arms':ARMS,'metric':'stored_reference_agreement','delta':metric['paired_delta'],**metric['paired_outcomes']}],'judge_disagreements':None,'judge_note':metric['judge_note'],'criteria':metric['criteria'],'verdicts':metric['verdicts'],'usage':{'product_calls':sum(x['calls'] for x in metric['by_arm'].values()),'product':{a:x['usage'] for a,x in metric['by_arm'].items()},'offline_evaluator':metric['judge_usage'],'judge_calls':metric['judge_calls']},'latency':{a:{k:x[k] for k in ['latency_p50_seconds','latency_p95_seconds']} for a,x in metric['by_arm'].items()},'error_taxonomy':sorted({x['failure_type'] for x in metric['by_case'] if x['correct'] is not True}),'main_wiring':'unchanged'}
 for i,case in enumerate(prod['cases'],1):
  cid=case['case_id'];lines=[f'# 질문 {i:03} — {cid}','## 1. 실행 메타','ADR-0492 run-001: baseline은 ADR0491 CM018 결과 상속, repaired만 신규 Qwen 호출. 각 제품 실행의 started_at·입출력·지연 원본은 아래 exact JSON.','## 2. 사용자 질문 원문',case['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',block(gold[cid]),'## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별','| run | arm | stage | before | added | discarded | after | gold before/+/-/after | recall |\n|---|---|---|---:|---:|---:|---:|---|---:|']
  for run in ledger['runs']:
   for arm in run['arms']:
    c=next(x for x in arm['cases'] if x['case_id']==cid)
    for s in c['stages']:lines.append(f"| {run['run_id']} | {arm['arm_id']} | {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_before']}/{s['gold_added']}/{s['gold_discarded']}/{s['gold_after']} | {s['golden_recall']} |")
  lines+=['정확한 후보·gold 탈락 좌표 및 이유:',block({'runs':[{'run_id':run['run_id'],'arms':[{'arm_id':ar['arm_id'],'case':next(c for c in ar['cases'] if c['case_id']==cid)} for ar in run['arms']]} for run in ledger['runs']]}),'## 5. 제품 모델 호출 — run·arm별 실제 원문']
  for run in ['run-001']:
   for arm in ARMS:
    p=ART/run/cid/arm;lines+=['### '+run+' / '+arm]
    for f in sorted(p.rglob('*.json')):lines += ['#### '+str(f.relative_to(p)),block(read(f))]
  lines += ['## 6. 중간 LLM 호출 — router/compiler/verifier/repair','앞의 exact request·provider response·journal trace에 실제 발생한 investigate/select_sources/compose/review와 오류를 보존했다. 미실행 단계는 성공으로 표시하지 않는다.','## 7. 채점 호출과 반복 판정']
  for run in ['run-001']:
   lines+=['### '+run]
   for f in sorted((ART/run/'judge'/cid).rglob('*.json')):lines+=['#### '+str(f.relative_to(ART)),block(read(f))]
   lines+=['익명 위치와 채점 결과',block(read(ART/run/'judged-results.json')['cases'][cid])]
  lines+=['## 8. 사례 최종 판정',block([x for x in metric['by_case'] if x['case_id']==cid])]
  path=A/'실험'/m['questions'][i-1]['file'];path.write_text('\n\n'.join(lines)+'\n');m['questions'][i-1]['sha256']=sha(path)
 write(A/'실험/manifest.json',m)
 b=metric['by_arm']['baseline'];c=metric['by_arm']['repaired'];front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected' if not all(metric['verdicts'].values()) else 'status: Proposed')
 sections=[('결정 요약',f"Qwen 실제 제품 12회(3문항×2방식×2반복) 검증 완료. v3 기준답 일치 {b['correct']}/6, v4 {c['correct']}/6. 사용자 게시 출처 recall v3 {b['gold_recall']:.1%}, v4 {c['gold_recall']:.1%}. 내부 선택 payload recall은 별도 v3 {b['payload_gold_recall']:.1%}, v4 {c['payload_gold_recall']:.1%}. 사전 판정: {json.dumps(metric['verdicts'],ensure_ascii=False)}. 인샘플이며 MAIN·GENOS 불변."),
 ('문제와 변경 전 구조','수정설계서 전체의 opt-in v4 기존 구현을 현행 v3와 동시 비교했다. 작은 선택 schema, 핵심/보완 역할, 관계 메뉴, 반복 복구, 별도 source bundle을 하나의 통합 후보로 취급한다. 이전 구현에서 등록한 opt-in 경로는 이미 존재하며 이 실험 안에서 제품 코드·registry를 새로 수정하지 않았다. 동일 frozen snapshot에서 두 실행 경로를 선택한다.'),
 ('가설과 사전 판정 기준',m['design']['success_criteria']+'\n\n'+block(metric['criteria'])),
 ('실험 설계','같은 CM003/018/038 질문, 공개145문서 범위, source/index 세대, Qwen FP8 thinking off, 온도0. 각 방식 문항당 모델14/도구56/controller300초/출력2800/입력60000 bound. 실행·익명 평가 순서를 문항과 반복별로 교대했다. 초기 자원 로딩을 포함한 전체 시간도 기록한다. 제품 완료 후에만 gold를 독립 evaluator에 제공했다. 결과를 보고 제품을 수정하거나 추가 재실행하지 않았다.'),
 ('데이터·모델·재현성','기존 CM3 제품 질문·기준답·결정조문을 그대로 동결. source RAW hash와 store hash, navigation/fulltext manifest, glossary binding, 모델 정책·export receipt·코드99파일 snapshot을 검증했다. 공개 원문 승인과 현재 Qwen 지시를 request-scoped export rebind로 결속하고 immutable 원본 export_allowed=false는 유지했다. initial seal은 첫 호출 전에 사용자 게시 기준을 명확히 하는 방식으로 보완했고 원본 seal·무호출 점검 기록을 보존했다. 최종 설계 동결 후 모델 호출 시작.'),
 ('결과',table+'\n\n'+block(metric['by_arm'])+'\n\nPaired outcomes: '+block(metric['paired_outcomes'])),
 ('사례별 오류 분석',block([{k:x[k] for k in ['run_id','case_id','arm','execution_error','publication_error','semantic_errors','limitations','phases','relation_families']} for x in metric['by_case']])),
 ('비용·지연·회수 규모',block(m['results']['usage'])+'\n\n'+block(m['results']['latency'])+f"\n\n공개 scope canonical 조문 {metric['corpus_total']}개. 내부 payload_sources와 실제 게시 final_sources를 각각 계측했다. 미게시 자료·후보·Tier3는 사용자 회수율에 넣지 않았다. 카드의 relevance 판정은 gold 포함 여부와 독립이며 자동 채점이다. 빈 목록 precision은 null이다. 지연 p95는 표본6개의 최댓값 근사이며 현장 추정치가 아니다."),
 ('해석','원문을 읽었는지, 모델에게 제시했는지, 선택이 저장됐는지, 원문 묶음이 만들어졌는지, outbox로 게시됐는지는 별도다. 내부 출처 선택 개선이 있어도 실제 게시에 도달하지 못하면 사용자가 받는 출처 품질 개선으로 판정하지 않는다. 저장된 기준답 일치 또한 현재 법령 해석의 확정 인증이 아니다.'),
 ('한계와 일반화 가능 범위','CM3는 인샘플이며 두 반복으로 일반 성능을 추정하지 않는다. 각 출력은 익명 Qwen 단회 채점으로 judge calibration·동일출력 재채점 불일치 미측정. 원문 정확 범위 무결성은 검사하지만 독립 gold span에 대한 항·호 수준 recall은 미측정이다. 실제 GENOS 내부 모델·권한·화면은 접근하지 않았다. 이 공개 시험 세대는 export_allowed=false이므로 실험별 외부 전송 승인과 v4의 동등성 게시 검사가 충돌하는 환경상 한계가 있다. source 품질과 guard 호환성 문제를 구분해 해석한다.'),
 ('운영 결정·롤백 조건','MAIN 기본·활성 릴리스·불변 원본을 수정하지 않았다. 결과를 본 뒤 수정·재실행·재채점하려면 새 ADR을 사용한다. 실패한 원시 기록과 코드 revision을 보존하며 이 인샘플 기록만으로 승격하지 않는다.'),
 ('재현 명령','완료 기록을 덮어쓰지 않는다. 새 ADR에서 이 동결 입력으로 반복한다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+rel(A)+' --final`\n\n[질문별 전체 입출력](실험/README.md) · [상세 측정](artifacts/metrics.json) · [사전 계획](PLAN.md) · [산출물 해시](artifacts/manifest.json)')]
 (A/'README.md').write_text('---'+front+'---\n\n# ADR-0492: Qwen 출처 계층 v3-v4 동시 반복 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(sections,1))+'\n')
 (A/'실험/README.md').write_text('# Qwen v3-v4 반복 검증\n\n'+table+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']}) — 모든 run·arm 입력·원응답·채점·원장" for q in m['questions'])+'\n')
 paths={p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json'};paths.update((R/'06_TOOLS/EXPERIMENTS/adr_0492').glob('*.py'));paths.update(A/x for x in ['PLAN.md','product-cases.json','gold-cases.json'])
 cand=R/'02_BACKEND/lawrag/research/candidates/adr_0492/repaired';paths.add(cand/'candidate.json');paths.update(R/x['frozen_path'] for x in read(cand/'candidate.json')['revisions'][0]['files'])
 am=read(ART/'manifest.json');am['files']=[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Sealed code/data or actual measured receipt; precall archives are prior setup versions, not product results','contains_raw_prompts_and_outputs':p.suffix=='.json' and any(r in str(p) for r in ['run-001'])} for p in sorted(paths)];write(ART/'manifest.json',am)
 print(table)
if __name__=='__main__':main()
