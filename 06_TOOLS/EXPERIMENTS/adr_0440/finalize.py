"""Render immutable provider IO and comparison receipts after frozen scoring."""
import json,hashlib,statistics
from pathlib import Path
from lawrag.platform.workspace import load_layout
R=load_layout().root;D=R/'04_EXPERIMENTS/ADR/ADR-0440-task-harness-flash-medium';A=D/'artifacts';OLD=R/'04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation';ARMS=['baseline','flash-medium']
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(p.relative_to(R))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
def main():
 m=read(D/'실험/manifest.json');metrics=read(A/'metrics.json');results=read(A/'results.json');cases=read(A/'dataset/product-cases.json');gold={g['id']:g for g in read(A/'grading/gold.json')['cases']};rows=[]
 for num,c in enumerate(cases,1):
  cid=c['id'];text=f'# {cid}\n\n## 1. 실행 메타\n\nADR0440 / run-001. baseline은 ADR0438/harness 과거 출력. flash-medium은 gemini-3.8-flash, thinking=medium 신규 실행.\n\n## 2. 사용자 질문 원문\n\n'+c['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n'+block(gold[cid])+'\n## 4. 제품 입력을 구성한 원값\n'+block(c)+'\n### 회수·탈락 단계 원장 — run·arm별\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(read(A/'graded'/f'{cid}-{arm}.json'))
  text+='\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n'
  for arm in ARMS:
   folder=OLD/'artifacts/calls'/cid/'harness' if arm=='baseline' else A/'calls'/cid/arm;text+='\n### '+arm+'\n'
   for call in sorted(folder.glob('call-*')):
    for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
     if (call/name).exists():text+='\n#### '+call.name+'/'+name+'\n'+block(read(call/name))
  text+='\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n위 해석·탐색·근거 검토 모두 제품 호출 예산에 포함. 원래 하네스 코드를 수정하지 않았다.\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(results['cases'][cid][arm])
  text+='\n## 7. 채점 호출과 반복 판정\n\n양쪽 출력을 같은 Gemini3.8Flash medium 단회 평가자로 새로 채점했다. 기존 ADR0438 판정을 수정하지 않았다. 익명 위치를 교대. FINISH·오류 상태의 사전 기계검사를 함께 적용했다.\n'
  for call in sorted((A/'judges'/cid).glob('call-*')):
   for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
    if (call/name).exists():text+='\n### '+call.name+'/'+name+'\n'+block(read(call/name))
  text+='\n## 8. 사례 최종 판정\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(metrics['by_arm'][arm]['by_case'][cid])
  (D/'실험'/f'질문-{num:03d}-{cid}.md').write_text(text)
  a=metrics['by_arm']['flash-medium']['by_case'][cid];rows.append(f"| [{cid}](질문-{num:03d}-{cid}.md) | {a['status']} / {a['phase']} | {a['read_count']} | {a['calls']} | {a['answer_pass'] if a['kind']=='answer' else a['guard_pass']} |")
 (D/'실험/README.md').write_text('# 동일8개 질문의 모델 상향 비교\n\n각 링크에 생략 없는 실제 요청·응답·채점·하네스 상태를 보존했다.\n\n| 질문 | 상태 | 읽은 조문 | 호출 | 통과 |\n|---|---|---:|---:|---|\n'+'\n'.join(rows)+'\n')
 counts={k:{a:metrics['by_arm'][a][k] for a in ARMS} for k in ['presented_total','presented_mean','presented_p50','presented_p95','selectivity']};m['retrieval_accounting'].update(corpus_total=metrics['corpus_total'],before_filter=metrics['corpus_total'],after_filter=statistics.mean(counts['presented_mean'].values()),golden_recall={a:metrics['by_arm'][a]['selected_required_recall'] for a in ARMS},**counts);m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'retrieval-ledger.json');m['runs'][0].update(status='complete',sha256=sha(A/'results.json'))
 candidate=metrics['by_arm']['flash-medium'];judge=metrics['judge_usage'];cost=(candidate['usage']['input_tokens']*0.75+(candidate['usage']['output_tokens']+candidate['usage']['thinking_tokens'])*3.75)/1e6;judgecost=sum((u.get('input_tokens',0)*0.75+((u.get('output_tokens') or 0)+(u.get('thinking_tokens') or 0))*3.75)/1e6 for u in judge)
 m['results'].update(status='complete',by_arm=metrics['by_arm'],comparisons=metrics['comparisons'],judge_disagreements=None,judge_disagreement_note='Single uncalibrated evaluator; repetition disagreement unmeasured',usage={'new_product_calls':candidate['calls'],'new_product':candidate['usage'],'historical_baseline_not_recalled':True,'judge_usage':judge,'estimated_new_product_usd':cost,'estimated_judge_usd':judgecost,'actual_billing_unmeasured':True},latency={a:{'p50':metrics['by_arm'][a]['latency_p50'],'p95':metrics['by_arm'][a]['latency_p95']} for a in ARMS},error_taxonomy=['other:model_or_contract_failure'])
 write(D/'실험/manifest.json',m)
 table='| 모델 설정 | 정의·범위 완료 | 보호 질문 | FINISH | 필수 원문 읽기 | 제품 호출 |\n|---|---:|---:|---:|---:|---:|\n'+''.join(f"| {a} | {metrics['by_arm'][a]['answer_pass']}/6 | {metrics['by_arm'][a]['guard_pass']}/2 | {metrics['by_arm'][a]['finish_count']} | {metrics['by_arm'][a]['read_required_recall']:.0%} | {metrics['by_arm'][a]['calls']} |\n" for a in ARMS)
 diagnosis=(A/'diagnosis.md').read_text() if (A/'diagnosis.md').exists() else '실제 해석·거절 행동·미완료 의무는 질문별 기록에 있다. 단회 모델 채점은 전문가 확정 평가가 아니다.'
 sections=[('결정 요약',f'Gemini3.8Flash medium으로 상향하여 동일 하네스를 실행했다. 사전 성공 기준 통과={metrics["success_criteria_pass"]}. Proposed, 운영 MAIN·전역 기본 모델 변경 없음.'),('문제와 변경 전 구조','ADR0438 첫 하네스는6개 설명 질문 모두 해석 좌표 오류로 종료했다. 사용자가 중상 정도로 모델 상향을 요청했다. 코드·프롬프트·자료를 유지하고 모델+추론설정 묶음의 효과를 본다.'),('가설과 사전 판정 기준','설명4/6 이상, 보호2/2, 회귀0, 잘못된 인용·범위 탈출0, 요청20회·180초. [동결 설계](artifacts/frozen-design.json). 기준과 후보 모두 같은 새 채점기로 평가하며 설명은FINISH, 보호 질문은 오류 없는WAITING_USER와 의미 있는 안내를 추가로 요구한다.'),('실험 설계','baseline은 완료된 ADR0438/harness의 실제 출력 재사용이다. 신규 flash-medium은 같은8질문을1회 실행했다. 실험 한정 명시 모델 권한과 hash를 결속하고 공통GeminiExperimentClient의 transport를 사용했다. 후보 snapshot은 모델선택 wrapper이며 실제 하네스는 ADR0438의 byte-identical frozen runtime을 주입한다.'),('데이터·모델·재현성','동일 공개 법률 snapshot·용어집·색인·정책DB·source fingerprint를 읽기 전용으로 재사용했다. 실제 내부 데이터 없음. 모델gemini-3.8-flash, thinking medium, temperature0, output4096; fallback없음. Lite 전역 정책은 그대로이며 scoped authorization은 사용자 요청에 한정한다. 최신법·GENOS 검증이 아니다.'),('결과',table+'\n[질문별 전체 입출력](실험/README.md). 기준은 과거 실행이므로 동시 대조 실험이 아니다. 이전 ADR0438의 raw점수와 이번 엄격판정 수치를 직접 혼합하지 않는다.'),('사례별 오류 분석',diagnosis),('비용·지연·회수 규모',f'신규 제품{candidate["calls"]}회, 채점{len(judge)}회. 공개단가 기준 제품 약${cost:.4f}, 채점 약${judgecost:.4f}; 실제 청구 미확인. 과거baseline 호출은 이번 비용에서 제외했다. 제품p50={candidate["latency_p50"]:.2f}초, p95={candidate["latency_p95"]:.2f}초. 파일 초기화·검증 포함 p.run 지연이며 운영 지연으로 외삽하지 않는다. [가격 근거](https://ai.google.dev/gemini-api/docs/pricing).'),('해석','원문읽기·근거채택·실제완료를 구분했다. 비용 감소가 조기 실패에서 왔으면 효율 향상으로 해석하지 않는다. 모델과 추론설정을 동시에 상향한 조합 실험으로 각각의 효과는 분리되지 않는다.'),('한계와 일반화 가능 범위','동일한6개 공개 법률 질문과2개 보호 질문의 in-sample 단회 실행이다. 과거baseline 비동시 비교. 평가자는같은 모델계열 단회로 전문가 calibration과 반복 일치도 미확인. GENOS 내부모델·실제내부데이터·운영반영 미실행.'),('운영 결정·롤백 조건','제품코드·활성 MAIN·전역 모델 기본값 변경 없음. 새 모델은 실험에만 명시 주입했다. 완료 ADR과 기존 실험 결과는 보존한다. 후속 프롬프트·코드 변경이나 재시도는 새 ADR에서 한다.'),('재현 명령','`PYTHONPATH=02_BACKEND .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0440/run_probe.py` (완료실행 덮어쓰기 거부). 모델 호출 전14,474입력을 해시검증한다. `score.py`는 별도 프로세스에서 처음 gold를 읽는다. `adr_structure.py validate --final`, `graph` 결과는 검증로그에 남긴다.')]
 front=(D/'README.md').read_text().split('---',2)[1];(D/'README.md').write_text('---'+front+'---\n\n# 모델 상향 비교\n'+''.join(f'\n## {i}. {t}\n\n{b}\n' for i,(t,b) in enumerate(sections,1)));(D/'RESULT.md').write_text('# Gemini Flash medium 실행 결과\n\n'+table+'\n'+diagnosis+'\n\n[전체기록](실험/README.md) · [설계와 한계](README.md)\n')
 files=[p for p in A.rglob('*') if p.is_file() and p!=A/'manifest.json' and not p.name.endswith('.log')]+list((R/'06_TOOLS/EXPERIMENTS/adr_0440').glob('*.py'))+[D/'RESULT.md']
 cm=R/'02_BACKEND/lawrag/research/candidates/adr_0440/flash-medium/candidate.json';files+=[cm]+[R/f['frozen_path'] for f in read(cm)['revisions'][-1]['files']]
 write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0440','files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen binding, exact provider IO, execution result or offline report'} for p in sorted(set(files))]})
 print(json.dumps({'answer':candidate['answer_pass'],'guard':candidate['guard_pass'],'calls':candidate['calls'],'estimated_total_usd':cost+judgecost},ensure_ascii=False))
if __name__=='__main__':main()
