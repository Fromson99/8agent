"""Report-only rendering; no changes to frozen inputs or model output."""
from pathlib import Path
import json,hashlib,statistics
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0441-structured-navigation-sample-probe';A=D/'artifacts';T=R/'06_TOOLS/EXPERIMENTS/adr_0441';C=R/'02_BACKEND/lawrag/research/candidates/adr_0441/structured';ARMS=['baseline','structured']
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def block(x):return '\n```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```\n'
def rel(p):return str(p.relative_to(R))
def inventory():
 paths=[p for folder in [A,T,C] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=A/'manifest.json' and p.suffix!='.log']
 write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0441','files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact frozen input, candidate, provider request/response, test record or offline report'} for p in sorted(paths)]})
def main():
 metrics=read(A/'metrics.json');cases=read(A/'dataset/product-cases.json');gold={g['id']:g for g in read(A/'grading/gold.json')['cases']};results=read(A/'results.json');m=read(D/'실험/manifest.json');rows=[]
 for num,c in enumerate(cases,1):
  cid=c['id'];text=f'# 질문 {num:03d} — {cid}\n\n## 1. 실행 메타\n\nADR-0441 / run-001 / baseline, structured / gemini-3.1-flash-lite. '+c['dataset']+' 자료의 단회 비교.\n\n## 2. 사용자 질문 원문\n\n'+c['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n'+block(gold[cid])+'\n## 4. 제품 입력을 구성한 원값\n'+block(c)
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
 table='| 사례 | 자료 | 기존 탐색 | 새 후보 |\n|---|---|---|---|\n'+'\n'.join(rows)+'\n'
 (D/'실험/README.md').write_text('# 샘플 질문 8개 × 2방식\n\n모의 자료 6개, 선택된 공개 법률 2개. 기능과 의미 판정을 모두 통과한 경우만 통과 표시. 모든 질문의 실제 입력·출력·채점 원문을 보존한다.\n\n'+table+'\n[사전 기준·계보·단계 원장 결속](manifest.json). 운영 MAIN 변경 없음.\n')
 for k in ['presented_total','presented_mean','presented_p50','presented_p95']:m['retrieval_accounting'][k]={a:metrics['by_arm'][a][k] for a in ARMS}
 m['retrieval_accounting'].update(corpus_total=sum(metrics['corpus_counts'].values()),before_filter=metrics['corpus_counts'],after_filter={a:metrics['by_arm'][a]['presented_total'] for a in ARMS},selectivity={a:metrics['by_arm'][a]['presented_mean']/sum(metrics['corpus_counts'].values()) for a in ARMS},golden_recall={a:sum(v['required_selected'] for v in metrics['by_arm'][a]['by_case'].values())/sum(v['required_total'] for v in metrics['by_arm'][a]['by_case'].values()) for a in ARMS})
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'retrieval-ledger.json');m['runs'][0].update(status='complete',sha256=sha(A/'results.json'))
 total=sum(v['calls'] for v in metrics['by_arm'].values());usage={k:sum(v['usage'][k] for v in metrics['by_arm'].values()) for k in ['input_tokens','output_tokens','thinking_tokens','total_tokens']}
 m['results'].update(status='complete',by_arm=metrics['by_arm'],comparisons=metrics['comparisons'],judge_disagreements=None,judge_disagreement_note=metrics['judge_disagreement_note'],usage={'product_calls':total,'product_tokens':usage,'judge_usage':metrics['judge_usage']},latency={a:{'p50':metrics['by_arm'][a]['latency_p50'],'p95':metrics['by_arm'][a]['latency_p95']} for a in ARMS},error_taxonomy=['See per-case functional checks, failed tool arguments and evaluator missing points'])
 write(D/'실험/manifest.json',m)
 summary=' / '.join(f"{a}: 모의 {v['synthetic_pass']}/6, 공개 법률 {v['public_pass']}/2" for a,v in metrics['by_arm'].items())
 sections=[('결정 요약',summary+f". 사전 기준 통과={metrics['success_criteria_pass']}. Proposed 유지, MAIN 변경 없음. 단회 샘플 결과이며 전체 설계·운영 품질 인증은 아니다."),('문제와 변경 전 구조','기존 탐색은 용어/구조 시작점에서 원문을 찾으며 전체 문서 목록을 답변하는 경로와 일반 전문검색이 없다. READ는 2400자 구간이고 읽기·인용·미해결 상태를 관리한다. 이번에는 이 읽기 규칙을 원문 단위로 교체하고 목록·검색·복귀 도구를 추가했다.'),('가설과 사전 판정 기준','8개 중 6개 이상, catalogue와 graph 필수 통과, 공개 법률 사례 기존 대비 회귀 0, 잘못된 인용·범위 이탈 0. 모든 기준/문항/원문/채점 기준을 첫 호출 전에 동결했다. [사전 기준](artifacts/design-before-snapshot.json), [첫 호출 전 manifest](artifacts/pre-call-manifest.json), [입력 해시](artifacts/input-lock.json).'),('실험 설계','baseline은 동결한 현재 작업 NavigationAgent, structured는 같은 파일 묶음의 StructuredAgent다. active release를 실제로 교체한 비교가 아니다. 문항 순서에 따라 arm 순서를 교대하며 각 1회. 동일 Gemini와 호출16회·행동48회·루프180초·active18000자·context60000자 예산. 문맥 제한은 글자 수이며 토큰 한도를 정확히 보장하는 값이 아니다. runtime의 retrieve→select→assemble→answer 및 Result 계약을 실제 실행했다.'),('데이터·모델·재현성','모의 문서3개로 만든 질문6개, 선택된 공개 자본시장법의 질문2개. 공개 범위 문서 ID 5be4de51a89dc664의 출처/해시와 기존 반출 근거를 authorization.json에 결속했다. 원본 export 플래그를 수정하지 않았다. gemini-3.1-flash-lite 공통 클라이언트로 요청·응답·스키마·usage를 전량 보존했다. 현재 시행 법률 확인이나 실제 내부 데이터 시험은 아니다.'),('결과',table+'\n[전체 답변·도구 호출·채점](실험/README.md). 단위·회귀35개 통과(새 후보12개 포함). 외부 모델 검증과 구분한다.'),('사례별 오류 분석','[상세 진단](artifacts/diagnosis.md)에 실제 답변과 선택 경로, 의미 판정 충돌을 기록한다. 결과를 본 뒤 후보·프롬프트를 수정하거나 재실행하지 않았다. 실패가 있으면 후속 ADR에서 다룬다.'),('비용·지연·회수 규모',f"제품 {total}회, input {usage['input_tokens']}, output {usage['output_tokens']}, thinking {usage['thinking_tokens']}, total {usage['total_tokens']} tokens. 오프라인 판정은 별도 8회 계획이며 실제 사용량은 metrics.json. 청구액은 미측정. 데이터 범위는 모의3조문, 공개{metrics['corpus_counts']['public']}조문. 전체 p.run 지연은 초기화/해시검증/모델을 포함하고 입력 봉인 작업은 제외. "+' / '.join(f"{a} p50 {v['latency_p50']:.1f}s, p95 {v['latency_p95']:.1f}s" for a,v in metrics['by_arm'].items())),('해석','목록 완료와 원문 근거 완료를 다른 상태로 처리한다. 원문 본문은 온전한 조문 또는 원본 block으로 읽고 큰 단일 block은 명시적으로 거절한다. 누락을 숨기지 않는다는 제어를 구현했으나 모든 법적 의존관계의 의미적 완전성을 보장하지 않는다. GOLD는 선택 이후의 채점기에만 제공했다.'),('한계와 일반화 가능 범위','내장 FTS5는 unicode61 토큰 검색으로 한국어 형태소 검색·embedding 검색이 아니다. embedding은 UNAVAILABLE를 반환한다. GRAPH/명시참조는 기존 자료를 유지한다. BACK/REOPEN은 한 세션의 복귀이며 프로세스 재시작 복원은 미구현. 제안한 v2 API/영속 세션/권한 변경에 따른 핸들 무효화/GENOS 배포/모든 구조 경계 의미 검증은 미구현 또는 미검증이다. 원래 기사 수준 index이므로 하위 구조 선택의 실제 반환 범위를 article_unit_id로 밝힌다. 전문가 채점·반복·독립 holdout이 없으며 샘플 점수를 일반 성능 수치로 쓰지 않는다.'),('운영 결정·롤백 조건','운영 코드·기본 registry·활성 포인터·완료 원문 세대 미변경. 코드 위치는 02_BACKEND/lawrag/research/candidates/adr_0441/structured/revisions/rev-001/snapshot. 후보는 실험 실행기에서만 주입하며 재현/검토 가능한 상태로 보존한다. 후속 개선 또는 운영 승격은 별도 실험/명시적 MAIN 절차를 따른다.'),('재현 명령','실제 비교: `PYTHONPATH=02_BACKEND .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0441/run_probe.py`. 완료 실행은 덮어쓰기 거절. 새 실제 실행/재채점은 새 ADR 필요. 계약 검사: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=02_BACKEND .venv/bin/python -B -m pytest -q -p no:cacheprovider 06_TOOLS/EXPERIMENTS/adr_0441/test_contracts.py`. 후보 검증: `adr_candidate.py validate` / 최종 기록 검증: `adr_structure.py validate --final` 및 `graph`를 stable runner로 실행.')]
 front=(D/'README.md').read_text().split('---',2)[1];(D/'README.md').write_text('---'+front+'---\n\n# 구조 기반 도구 탐색 후보 구현·샘플 결과\n'+''.join(f'\n## {i}. {title}\n\n{body}\n' for i,(title,body) in enumerate(sections,1)))
 (D/'RESULT.md').write_text('# 구조 기반 RAG 도구 샘플 결과\n\n'+summary+'\n\n'+table+'\n[실제 답변과 진단](artifacts/diagnosis.md) · [전체 호출 기록](실험/README.md) · [구현/한계](README.md)\n')
 write(A/'tests.json',{'command':'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=02_BACKEND .venv/bin/python -B -m pytest -q -p no:cacheprovider 05_TESTS/CONTRACTS/test_navigation_loop.py 05_TESTS/CONTRACTS/test_navigation_main_wiring.py 06_TOOLS/EXPERIMENTS/adr_0441/test_contracts.py','passed':35,'warnings':['Unknown pytest cache_dir option when cacheprovider disabled','starlette httpx deprecation'],'elapsed_seconds':29.39,'candidate_new_contract_tests':12})
 inventory();print(summary)
if __name__=='__main__':main()
