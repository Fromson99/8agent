"""Render sealed observations without model calls or modifications to product results."""
from pathlib import Path
import hashlib,json,statistics
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0438';T=R/'06_TOOLS/EXPERIMENTS/adr_0438';ARMS=['baseline','harness']
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(p.relative_to(R))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
def inventory():
 lock=read(A/'input-lock.json')['files'];files=[p for p in A.rglob('*') if p.is_file() and p!=A/'manifest.json' and not p.name.endswith('.log')]+[p for folder in [C,T] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
 rows=[{'path':rel(p),'sha256':lock.get(rel(p)) or sha(p),'bytes':p.stat().st_size,'description':'Hash-bound immutable input, exact provider request/response, execution state or offline report'} for p in sorted(set(files))]
 write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0438','files':rows})
def main():
 m=read(D/'실험/manifest.json');metrics=read(A/'metrics.json');cases=read(A/'dataset/product-cases.json');gold={g['id']:g for g in read(A/'grading/gold.json')['cases']};results=read(A/'results.json');rows=[]
 for num,c in enumerate(cases,1):
  cid=c['id'];text=f'# 질문 {num:03d} — {cid}\n\n## 1. 실행 메타\n\nADR0438 / run-001 / baseline, harness. gemini-3.1-flash-lite. exact provider payloads, 공개 동결 법률과 작성된 예시 질문.\n\n## 2. 사용자 질문 원문\n\n'+c['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n'+block(gold[cid])+'\n## 4. 제품 입력을 구성한 원값\n'+block(c)
  text+='\n### 회수·탈락 단계 원장 — run·arm별\n\n| arm | stage | before | added | discarded | after | gold before | gain | loss | gold after/total |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---|\n'
  for arm in ARMS:
   for s in read(A/'graded'/f'{cid}-{arm}.json')['stages']:
    text+=f"| {arm} | {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_before']} | {s['gold_added']} | {s['gold_discarded']} | {s['gold_after']}/{s['gold_total']} |\n"
  text+='\n원문 좌표와 탈락 근거는 [전체 원장](../artifacts/retrieval-ledger.json). discovered는 조회 메뉴에서 발견한 원문 ID, read는 모델에 전달한 구간이 있는 조문, adopted/present는 최종 답변에 쓰인 조문이다.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n'
  for arm in ARMS:
   text+='\n### '+arm+'\n'
   for folder in sorted((A/'calls'/cid/arm).glob('call-*')):
    for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
     if (folder/name).exists():text+='\n#### '+folder.name+'/'+name+'\n'+block(read(folder/name))
  text+='\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n위 task_interpret/task_navigation/task_evidence_review는 모두 제품 호출이며 총 예산에 포함된다. 아래 기록은 모델이 제안한 해석과 제어부의 실제 도구 결과·거절·완료 상태다.\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(results['cases'][cid][arm])
  text+='\n## 7. 채점 호출과 반복 판정\n\n모든 제품 출력을 봉인한 뒤 1회 익명 평가. 위치를 번갈아 배정. 전문가 calibration·반복 불일치율은 미측정.\n'
  for folder in sorted((A/'judges'/cid).glob('call-*')):
   for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
    if (folder/name).exists():text+='\n### '+name+'\n'+block(read(folder/name))
  text+='\n## 8. 사례 최종 판정\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(metrics['by_arm'][arm]['by_case'][cid])
  (D/'실험'/f'질문-{num:03d}-{cid}.md').write_text(text)
  cells=[]
  for arm in ARMS:
   v=metrics['by_arm'][arm]['by_case'][cid];passed=v['answer_pass'] if v['kind']=='answer' else v['guard_pass'];cells.append(('통과' if passed else '미통과')+f" ({v['calls']}회)")
  rows.append(f'| [{cid}](질문-{num:03d}-{cid}.md) | '+' | '.join(cells)+' |')
 (D/'실험/README.md').write_text('# 실제 질문 8개 × 2방식\n\n설명 질문6개와 보호 경계2개를 구분한다. 본문과 전체 호출·판정은 각 질문 링크에 있다.\n\n| 질문 | 기존 탐색 | 새 하네스 |\n|---|---|---|\n'+'\n'.join(rows)+'\n')
 counts={k:{a:metrics['by_arm'][a][k] for a in ARMS} for k in ['presented_total','presented_mean','presented_p50','presented_p95','selectivity']}
 m['retrieval_accounting'].update(corpus_total=metrics['corpus_total'],before_filter=metrics['corpus_total'],after_filter=statistics.mean(counts['presented_mean'].values()),golden_recall={a:metrics['by_arm'][a]['selected_required_recall'] for a in ARMS},**counts)
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'retrieval-ledger.json');m['runs'][0].update(status='complete',sha256=sha(A/'results.json'))
 total_calls=sum(v['calls'] for v in metrics['by_arm'].values());tokens={k:sum(v['usage'][k] for v in metrics['by_arm'].values()) for k in ['input_tokens','output_tokens','thinking_tokens','total_tokens']}
 m['results'].update(status='complete',by_arm=metrics['by_arm'],comparisons=metrics['comparisons'],judge_disagreements=0,judge_disagreement_note=metrics['judge_disagreement_note'],usage={'product_calls':total_calls,'product':tokens,'judge_usage':metrics['judge_usage']},latency={a:{'p50':metrics['by_arm'][a]['latency_p50'],'p95':metrics['by_arm'][a]['latency_p95']} for a in ARMS},error_taxonomy=sorted({v['judge']['error_type'] for a in metrics['by_arm'].values() for v in a['by_case'].values() if not(v['answer_pass'] or v['guard_pass'])}))
 write(D/'실험/manifest.json',m)
 summary=' / '.join(f"{a}: 설명 {metrics['by_arm'][a]['answer_pass']}/6, 보호 경계 자동판정 {metrics['by_arm'][a]['guard_pass']}/2" for a in ARMS)
 table='| 방식 | 설명 성공 | 보호 경계 자동판정 | FINISH | 필수 원문 읽기 | 호출 | 전체 지연 p50/p95 |\n|---|---:|---:|---:|---:|---:|---:|\n'+''.join(f"| {a} | {metrics['by_arm'][a]['answer_pass']}/6 | {metrics['by_arm'][a]['guard_pass']}/2 | {metrics['by_arm'][a]['finish_count']}/8 | {metrics['by_arm'][a]['read_required_recall']:.0%} | {metrics['by_arm'][a]['calls']} | {metrics['by_arm'][a]['latency_p50']:.1f}/{metrics['by_arm'][a]['latency_p95']:.1f}초 |\n" for a in ARMS)
 sections=[('결정 요약',summary+f'. 사전 성공 기준 통과={metrics["success_criteria_pass"]}. Proposed 유지, MAIN 변경 없음. 결과를 운영 품질 인증으로 해석하지 않는다.'),('문제와 변경 전 구조','이전 구현의 모의 계약·회귀61개가 통과했으나 실제 모델의 요청 해석·후보 선택·원문 읽기·근거 판단 성공은 확인되지 않았다. 이를 현재 작업 탐색 루프와 같은 자료·모델·예산에서 비교한다.'),('가설과 사전 판정 기준','설명 성공≥4/6, 보호 경계2/2, 기존 대비 회귀0, 인용/범위 위반0, 요청당20호출·180초 이내. 정확한 [사전 설계](artifacts/design-before-snapshot.json)와 [첫 호출 전 결속](artifacts/pre-call-manifest.json).'),('실험 설계','8개 질문마다 두 arm1회, 실행·익명 채점 순서를 번갈아 배정했다. 준비한 후보는 원래 첫 구현을 수정하지 않은 rev-001이다. 같은 snapshot의 기존 탐색과 하네스 객체를 명시 주입하며 운영 registry를 바꾸지 않았다. 하네스 정의는 실험 전용 검토 기록으로 결속했으며 운영 승인은 아니다. 결과 확인 후 코드·프롬프트·질문·판정을 고치거나 재실행하지 않았다.'),('데이터·모델·재현성','선택 공개 자본시장법 5be4de51a89dc664, 원문/좌표/버전/해시·전체 용어집·색인 동일. 별도 세대 뷰는 원본 불변 파일의 hardlink이며 정책 DB만 새 파일이다. 공개 법률의 고정 문서 실험이고 최신 법률 인증은 아니다. 새 Gemini 정책과 기존 동일 source fingerprint의 전송 근거를 승인 결속에 기록했으며 원문 export 플래그는 바꾸지 않았다. 실제 내부 데이터·비공개 질문 없음. 공통 GeminiExperimentClient 사용.'),('결과',table+'\n주의: 자동 채점은 미등록 개념의 내부 오류 출력도 통과시켰다. 하네스 보호 경계2/2는 정상 동작2/2가 아니다. 실제 동작은 미등록 개념 처리 실패, 매도 요청 거절 정상이다. 증권 두 질문의 자동 판정에도 불일치가 있어 기존1/6은 확정 성능 수치로 쓰지 않는다. [관측·채점 충돌](artifacts/diagnosis.md).\n\n[질문·전체 답변·판정](실험/README.md), [지표](artifacts/metrics.json). 답변 성공은 정답·근거·필수 원문 채택·계약 검사를 함께 통과해야 한다. FINISH와 의미 판정을 따로 집계한다.'),('사례별 오류 분석','[질문별 기록](실험/README.md)의 거절 행동·실패·의무 상태·답변을 확인한다. 별도 [관측 원인 분석](artifacts/diagnosis.md)에 실제 trace와의 연결을 남긴다. 실험 실패를 모의 테스트 통과로 상쇄하지 않는다.'),('비용·지연·회수 규모',f'제품 {total_calls}회, 입력 {tokens["input_tokens"]}·출력 {tokens["output_tokens"]}토큰. thinking 포함 전체 {tokens["total_tokens"]}. 오프라인 판정8회 계획, usage 전량 기록. 원문 범위 {metrics["corpus_total"]}조문. 이번 지연은 p.run 전체로 자료 초기화·사전 검증·모델 호출을 포함한다. 선행 파일 봉인·실험 setup은 제외한다. 루프 시간은 별도 controller_seconds이며 운영 GENOS 지연으로 외삽하지 않는다. 실제 청구액은 미측정.'),('해석','사용자가 의도한 실제 질문의 end-to-end 작동을 관찰한 개발용 probe다. 모델의 자가 완료 선언만으로 성공 처리하지 않는다. 정답/원문 기준은 제품 선택이 봉인된 뒤 별도 프로세스에서만 결합했다. 실패 후보와 시행착오는 보존한다.'),('한계와 일반화 가능 범위','직접 작성한 질문·단일 공개 법률·단회 실행이며 앞선 실패 사례를 알고 설계했다. 독립 holdout이 아니다. 채점은 동일 Gemini 계열의 단회 모델 판단으로 전문가 calibration·반복 불일치율 미측정. GENOS 모델·실제 내부 데이터·프로세스 재개·조직별 권한은 미검증이다. 운영 품질이나 비용 개선을 확정하지 않는다.'),('운영 결정·롤백 조건','Proposed, MAIN unchanged. 이번 실험에서 운영 코드/기본 설정/활성 포인터/완료 원문 세대를 수정하지 않았다. 개선이 필요하면 이 결과를 보존하고 새 ADR로 후보를 만든다. 별도 분리 검증과 명시적 MAIN 절차 전 활성화하지 않는다.'),('재현 명령','`PYTHONPATH=02_BACKEND .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0438/run_probe.py`\n\n완료 runs가 있으면 재실행을 거부한다. 새로운 모델 실행·재채점은 새 ADR에서 수행한다. `score.py`는 기존 judges/metrics 덮어쓰기를 거부한다. 검증: `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation --final` 및 `graph --adr-root 04_EXPERIMENTS/ADR`.')]
 front=(D/'README.md').read_text().split('---',2)[1]
 (D/'README.md').write_text('---'+front+'---\n\n# 개념 정의·범위 하네스 실제 모델 검증\n'+''.join(f'\n## {i}. {title}\n\n{body}\n' for i,(title,body) in enumerate(sections,1)))
 (D/'RESULT.md').write_text('# 실제 질문 비교 결과\n\n'+summary+'\n\n'+table+'\n주의: 위 보호 경계 점수는 오류 출력을 통과시킨 단회 자동 판정이다. 실제 하네스는 미등록 개념 확인 처리 실패, 매도 요청 거절 정상이다. [채점 충돌 분석](artifacts/diagnosis.md).\n\n[상세 결정문](README.md) · [질문과 전체 답변](실험/README.md)\n')
 inventory();print(summary)
if __name__=='__main__':main()
