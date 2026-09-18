"""Report-only rendering; no changes to frozen inputs or model output."""
from pathlib import Path
import json,hashlib,statistics
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0447-template-bound-tool-handles';A=D/'artifacts';T=R/'06_TOOLS/EXPERIMENTS/adr_0447';C=R/'02_BACKEND/lawrag/research/candidates/adr_0447';ARMS=['baseline','bound']
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def block(x):return '\n```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```\n'
def rel(p):return str(p.relative_to(R))
def inventory():
 paths=[p for folder in [A,T,C] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=A/'manifest.json' and p.suffix!='.log']
 write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0447','files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact frozen input, candidate, provider request/response, test record or offline report'} for p in sorted(paths)]})
def main():
 metrics=read(A/'metrics.json');cases=read(A/'dataset/product-cases.json');gold={g['id']:g for g in read(A/'grading/gold.json')['cases']};results=read(A/'results.json');m=read(D/'실험/manifest.json');rows=[]
 for num,c in enumerate(cases,1):
  cid=c['id'];text=f'# 질문 {num:03d} — {cid}\n\n## 1. 실행 메타\n\nADR-0447 / run-001 / baseline, bound / gemini-3.1-flash-lite. '+c['dataset']+' 자료의 단회 비교.\n\n## 2. 사용자 질문 원문\n\n'+c['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n'+block(gold[cid])+'\n## 4. 제품 입력을 구성한 원값\n'+block(c)
  text+='\n### 회수·탈락 단계 원장 — run·arm별\n\n| arm | stage | before | added | discarded | after | gold before | gain | loss | gold after/total |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---|\n'
  for arm in ARMS:
   for s in read(A/'graded'/f'{cid}-{arm}.json')['stages']:
    text+=f"| {arm} | {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_before']} | {s['gold_added']} | {s['gold_discarded']} | {s['gold_after']}/{s['gold_total']} |\n"
  text+='\n[원문 좌표 및 탈락 이유 전체](../artifacts/retrieval-ledger.json). read는 일부라도 모델에 전달된 조문 수이며 전체 조문 완독률이 아니다.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n'
  for arm in ARMS:
   text+='\n### '+arm+'\n'
   for folder in sorted((A/'calls'/cid/arm).glob('call-*')):
    for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
     if (folder/name).exists():text+='\n#### '+folder.name+'/'+name+'\n'+block(read(folder/name))
  text+='\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n별도 숨겨진 모델 호출 없음. 위 navigation 또는 structured_navigation 호출에 도구 선택·판단·종료가 포함된다. 아래는 전체 실행 상태와 제어부 검증 결과다.\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(results['cases'][cid][arm])
  text+='\n## 7. 채점 호출과 반복 판정\n\n모든 제품 출력을 봉인한 뒤 단회 익명 평가. 전문가 보정과 반복 불일치율은 미측정. 기능 체크와 의미 체크는 별도 표시한다.\n'
  for folder in sorted((A/'judges'/cid).glob('call-*')):
   for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
    if (folder/name).exists():text+='\n### '+name+'\n'+block(read(folder/name))
  text+='\n## 8. 사례 최종 판정\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(metrics['by_arm'][arm]['by_case'][cid])
  (D/'실험'/f'질문-{num:03d}-{cid}.md').write_text(text)
  cells=[]
  for arm in ARMS:
   v=metrics['by_arm'][arm]['by_case'][cid];cells.append(('통과' if v['pass'] else '미통과')+f" ({v['calls']}회)")
  rows.append(f'| [{cid}](질문-{num:03d}-{cid}.md) | '+c['dataset']+' | '+' | '.join(cells)+' |')
 table='| 사례 | 자료 | 기존 한국어 도구 | 구조화 결속 |\n|---|---|---|---|\n'+'\n'.join(rows)+'\n'
 (D/'실험/README.md').write_text('# 합성 질문 12개 × 2방식\n\n기존 6개와 새 한국어 사례 6개, 모두 모의 자료. 두 방식 모두 같은 동결 입력으로 새 실행. 실제 법률·내부 자료 전송 없음.\n\n'+table+'\n[사전 기준·계보·단계 원장 결속](manifest.json). MAIN 변경 없음.\n')
 for k in ['presented_total','presented_mean','presented_p50','presented_p95']:m['retrieval_accounting'][k]={a:metrics['by_arm'][a][k] for a in ARMS}
 m['retrieval_accounting'].update(corpus_total=sum(metrics['corpus_counts'].values()),before_filter=metrics['corpus_counts'],after_filter={a:metrics['by_arm'][a]['presented_total'] for a in ARMS},selectivity={a:metrics['by_arm'][a]['presented_mean']/sum(metrics['corpus_counts'].values()) for a in ARMS},golden_recall={a:sum(v['required_selected'] for v in metrics['by_arm'][a]['by_case'].values())/sum(v['required_total'] for v in metrics['by_arm'][a]['by_case'].values()) for a in ARMS})
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'retrieval-ledger.json');m['runs'][0].update(status='complete',sha256=sha(A/'results.json'))
 total=sum(v['calls'] for v in metrics['by_arm'].values());usage={k:sum(v['usage'][k] for v in metrics['by_arm'].values()) for k in ['input_tokens','output_tokens','thinking_tokens','total_tokens']}
 m['results'].update(status='complete',by_arm=metrics['by_arm'],comparisons=metrics['comparisons'],judge_disagreements=None,judge_disagreement_note=metrics['judge_disagreement_note'],usage={'product_calls':total,'product_tokens':usage,'judge_usage':metrics['judge_usage']},latency={a:{'p50':metrics['by_arm'][a]['latency_p50'],'p95':metrics['by_arm'][a]['latency_p95']} for a in ARMS},error_taxonomy=['See per-case functional checks, failed tool arguments and evaluator missing points'])
 write(D/'실험/manifest.json',m)
 summary=' / '.join(f"{a}: {v['pass']}/12" for a,v in metrics['by_arm'].items())
 sections=[
 ('결정 요약',summary+f". 사전 기준 통과={metrics['success_criteria_pass']}. Proposed, MAIN unchanged. 합성 단회 개발용 비교이며 운영 품질 인증이 아니다."),
 ('문제와 변경 전 구조','사용자 지시: 조문은 기존 구조화 틀의 값으로 판별한다. ADR0446은 heading 조문 재분석과 부칙 문자열 구분에 의존했고, 모델은 구조/원문 ID를 혼동하거나 잘못 제한한 LIST에서 복구하지 못했다. ReverseMatcher가 일부 구조 필드만 전달하는 문제를 연구 어댑터로 보완했다.'),
 ('가설과 사전 판정 기준','bound11/12 이상, recovery 필수통과, 기준만 통과하는 회귀0, 인용·범위위반0, 구조 계약통과. [첫 호출 전 기준](artifacts/design-before-snapshot.json). 사후 기준 변경 없음.'),
 ('실험 설계','직접 부모 ADR0446/legal frozen rev-001 대 새 bound의2arm. 동일12질문, 신규 구조화 세대, arm과 익명 평가 순서 교대. Gemini/16호출·48행동·180초·18000자 읽기·60000자 문맥 한도. select/assemble/answer/Result 하위 계약을 실행한다. [동결 결속](artifacts/pre-call-manifest.json).'),
 ('데이터·모델·재현성','모의9원문을 기존 recipe_regions.build + recipe_template + viewer 구조화 경로로 처리하고 source_unit에 적재했다. 모든 좌표는 질문 실행 전에 저장했다. 비교 두 방식 모두 같은 새 세대를 사용한다. GeminiExperimentClient/gemini-3.1-flash-lite, 외부 모델 입력은 합성자료만. 별도 실제 로컬 세대 source_unit 어댑터 검사는 읽기 전용·모델0회다. [입력 해시](artifacts/input-lock.json) · [구조 생성 영수증](artifacts/dataset/structure-build-receipts.json) · [실제 저장 계약](artifacts/stored-contract.json).'),
 ('결과',table.replace('](질문-','](실험/질문-')+'\n[전체 답변·도구 호출·판정](실험/README.md). 기능 판정은 실행 기록과 원문에서 코드로, 의미 판정은 사례별 원문을 준 단회 모델로 분리했다.'),
 ('사례별 오류 분석','[진단](artifacts/diagnosis.md). 실패·회귀·모델 선택 오류는 보존한다. 결과 확인 후 후보나 질문을 수정하거나 재실행하지 않았다.'),
 ('비용·지연·회수 규모',f"신규 제품 {total}호출, 입력 {usage['input_tokens']}·출력 {usage['output_tokens']}·총 {usage['total_tokens']}토큰. 채점은 별도12회, usage 기록 참조. 실제 청구액 미측정. 모의9원문의 발견/읽기/채택 단계별 좌표·탈락·gold 회수는 [원장](artifacts/retrieval-ledger.json). 읽기 count는 일부 전달도 포함하며 완독률이 아니다. "+' / '.join(f"{a}: p50 {v['latency_p50']:.1f}s / p95 {v['latency_p95']:.1f}s" for a,v in metrics['by_arm'].items())),
 ('해석','FIND_ARTICLE은 저장 legal_coordinate를 역직렬화하고 coordinate_scope/key·family·ordinal·parent로 후보를 유지한다. 구세대는 저장 surface를 ingestion 공통 문법으로 읽되 없는 scope/key를 본문에서 만들어내지 않는다. 문서·구조 ID로 직접 READ할 수 없으며 서버가 제시한 RH 핸들만 실제 source_id·내용해시·세대에 결속한다. OPEN_TERM→LIST→READ와 0건 LIST의 선택 문서 필터 완화는 실행 가능한 전환으로 제한한다. 원문 인용은 기존 quote_ref 검증을 유지한다.'),
 ('한계와 일반화 가능 범위','알려진 합성12질문의 단회 개발 비교이며 독립 holdout·실제 법률 품질 인증이 아니다. 같은 계열 모델의 단회 judge로 전문가 보정·반복 불일치율 미측정. 저장 좌표가 없는 구세대 노드는 미확인으로 보존한다. 항·호 좌표가 특정되어도 원문 READ 단위는 해당 조문 전체이며 항·호만 잘라 인용하지 않는다. 구조화 오류 자체를 고치는 기능은 아니다. 실제 GENOS 배포·내부 자료 품질·영속 핸들 재개 미검증.'),
 ('운영 결정·롤백 조건','운영 코드·registry·활성 포인터·완료 세대 불변. 새 코드는 adr_0447/bound frozen rev-001이며 runner가 부모0445 전체 런타임과0446/legal 및 공통좌표 모듈을 해시 결속해 주입한다. MAIN 자동 선택 없음. 비교 기준은 완료된0446/legal로 되돌릴 수 있다. 후속 결과 기반 수정은 새 ADR이 필요하다.'),
 ('재현 명령','`PYTHONPATH=02_BACKEND .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0447/run_probe.py`와 `score.py`는 완료 실행 덮어쓰기를 거부한다. 계약: `.venv/bin/python -m pytest -q 06_TOOLS/EXPERIMENTS/adr_0447/test_contracts.py`. 후보 validate, ADR validate --final, graph는 stable runner 사용.')]
 front=(D/'README.md').read_text().split('---',2)[1];(D/'README.md').write_text('---'+front+'---\n\n# 구조화 좌표와 원문 읽기 핸들 결속\n'+''.join(f'\n## {i}. {title}\n\n{body}\n' for i,(title,body) in enumerate(sections,1)))
 (D/'RESULT.md').write_text('# 한국어 법률 도구 비교 결과\n\n'+summary+'\n\n'+table.replace('](질문-','](실험/질문-')+'\n[실제 답변과 진단](artifacts/diagnosis.md) · [전체 호출 기록](실험/README.md) · [구현/한계](README.md)\n')
 inventory();print(summary)
if __name__=='__main__':main()
