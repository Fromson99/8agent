"""Generate CM result reports only after sealed execution and separate scoring exist."""
from pathlib import Path
import json,statistics
from run_probe import R,D,A,C,ARMS,read,sha,rel
T=Path(__file__).parent
HEADINGS=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
def main():
 m=read(D/'실험/manifest.json');metrics=read(A/'metrics.json');cases=read(A/'dataset/product-cases.json');gold={c['id']:c for c in read(A/'grading/gold.json')['cases']};results=read(A/'results.json');index=[];sample=[]
 for i,c in enumerate(cases,1):
  cid=c['id'];text=f'# 질문 {i:03d} — {cid}\n\n## 1. 실행 메타\n\nADR0444/run-001, baseline/schema, gemini-3.1-flash-lite. CM 원 질문과 업무 문맥, 동결된 공개159문서 전체. 실제 provider payload exact.\n\n## 2. 사용자 질문 원문\n\n'+c['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n'+block(gold[cid])+'\n## 4. 제품 입력을 구성한 원값\n'+block(c)+'\n### 회수·탈락 단계 원장 — run·arm별\n\n| arm | stage | before | added | discarded | after | gold before | gain | loss | gold after/total |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---|\n'
  for arm in ARMS:
   for s in read(A/'graded'/f'{cid}-{arm}.json')['stages']:text+=f"| {arm} | {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_before']} | {s['gold_added']} | {s['gold_discarded']} | {s['gold_after']}/{s['gold_total']} |\n"
  text+='\n[전용 좌표·탈락 사유 원장](../artifacts/retrieval-ledger.json). 원문33,443개 중 구조 좌표 있는33,387개가 정본 좌표 원장에 포함되며 미구조56개는 검색에서 제거하지 않고 별도 측정한다.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n'
  for arm in ARMS:
   text+='\n### '+arm+'\n'
   for folder in sorted((A/'calls'/cid/arm).glob('call-*')):
    for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
     if (folder/name).exists():text+='\n#### '+folder.name+'/'+name+'\n'+block(read(folder/name))
  text+='\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n모든 선택·판단 호출은 위 navigation에 포함. 별도 router 없음.\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(results['cases'][cid][arm])
  text+='\n## 7. 채점 호출과 반복 판정\n\n제품 출력과 좌표 capture 봉인 후 케이스별 기준만 보내 단회 익명 판정했다. 위치 교차, 재채점·다수결·전문가 calibration 없음. 도구 실행은 evaluator가 추측하지 않고 실행 receipt로 확인한다.\n'
  for folder in sorted((A/'judges'/cid).glob('call-*')):
   for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
    if (folder/name).exists():text+='\n### '+name+'\n'+block(read(folder/name))
  text+='\n## 8. 사례 최종 판정\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(metrics['by_arm'][arm]['by_case'][cid])
  filename=f'질문-{i:03d}-{cid}.md';(D/'실험'/filename).write_text(text);index.append(f'| [{cid}]({filename}) | '+' | '.join(('통과' if metrics['by_arm'][a]['by_case'][cid]['pass'] else '미통과')+f" ({metrics['by_arm'][a]['by_case'][cid]['calls']}회)" for a in ARMS)+' |')
  sample.append('## '+cid+'\n\n'+c['question']+'\n\n'+''.join('### '+a+'\n\n'+(results['cases'][cid][a].get('output') or {}).get('answer',{}).get('text','실행 실패')+'\n\n' for a in ARMS))
 (D/'실험/README.md').write_text('# 실제 CM6 질문별 기록\n\n전체159문서에서 동일 질문을 두 방식으로 단회 실행.\n\n| 질문 | 기존 탐색 | 스키마 후보 |\n|---|---|---|\n'+'\n'.join(index)+'\n')
 table='| 방식 | 엄격 성공 | 의미 판정 | 필수 원문 읽기 | 호출 | 전체 지연 p50/p95 |\n|---|---:|---:|---:|---:|---:|\n'+''.join(f"| {a} | {metrics['by_arm'][a]['correct']}/6 | {metrics['by_arm'][a]['semantic_correct']}/6 | {metrics['by_arm'][a]['read_required_recall']:.0%} | {metrics['by_arm'][a]['calls']} | {metrics['by_arm'][a]['latency_p50']:.1f}/{metrics['by_arm'][a]['latency_p95']:.1f}초 |\n" for a in ARMS)
 counts={k:{a:metrics['by_arm'][a][k] for a in ARMS} for k in ['presented_total','presented_mean','presented_p50','presented_p95','selectivity']};m['retrieval_accounting'].update(corpus_total=metrics['corpus_total'],before_filter=metrics['corpus_total'],after_filter=statistics.mean(counts['presented_mean'].values()),golden_recall={a:metrics['by_arm'][a]['selected_required_recall'] for a in ARMS},**counts);m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'retrieval-ledger.json');m['runs'][0].update(status='complete',sha256=sha(A/'results.json'))
 usage={k:sum(v['usage'][k] for v in metrics['by_arm'].values()) for k in ['input_tokens','output_tokens','thinking_tokens','total_tokens']};calls=sum(v['calls'] for v in metrics['by_arm'].values());m['results'].update(status='complete',by_arm=metrics['by_arm'],comparisons=metrics['comparisons'],judge_disagreements=0,judge_disagreement_note=metrics['judge_disagreement_note'],usage={'product_calls':calls,'product':usage,'judge_usage':metrics['judge_usage']},latency={a:{'p50':metrics['by_arm'][a]['latency_p50'],'p95':metrics['by_arm'][a]['latency_p95']} for a in ARMS},error_taxonomy=sorted({v['judge']['error_type'] for a in metrics['by_arm'].values() for v in a['by_case'].values() if not v['pass']}));write(D/'실험/manifest.json',m)
 bodies=[f"실제 CM6 비교 관측. 사전 성공 기준 통과={metrics['success_criteria_pass']}. Proposed, MAIN unchanged.\n\n"+table,'모의8개 결과 이후 사용자가 실제CM 데이터를 요청했다. 기능을 고치는 실험이 아니라 동일 후보의 실데이터 적용 관측이다.','후보 성공≥4/6, 기존만 성공하는 회귀0, scope/quote 위반0, 요청당12모델 호출·180초 controller 한도. [사전 설계](artifacts/design-before-snapshot.json).','CM51 원본에서1·11·21·31·41·51번을 결과 전에 고정했다. 정답으로159문서 범위를 좁히지 않았다. baseline은 활성 release navigation, 후보는 ADR0442 동결 바이트 및 소유block 어댑터로 기존 Pipeline에 객체 주입했다. retrieve 이후 select/assemble/answer/Result 계약은 원래 경로다.','질문·기준답변 정본, 승인된 공개 원문·용어집·색인 해시 동일성 확인. 초기 자동 승인 거절 후 실제 전송 승인 상태는 별도 receipt로 보존한다. 원문 export 플래그와 MAIN 포인터는 변경하지 않는다. 실제 CM 현업 질문이며 실제 GENOS 모델/서빙 시험은 아니다.',table+'\n[질문별 전체 기록](실험/README.md) · [지표](artifacts/metrics.json). 성공은 의미 판정과 FINISH·필수 근거 채택·원문 인용·Result 계약을 함께 만족해야 한다.','[실행 검토](artifacts/review.md)에 실제 trace와 실패/채점 해석 한계를 기록했다. 제품 입력·후보·기준답변·채점 기준은 결과를 보고 바꾸지 않았다.',f'제품{calls}호출. 입력{usage["input_tokens"]}·출력{usage["output_tokens"]}토큰. 실제 청구액 미측정. 전체 지연은 요청별 자료/용어집 초기화 및 모델/하위 단계를 포함한다. controller_seconds와 구분. 원문33,443개 중 좌표33387개 원장 및 미구조56개 별도 집계.','6개 실제 업무 사례의 개발용 probe. 과거실험에서 일부 질문을 본 상태이므로 holdout 아님. 소표본 결과를 CM51 전체/새질문으로 일반화하지 않는다.','단회 Gemini 기반이며 전문가 판정 미실행. 기준답변은 원 현업 답변이고 현재법 인증이 아니다. 원문 버전 차이는 별도 표시. 임베딩 검색 미연결. 기존 ID·완료·복구 문제는 알고리즘 수정 없이 그대로 관찰한다. API 호출 자체 실패와 모델 판단 실패를 구분한다.','Proposed, MAIN unchanged. 후보와 원시 산출물은 격리되어 운영에서 자동 발견하지 않는다. 이번 결과로 자동 승격하지 않는다.','`run_probe.py --check`는 모델 없이 실제 원문 adapter를 확인한다. `run_probe.py` 및 `score.py`는 기존 모델실행/채점 덮어쓰기를 거부한다. 새 반복/개선은 새ADR. 최종 `adr_structure.py validate --final` 및 `graph`를 기록한다.']
 front=(D/'README.md').read_text().split('---',2)[1];(D/'README.md').write_text('---'+front+'---\n\n# 실제 CM6 스키마 도구 탐색 비교\n'+''.join(f'\n## {i}. {h}\n\n{b}\n' for i,(h,b) in enumerate(zip(HEADINGS,bodies),1)))
 (D/'SAMPLES.md').write_text('# 실제 CM 샘플 답변\n\n'+table+'\n실제 CM6, 전체159문서 검색, 동일 모델/예산. 전문가 품질 인증이나 GENOS 운영 시험 아님.\n\n'+'\n'.join(sample)+'\n[전체 trace와 채점](실험/README.md) · [오류 검토](artifacts/review.md)\n')
 files=[p for folder in [A,C,T] for p in folder.rglob('*') if p.is_file() and p!=A/'manifest.json' and '__pycache__' not in p.parts];write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0444','files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen actual CM input/code, exact provider payload or isolated evaluation report'} for p in sorted(set(files))]});print(table)
if __name__=='__main__':main()
