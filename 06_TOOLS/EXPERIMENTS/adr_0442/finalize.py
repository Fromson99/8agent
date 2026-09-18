"""Render recorded outputs without altering or rerunning the candidate."""
from pathlib import Path
import hashlib,json,statistics
from run_probe import R,D,A,C,ARMS,read,sha,rel
T=R/'06_TOOLS/EXPERIMENTS/adr_0442'
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
def main():
 m=read(D/'실험/manifest.json');metrics=read(A/'metrics.json');cases=read(A/'dataset/product-cases.json');gold={v['id']:v for v in read(A/'grading/gold.json')};results=read(A/'results.json');rows=[]
 for i,c in enumerate(cases,1):
  cid=c['id'];text=f'# 질문 {i:03d} — {cid}\n\n## 1. 실행 메타\n\nADR0442/run-001, baseline/schema, gemini-3.1-flash-lite. 모의 문서·모의 질문; provider payload exact.\n\n## 2. 사용자 질문 원문\n\n'+c['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n'+block(gold[cid])+'\n## 4. 제품 입력을 구성한 원값\n'+block(c)+'\n공통 [모의 corpus](../artifacts/dataset/corpus.json). 실제 모델에 보낸 원문은 아래 호출에 전량 보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n| arm | stage | before | added | discarded | after | gold before | gain | loss | gold after/total |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---|\n'
  for arm in ARMS:
   for s in read(A/'graded'/f'{cid}-{arm}.json')['stages']:
    text+=f"| {arm} | {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_before']} | {s['gold_added']} | {s['gold_discarded']} | {s['gold_after']}/{s['gold_total']} |\n"
  text+='\n정확한 좌표·탈락 사유·gold loss는 [전용 원장](../artifacts/retrieval-ledger.json). 기사/조문 기준이며 catalogue 메타데이터는 별도 도구 receipt로 검증한다.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n'
  for arm in ARMS:
   text+='\n### '+arm+'\n'
   for folder in sorted((A/'calls'/cid/arm).glob('call-*')):
    for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
     if (folder/name).exists():text+='\n#### '+folder.name+'/'+name+'\n'+block(read(folder/name))
  text+='\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\nnavigation 안에서 도구 선택·판단·복구를 수행한다. 별도 router 모델 없음. 모든 호출은 위에 포함.\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(results['cases'][cid][arm])
  text+='\n## 7. 채점 호출과 반복 판정\n\n제품 출력 봉인 후 단회 익명 Gemini 판정. 다수결·전문가 calibration 없음. 판정은 제품 출력을 변경하지 않음.\n'
  for folder in sorted((A/'judges'/cid).glob('call-*')):
   for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
    if (folder/name).exists():text+='\n### '+name+'\n'+block(read(folder/name))
  text+='\n## 8. 사례 최종 판정\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(metrics['by_arm'][arm]['by_case'][cid])
  (D/'실험'/f'질문-{i:03d}-{cid}.md').write_text(text)
  rows.append(f'| [{cid}](질문-{i:03d}-{cid}.md) | '+' | '.join(('통과' if metrics['by_arm'][a]['by_case'][cid]['pass'] else '미통과')+f" ({metrics['by_arm'][a]['by_case'][cid]['calls']}회)" for a in ARMS)+' |')
 (D/'실험/README.md').write_text('# 모의 질문 8개 비교\n\n동일 모델·문서·질문·예산, 단회 실행. 성공은 의미 판정과 원문·도구·완료 검사를 모두 통과한 경우.\n\n| 질문 | 기존 탐색 | 스키마 후보 |\n|---|---|---|\n'+'\n'.join(rows)+'\n')
 counts={k:{a:metrics['by_arm'][a][k] for a in ARMS} for k in ['presented_total','presented_mean','presented_p50','presented_p95','selectivity']}
 m['retrieval_accounting'].update(corpus_total=metrics['corpus_total'],before_filter=metrics['corpus_total'],after_filter=statistics.mean(counts['presented_mean'].values()),golden_recall={a:metrics['by_arm'][a]['selected_required_recall'] for a in ARMS},**counts);m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'retrieval-ledger.json');m['runs'][0].update(status='complete',sha256=sha(A/'results.json'))
 usage={k:sum(v['usage'][k] for v in metrics['by_arm'].values()) for k in ['input_tokens','output_tokens','thinking_tokens','total_tokens']}
 m['results'].update(status='complete',by_arm=metrics['by_arm'],comparisons=metrics['comparisons'],judge_disagreements=0,judge_disagreement_note=metrics['judge_disagreement_note'],usage={'product_calls':sum(v['calls'] for v in metrics['by_arm'].values()),'product':usage,'judge_usage':metrics['judge_usage']},latency={a:{'p50':metrics['by_arm'][a]['latency_p50'],'p95':metrics['by_arm'][a]['latency_p95']} for a in ARMS},error_taxonomy=sorted({v['judge']['error_type'] for a in metrics['by_arm'].values() for v in a['by_case'].values() if not v['pass']}))
 write(D/'실험/manifest.json',m)
 table='| 방식 | 엄격 성공 | 의미 판정만 | 거짓 완료 | 필수 원문 읽기 | 호출 | 지연 p50/p95 |\n|---|---:|---:|---:|---:|---:|---:|\n'+''.join(f"| {a} | {metrics['by_arm'][a]['correct']}/8 | {metrics['by_arm'][a]['semantic_correct']}/8 | {metrics['by_arm'][a]['false_completion']}/8 | {metrics['by_arm'][a]['read_required_recall']:.0%} | {metrics['by_arm'][a]['calls']} | {metrics['by_arm'][a]['latency_p50']:.1f}/{metrics['by_arm'][a]['latency_p95']:.1f}초 |\n" for a in ARMS)
 sections=[('결정 요약',f"격리 후보 구현 및 비교 실행 완료. 사전 기준 통과={metrics['success_criteria_pass']}. Proposed, MAIN unchanged. 후보의 다음 단계는 결과에 근거해 별도 ADR에서 결정한다.\n\n"+table),('문제와 변경 전 구조','기존 용어/구조 역매칭은 개념에 잡히지 않는 전체 문서 목록·리터럴/전문검색을 직접 다루지 못하며 READ가 2400자로 나뉜다. 사용자 요청에 따라 ADR0441과 별도 후보를 명시 승인받아 구현했다. 다른 후보의 코드·결과는 사용하지 않았다.'),('가설과 사전 판정 기준','성공≥6/8, 기존만 성공하는 회귀0, 범위 침범·무효 인용0, 후보 요청당12호출/180초 이내. [사전 설계](artifacts/design-before-snapshot.json), [실행전 봉인](artifacts/pre-call-manifest.json). 긴 원문 fixture는 첫 실행 전에2400자를 넘도록 수정했고 원래/새 해시를 [사전 수정 기록](artifacts/prerun-fixture-amendment.json)에 남겼다.'),('실험 설계','baseline은 활성 릴리스의 동결 navigation-loop-v1, 후보는 상속 adapter다. 기존 GRAPH/OPEN_TERM/REFERENCES 유지, CATALOG/GREP/FTS5/구조 READ/REFOCUS 및 맥락 요약을 추가했다. 전체 원문과 전체 이력은 보존하고 현재 필요한 구조만 모델에 보낸다. 법률형 결과는 기존 select→assemble→answer를 그대로 실행해 Answer 계약을 검증했다. 문서 목록은 명시적 v2 모의 envelope에 출력한다. HTTP API와 v2 feedback 배선은 이번 범위 밖이다.'),('데이터·모델·재현성','11개 허용 모의 문서 메타데이터와 비공개 모의 문서1개, 허용 원문6개, 가상 용어2개, 등록 관계1개, 원문 참조1개. 실제 법률·내부 자료는 외부에 보내지 않았다. 신규 모델 정책 Gemini 공통 client, 고정 temperature 및 호출 상한. 후보 manifest/revision/runner/질문/문서/스키마를 해시로 결속했다. [계약 검사](artifacts/contract-tests.txt).'),('결과',table+'\n자동 채점에 질문 기준 혼입이 확인되었다. 기존0/8과 비교 delta는 확정 품질 수치로 사용하지 않는다. 후보 catalogue/structure2건 성공은 trace에서 확인했고 사전6/8 기준은 미달이다. [채점 오류 검토](artifacts/review.md).\n[질문별 답변과 전체 trace](실험/README.md). [비교쌍](artifacts/metrics.json). 엄격 성공은 의미 판정+명시 요청 도구+필수 원문 채택+scope/quote+완료 조건이 모두 맞는 경우다. 목록과 부재 확인은 별도 기준이며 조문 recall에 억지로 포함하지 않는다.'),('사례별 오류 분석','[질문별 판정](실험/README.md)에 rejected actions, 실패 위치, 실제 사용자 답변과 판정 근거를 전량 기록했다. JSON 성공이나 계약 테스트 통과가 의미 품질을 보장하지 않는다. [별도 검토 메모](artifacts/review.md)를 함께 확인한다.'),('비용·지연·회수 규모',f"제품 호출 {m['results']['usage']['product_calls']}회, 입력 {usage['input_tokens']}, 출력 {usage['output_tokens']}, thinking {usage['thinking_tokens']}토큰. 평가 호출은 별도 usage. 청구액 미측정. 지연은 케이스 실행과 모델·기존 하위 단계를 포함하고 준비/동결은 제외. 모델 입력 문자예산은 토큰 정확예산이 아니다. [단계별 원장](artifacts/retrieval-ledger.json)."),('해석','작게 작성한 모의 데이터에서 기능 연결·도구 선택·완료를 관찰한 개발용 probe다. 실제 전체 법률 corpus 검색 품질 또는 운영 비용 개선을 입증하지 않는다. 단회 동일 계열 모델 평가이며 전문가 검증은 아니다.'),('한계와 일반화 가능 범위','생성된 모의 질문8개, 단회, 독립 holdout 아님. semantic/hybrid는 backend 미결속으로 UNAVAILABLE. FTS5 unicode61은 한국어 형태소 분석·임베딩 의미검색이 아니다. 실제 원문 DB 소유 block mapper는 구현 및 모의 DB 계약 검사했으나159개 실제 문서 대규모 실모델 평가는 안 했다. 지속 세션·권한 변경·v2 gateway/feedback·GENOS 미검증. 큰 원자 구조는 BLOCKED로 남긴다. 구조 자식별 읽기 합집합 완료 계산은 후속 범위이며 전체 SUBTREE 읽기로만 current pending을 해소한다.'),('운영 결정·롤백 조건','Proposed. MAIN 기본 경로·활성 포인터·불변 원문은 변경하지 않았다. 후보는 research 경로에서 hash 확인 후 명시 주입하며 운영 registry에서 선택할 수 없다. 이번 in_sample probe로 자동 승격하지 않는다. 실패 결과를 보고 수정하거나 재실행하면 별도 ADR에 남긴다.'),('재현 명령','계약 테스트: `PYTHONPATH=02_BACKEND .venv/bin/python -B -m pytest -q -p no:cacheprovider 06_TOOLS/EXPERIMENTS/adr_0442/test_contracts.py`\n\n실행 runner `06_TOOLS/EXPERIMENTS/adr_0442/run_probe.py`, 평가 `score.py`, 보고 `finalize.py`. 완료 모델 run/채점은 덮어쓰기 거부. 다시 실행하려면 새 ADR. `adr_structure.py validate --final`과 `graph`로 기록 검증.')]
 front=(D/'README.md').read_text().split('---',2)[1];(D/'README.md').write_text('---'+front+'---\n\n# 스키마 도구 탐색 별도 후보 비교\n'+''.join(f'\n## {i}. {title}\n\n{body}\n' for i,(title,body) in enumerate(sections,1)))
 (D/'RESULT.md').write_text('# 모의 샘플 비교 결과\n\n자동 채점에서 질문 기준 혼입이 확인되어 baseline 점수와 delta는 신뢰 가능한 개선 지표가 아니다. [검토](artifacts/review.md).\n\n'+table+'\n사전 기준 통과: '+str(metrics['success_criteria_pass'])+'\n\n[질문별 답변](실험/README.md) · [상세 결정문](README.md)\n')
 files=[p for folder in [A,C,T] for p in folder.rglob('*') if p.is_file() and p!=A/'manifest.json' and '__pycache__' not in p.parts]
 write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0442','files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code/input, exact provider receipt, or isolated post-selection report'} for p in sorted(set(files))]})
 print(table)
if __name__=='__main__':main()
