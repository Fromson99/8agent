"""Report rendering only, after frozen products and offline grading."""
from runtime import *
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def block(x):return '\n```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```\n'
def inventory():
 paths=[p for folder in [A,T,C] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=A/'manifest.json']
 write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0456','files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen synthetic input, immutable product/provider output, offline grading or report'} for p in sorted(paths)]})
def main():
 metrics=read(A/'metrics.json');cases=read(A/'dataset/product-cases.json');gold={x['id']:x for x in read(A/'grading/gold.json')['cases']};results=read(A/'results.json');m=read(D/'실험/manifest.json');rows=[]
 for num,c in enumerate(cases,1):
  cid=c['id'];text=f'# 질문 {num:03d} — {cid}\n\n## 1. 실행 메타\n\nADR0454/run-001, baseline(ADR0451 mapped), routed(ADR0454). Gemini gemini-3.1-flash-lite, synthetic EXAMPLE, 단회. 정확한 실행 시각은 아래 provider 원응답과 개별 receipt/파일 기록에 보존한다. 원문 payload는 exact.\n\n## 2. 사용자 질문 원문\n\n'+c['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n'+block(gold[cid])+'\n## 4. 제품 입력을 구성한 원값\n'+block(c)+'\n\n모의 원문12개/문서10개. 문서명 목록은 조문 근거를 제시한 것으로 세지 않는다. article 좌표 원장은 원문 발견/읽기/채택과 별도 집계다.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n| arm | stage | before | added | discarded | after | gold before | gain | loss | gold after/total |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---|\n'
  for arm in ARMS:
   for s in read(A/'graded'/f'{cid}-{arm}.json')['stages']:text+=f"| {arm} | {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_before']} | {s['gold_added']} | {s['gold_discarded']} | {s['gold_after']}/{s['gold_total']} |\n"
  text+='\n[정확한 조문 좌표·탈락 이유](../artifacts/retrieval-ledger.json). metadata 문서 필터 정확성은 별도 expected/returned document ID 비교로 검사한다.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n'
  for arm in ARMS:
   text+='\n### '+arm+'\n';calls=list(sorted((A/'calls'/cid/arm).glob('call-*')))
   if not calls:text+='\n로컬 메타데이터 경로로 처리하여 모델 호출이 없었다.\n'
   for folder in calls:
    for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
     if (folder/name).exists():text+='\n#### '+folder.name+'/'+name+'\n'+block(read(folder/name))
  text+='\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n별도 숨겨진 모델 없음. 위 structured_navigation 호출에 포함한다. 아래는 전체 제어 상태와 하위 Pipeline Result다.\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(results['cases'][cid][arm])
  text+='\n## 7. 채점 호출과 반복 판정\n'
  if gold[cid]['kind']!='content':text+='\n메타데이터/매핑은 동결 gold의 문서 ID·타입·검토 상태를 오프라인 코드로 비교했다. 채점 모델 호출 없음.\n'
  else:
   text+='\n제품 선택 후 동결 원문·required_points를 준 익명2방식 단회 Gemini 평가다. 반복/전문가 calibration 미실시.\n'
   for folder in sorted((A/'judges'/cid).glob('call-*')):
    for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
     if (folder/name).exists():text+='\n### '+name+'\n'+block(read(folder/name))
  text+='\n## 8. 사례 최종 판정\n'
  for arm in ARMS:text+='\n### '+arm+'\n'+block(metrics['by_arm'][arm]['by_case'][cid])
  (D/'실험'/f'질문-{num:03d}-{cid}.md').write_text(text)
  rows.append('| ['+cid+f'](질문-{num:03d}-{cid}.md) | '+c['question']+' | '+' | '.join(('통과' if metrics['by_arm'][a]['by_case'][cid]['pass'] else '실패')+f" ({metrics['by_arm'][a]['by_case'][cid]['calls']}회)" for a in ARMS)+' |')
 table='| 사례 | 질문 | 기존 mapped | 수정 routed |\n|---|---|---|---|\n'+'\n'.join(rows)+'\n';(D/'실험/README.md').write_text('# 모의18질문 × 2방식\n\n전체 호출·답변·판정 기록. 문서/매핑16개와 내용2개를 분리한다.\n\n'+table+'\n[사전 설계·계보](manifest.json).\n')
 for k in ['presented_total','presented_mean','presented_p50','presented_p95']:m['retrieval_accounting'][k]={a:metrics['by_arm'][a][k] for a in ARMS}
 m['retrieval_accounting'].update(corpus_total=12,before_filter={a:sum(len((r[a].get('output') or {}).get('retrieval',{}).get('term_agent',{}).get('known_source_ids',[])) for r in results['cases'].values()) for a in ARMS},after_filter={a:metrics['by_arm'][a]['presented_total'] for a in ARMS},selectivity={a:metrics['by_arm'][a]['presented_mean']/12 for a in ARMS},golden_recall={a:sum(v['required_selected'] for v in metrics['by_arm'][a]['by_case'].values())/8 for a in ARMS})
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'retrieval-ledger.json');m['runs'][0].update(status='complete',sha256=sha(A/'results.json'))
 total=sum(v['calls'] for v in metrics['by_arm'].values());usage={k:sum(v['usage'][k] for v in metrics['by_arm'].values()) for k in ['input_tokens','output_tokens','thinking_tokens','total_tokens']}
 m['results'].update(status='complete',by_arm=metrics['by_arm'],comparisons=metrics['comparisons'],judge_disagreements=None,judge_disagreement_note=metrics['judge_disagreement_note'],usage={'product_calls':total,'product_tokens':usage,'judge_calls':2,'judge_usage':metrics['judge_usage']},latency={a:{'p50':metrics['by_arm'][a]['latency_p50'],'p95':metrics['by_arm'][a]['latency_p95']} for a in ARMS},error_taxonomy=[{'arm':a,'counts':metrics['by_arm'][a]['errors']} for a in ARMS]);write(D/'실험/manifest.json',m)
 summary=' / '.join(f"{a}: 전체 {v['pass']}/18, 목록·매핑 {v['metadata_pass']}/16, 내용 {v['content_pass']}/2" for a,v in metrics['by_arm'].items());comparison=metrics['comparisons'][0]
 diagnosis=[]
 for c in cases:
  cid=c['id']
  for a in ARMS:
   v=metrics['by_arm'][a]['by_case'][cid]
   if not v['pass']:diagnosis.append(f"- {cid}/{a}: 반환문서={v['returned_documents']}, 기대={v['expected_documents']}, 종류={v['navigation_kind']}, 실패={v['failure']}, 골든채택={v['required_selected']}/{v['required_total']}, 도구거절={v['rejected_actions']}. 의미채점={v['judge']}\n")
 (A/'diagnosis.md').write_text('# 실패 기록\n\n'+''.join(diagnosis)+'\n실패 뒤 제품·프롬프트·질문 수정이나 재실행을 하지 않았다. 원인 해석은 원 trace와 함께 읽는다.\n')
 sections=[('결정 요약',summary+f". 사전 기준 충족={metrics['success_criteria_pass']}. Proposed 유지, MAIN 미반영. 모의 단회 개발 실험이며 GENOS·실제 자료 품질 인증이 아니다."),('문제와 변경 전 구조','ADR0451은 첫 LLM 해석과 표현 매핑 등록·검토 계약을 모의 통신으로만 검사했다. 실제 Gemini가 내문/외규/금투협의 범위와 도구를 올바르게 선택하는지, 여러 용어의 후보를 읽고 답하는지는 미확인이었다.'),('가설과 사전 판정 기준','새 mapped14/16 이상, 기존만 통과하는 회귀0, 미지 표현 확인 요청, 권한 범위 이탈/잘못된 인용0. 14메타데이터·매핑과2내용을 나누어 평가한다. [설계](artifacts/design-before-snapshot.json), [실행 직전 명세](artifacts/pre-call-manifest.json).'),('실험 설계','정확한 부모 ADR0451/mapped를 재검증한다. baseline은 그 부모가 상속한 ADR0450 TypedAgent/Conversation으로 되돌리는 ablation이며 mapped는 ADR0451 그대로다. 제품 수정 없이 같은 Gemini와 모의 원문, 예산, 질문을 사용한다. 실행 순서는 질문마다 교대한다. 첫 모델 호출 전 scaffold의 code_isolation/run purpose/계보 선언을 검증기 계약에 맞게 정정했고 초기 기록과 정정 이유를 보존했다. 기준·질문·모델·제품코드는 바꾸지 않았다.'),('데이터·모델·재현성','모의 문서10개·조문12개만 Gemini로 전송했다. 실제 내부/공개 법률 데이터는 전송하지 않았다. 기존 법률 반출 허용 범위를 확대하지 않고 합성 자료로 제한했다. gemini-3.1-flash-lite, minimal thinking, temperature0, maxOutputTokens4096, 공통 GeminiExperimentClient. 자동재시도/provider fallback 없음. [96개 입력 해시](artifacts/input-lock.json).'),('결과',table.replace('](질문-','](실험/질문-')+'\n비교쌍: '+block(comparison)),('사례별 오류 분석','[전체 실패 기록](artifacts/diagnosis.md). 기능 성공과 내용 의미 성공을 분리했다. 초기 scope 해석의 안전 차단을 정상 답변 성공으로 세지 않았다. 모델이 생성한 승인 후보는 현재 질문에서 사용될 수 있어도 재사용은 사용자 검토 이후이며, mapping 사례는 첫 제안을 선택하는 사전 고정 사용자 동작과 새 대화의 후속 질문을 포함한다.'),('비용·지연·회수 규모',f"제품{total}회, 입력{usage['input_tokens']}·출력{usage['output_tokens']}·thinking{usage['thinking_tokens']}토큰. 오프라인 내용 judge2회 별도. 실제 청구액은 미측정. "+' / '.join(f"{a}: p50 {v['latency_p50']:.2f}s / p95 {v['latency_p95']:.2f}s" for a,v in metrics['by_arm'].items())+'. 모델0회로 끝나는 기존 목록 경로와 새 모델 해석 비용의 차이를 포함한다. 원문 골든 회수와 metadata 문서 목록 정확도는 다른 지표다. [조문 단계원장](artifacts/retrieval-ledger.json).'),('해석','모든 약어를 사람이 미리 적는 접근 대신 실제 타입 후보를 LLM이 해석하는 경로를 실호출했다. 해석과 이후 원문 읽기/선택/최종 답변은 별개로 집계한다. 목록 필터를 잘 골라도 복수 조문 답변이 자동으로 정확해지는 것은 아니다. 골든은 제품 선택 완료 뒤 별도 오프라인 프로세스에서만 결합했다.'),('한계와 일반화 가능 범위','이미 논의한 표현을 포함한 합성·단회 in-sample probe다. 알려지지 않은 실제 약어의 일반화율·운영 GENOS 모델 성능·망분리 내부 자료 품질은 미확인이다. 내용 채점2개는 동일 계열 모델의 단회 판단이며 전문가 보정 없음. latency는 이 로컬 실험 환경의 값이다. 사용자별/세대별 mapping이며 실제 조직 공용 사전 승인은 다루지 않았다.'),('운영 결정·롤백 조건','활성 MAIN·원문 store·GENOS 배포는 그대로다. 결과 기반 수정은 새 ADR로 분기한다. 범위 오류/매핑 오류/근거 누락을 해결하고 별도 평가를 거치기 전 자동 승격하지 않는다. 기존 typed 객체로 원복 가능하다.'),('재현 명령','`PYTHONPATH=02_BACKEND .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0456/run_probe.py`와 score.py는 완료 실행·재채점 덮어쓰기를 거부한다. 새 실행은 새 ADR을 선점한다. [최종 검증](VALIDATION.md), [전체 질문](실험/README.md).')]
 front=(D/'README.md').read_text().split('---',2)[1];(D/'README.md').write_text('---'+front+'---\n\n# Gemini 질문 해석·표현 매핑 실험\n'+''.join(f'\n## {i}. {title}\n\n{body}\n' for i,(title,body) in enumerate(sections,1)))
 (D/'RESULT.md').write_text('# Gemini 실호출 결과\n\n'+summary+'\n\n'+table.replace('](질문-','](실험/질문-')+'\n[실패 원인](artifacts/diagnosis.md) · [전체 호출 기록](실험/README.md) · [조건·한계](README.md)\n')
 index=R/'04_EXPERIMENTS/ADR/README.md';s=index.read_text();line='- [ADR-0456 Gemini 질문 해석·표현 매핑 실험](ADR-0456-persistent-navigation-work-state/RESULT.md) — '+summary+'; 모의18질문·MAIN미반영.\n\n'
 if 'ADR-0456 Gemini 질문' not in s:index.write_text(s.replace('# ADR workspace\n\n','# ADR workspace\n\n'+line,1))
 inventory();print(summary)
if __name__=='__main__':main()
