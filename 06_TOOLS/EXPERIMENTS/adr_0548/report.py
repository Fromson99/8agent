"""Summarize completed measurements without making additional model calls."""
import hashlib, json, math, statistics
from pathlib import Path
from datetime import datetime, timezone
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0548-gemma-recorded-compose-compaction'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(v):return json.dumps(v,ensure_ascii=False,indent=2)
def write(p,v):p.write_text(dump(v)+'\n')
def median(v):return statistics.median(v) if v else None
def p95(v):return sorted(v)[math.ceil(len(v)*.95)-1] if v else None
def reduction(b,c):return 1-c/b if b else None
def summarize(rows):
 return {'runs':len(rows),'physical_calls':sum(x['physical_calls'] for x in rows),'input_tokens':sum(x.get('input_tokens',0) for x in rows),'output_tokens':sum(x.get('output_tokens',0) for x in rows),'cost_usd':sum(x.get('cost_usd',0) for x in rows),'p50_seconds':median([x['total_seconds'] for x in rows]),'p95_seconds':p95([x['total_seconds'] for x in rows]),'schema_repairs':sum(max(0,x['physical_calls']-1) for x in rows),'invalid_outputs':sum(x.get('schema_repairs',0) for x in rows),'terminal_failures':sum(not x.get('valid_output',False) for x in rows),'first_response_p50_seconds':median([x['provider_usage'][0]['seconds'] for x in rows if x.get('provider_usage')]),'repair_response_p50_seconds':median([x['provider_usage'][1]['seconds'] for x in rows if len(x.get('provider_usage',[]))>1]),'valid_outputs':sum(x.get('valid_output',x.get('answer_present',False)) for x in rows)}
def main():
 result=read(A/'artifacts/run-001/result.json');rows=result['rows'];design=read(A/'artifacts/frozen-design.json')
 summary={'experiment_id':design['experiment_id'],'groups':{},'criteria':design['success_criteria'],'semantic_quality':'unmeasured','main_wiring_unchanged':True}
 for mode,phase in [('e2e',None),('fixed','compose'),('fixed','review')]:
  group={arm:summarize([x for x in rows if x['mode']==mode and x['arm']==arm and (phase is None or x.get('phase')==phase)]) for arm in ['baseline','compact']}
  b,c=group['baseline'],group['compact'];group['reductions']={key:reduction(b[key],c[key]) for key in ['input_tokens','output_tokens','p50_seconds','cost_usd']}
  # First physical attempt makes the input comparison independent of repair count.
  pairs=[]
  if mode=='fixed':
   lookup={(x['case_id'],x['repeat'],x['arm']):x for x in rows if x['mode']=='fixed' and x['phase']==phase}
   for cid,repeat,arm in lookup:
    if arm!='baseline' or (cid,repeat,'compact') not in lookup:continue
    b1,c1=lookup[(cid,repeat,'baseline')],lookup[(cid,repeat,'compact')]
    pairs.append({'case_id':cid,'repeat':repeat,'baseline_first_input_tokens':b1['provider_usage'][0]['input_tokens'] if b1['provider_usage'] else None,'compact_first_input_tokens':c1['provider_usage'][0]['input_tokens'] if c1['provider_usage'] else None,'baseline_seconds':b1['total_seconds'],'compact_seconds':c1['total_seconds'],'baseline_output_tokens':b1['output_tokens'],'compact_output_tokens':c1['output_tokens'],'baseline_repairs':max(0,b1['physical_calls']-1),'compact_repairs':max(0,c1['physical_calls']-1),'baseline_valid':b1['valid_output'],'compact_valid':c1['valid_output']})
  group['pairs']=pairs
  if pairs:
   bt=sum(x['baseline_first_input_tokens'] or 0 for x in pairs);ct=sum(x['compact_first_input_tokens'] or 0 for x in pairs)
   group['first_attempt_input']={'baseline':bt,'compact':ct,'reduction':reduction(bt,ct)}
  summary['groups'][phase or mode]=group
 allusage=[u for row in rows for u in row.get('provider_usage',[])]
 summary['provider']={'models':sorted({u['model'] for u in allusage}),'providers':sorted({u['upstream_provider'] for u in allusage}),'physical_calls':result['physical_calls'],'cost_usd':sum(u.get('cost_usd') or 0 for u in allusage),'input_tokens':sum(u.get('input_tokens') or 0 for u in allusage),'output_tokens':sum(u.get('output_tokens') or 0 for u in allusage),'cached_tokens':sum((u.get('usage',{}).get('prompt_tokens_details') or {}).get('cached_tokens') or 0 for u in allusage),'thinking_tokens':sum(u.get('thinking_tokens') or 0 for u in allusage)}
 # Compare delivered original text and coordinates for every fixed view.
 import sys;sys.path.insert(0,str(R/'02_BACKEND'))
 from semantic_runtime.legal_agent.gateway import compact_wire_view
 checks=[]
 for path in sorted((A/'artifacts/fixed-views').glob('*/*.json')):
  v=read(path)['view'];c=compact_wire_view(v,v['phase'])
  exact=all(a['text']==b['text'] and {k:x for k,x in a.items() if k!='spans'}=={k:x for k,x in b.items() if k!='spans'} and all({k:x for k,x in s.items() if k!='text'}=={k:x for k,x in t.items() if k!='text'} and (t.get('text')==s.get('text') or s.get('text','') in a['text']) for s,t in zip(a.get('spans',[]),b.get('spans',[]))) for a,b in zip(v.get('exact_evidence',[]),c.get('exact_evidence',[])))
  checks.append({'view':str(path.relative_to(R)),'evidence_cards':len(v.get('exact_evidence',[])),'source_text_and_coordinates_preserved':exact})
 summary['source_preservation']=checks
 summary['input_feasibility']={'answer_obligations':len(read(A/'artifacts/fixed-views/public-recorded-compose/compose.json')['view']['answer_obligations']),'question_plan_present':read(A/'artifacts/fixed-views/public-recorded-compose/compose.json')['view']['question_plan'] is not None,'limitation':'Recorded prior failure view has no obligations; Draft requires non-empty obligation_refs. Latency includes invalid generation/repair, not valid final answer completion.'}
 comp=summary['groups']['compose'];review=summary['groups']['review']
 summary['criteria_results']={'input_reduction_pass':comp.get('first_attempt_input',{}).get('reduction',0)>=.25,'compose_latency_pass':comp['reductions']['p50_seconds'] is not None and comp['reductions']['p50_seconds']>=.2,'no_new_format_failures_pass':all(not p['baseline_valid'] or p['compact_valid'] for g in [comp,review] for p in g['pairs']),'source_preservation_pass':bool(checks) and all(x['source_text_and_coordinates_preserved'] for x in checks)}
 if not comp['baseline']['valid_outputs'] and not comp['compact']['valid_outputs']:
  summary['criteria_results']['no_new_format_failures_pass']=None
  summary['criteria_results']['format_comparison_reason']='All baseline and compact outputs fail on the same empty-obligation recorded view; usable format stability unverified.'
 summary['groups']={k:v for k,v in summary['groups'].items() if v['baseline']['runs'] or v['compact']['runs']}
 write(A/'artifacts/summary.json',summary)
 now=datetime.now(timezone.utc).isoformat();manifest=read(A/'실험/manifest.json')
 for row in manifest['questions']:
  cid=row['case_id'];case=next(x for x in read(R/design['product_cases'])['cases'] if x['case_id']==cid)
  chosen=[x for x in rows if x['case_id']==cid]
  sections=[f"# 질문 {row['number']:03d} — {cid}",f"## 1. 실행 메타\n\nADR-0548 / run-001, {now}. 원본 상태: exact (측정의 모든 실제 요청과 응답). baseline 지침만 frozen r3를 바탕으로 reconstructed. 모델: google/gemma-4-31b-it / Parasail FP8 / thinking off. 오프라인 채점 없음.",f"## 2. 사용자 질문 원문\n\n```text\n{case['question']}\n```","## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n해당 없음. 입력·지연·형식 측정이며 법률 정답 기준이나 judge를 생성하지 않았다.","## 4. 제품 입력을 구성한 원값\n\n동일 immutable source generation과 공개 145문서 범위. 회수 구현 변경 없음. 전체 실제 server view 및 근거는 아래 원문 요청과 journal에 보존한다. 고정 replay는 저장된 동일 view를 양 arm에 제공한다.","### 회수·탈락 단계 원장 — run·arm별\n\n회수 효과 비교 해당 없음. 원문 generation과 구현 해시를 frozen-design 및 control-code-hashes에 고정했다. E2E의 선택 결과 차이는 프롬프트의 순수 효과로 해석하지 않는다.","## 5. 제품 모델 호출 — run·arm별 실제 원문"]
  for x in chosen:
   out=A/'artifacts/run-001'/x['mode']/cid/(x['arm'] if x['mode']=='e2e' else x['phase']+'/repeat-'+str(x['repeat'])+'/'+x['arm'])
   sections.append(f"### {x['mode']} / {x.get('phase','all')} / {x.get('repeat',1)} / {x['arm']}\n\n```json\n{dump(x)}\n```")
   for call in sorted((out/'model').glob('call-*')):
    for name in ['request.json','response.json','error.json','binding.json']:
     p=call/name
     if p.exists():sections.append(f"#### {call.name} / {name}\n\n```json\n{p.read_text().strip()}\n```")
   if (out/'http-response.json').exists():sections.append(f"#### 완성 HTTP 응답\n\n```json\n{(out/'http-response.json').read_text().strip()}\n```")
  sections.extend(["## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n실제 계획·선별·검토·형식보정 호출은 5절의 순서별 전체 요청·응답에 포함한다. 숨겨진 model call 없음.","## 7. 채점 호출과 반복 판정\n\n해당 없음. 법률 정확도와 의미 비열등성은 미측정. 형식 검사는 실제 runtime protocol을 통과한 출력의 존재로 측정한다.",f"## 8. 사례 최종 판정\n\n```json\n{dump(chosen)}\n```\n\n사전 지정 신규 정답/회귀 분류: 미측정. 모델 오류와 형식보정은 실제 로그 수치로만 보고한다. 오류 분류: other (성능·형식 측정)."])
  p=A/'실험'/row['file'];p.write_text('\n\n'.join(sections)+'\n');row['sha256']=sha(p)
 manifest['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
 manifest['results'].update(status='complete',by_arm={arm:{'accuracy':None,'accuracy_reason':'No legal gold evaluation in this latency probe',**{key:val[arm] for key,val in summary['groups'].items()}} for arm in ['baseline','compact']},comparisons=[{'baseline':'baseline','candidate':'compact','groups':summary['groups'],'criteria_results':summary['criteria_results']}],judge_disagreements=None,usage=summary['provider'],latency={key:{arm:g[arm]['p50_seconds'] for arm in ['baseline','compact']} for key,g in summary['groups'].items()},error_taxonomy=[{'type':'other','reason':'See exact schema failures/repairs and HTTP errors in per-case records; semantic correctness unmeasured'}])
 write(A/'실험/manifest.json',manifest)
 front=(A/'README.md').read_text().split('---',2)[1]
 table='| 측정 | 축약 전 | 축약 후 | 감소율 |\n|---|---:|---:|---:|\n'
 for key,g in summary['groups'].items():
  for metric,label in [('input_tokens','입력 토큰 합계'),('p50_seconds','논리 호출 p50 초'),('schema_repairs','실제 형식 보정 호출 수'),('terminal_failures','논리 호출 최종 형식 실패 수'),('first_response_p50_seconds','첫 응답 p50 초')]:
   b,c=g['baseline'][metric],g['compact'][metric];pct=reduction(b,c)
   table+=f"| {key} {label} | {b:,.2f} | {c:,.2f} | {pct*100:.1f}% |\n" if pct is not None else f"| {key} {label} | {b} | {c} | 해당 없음 |\n"
 sections=["# ADR-0548: 저장된 실제 작성 view의 Gemma 프롬프트 축약 실측","## 1. 결정 요약\n\n측정 완료, 운영 승격 보류. 이 저장 view는 answer_obligations=[]·question_plan=null이며 Draft 출력은 non-empty obligation_refs를 요구한다. 모든 출력 실패 가능성이 있는 과거 실패 context이므로 토큰/요청 응답 지연 측정에만 사용하고 정상 최종답변 완료 시간으로 간주하지 않는다. in-sample 성능 probe이며 decision_eligible=false. MAIN 활성 포인터·GENOS 배선 변경 없음. 사전 기준의 항목별 판정은 아래에 기록한다. 신규 형식 회귀 수는0이지만 양쪽 모두 정상 완료0이므로 형식 안정성 통과를 인증하지 않는다.","## 2. 문제와 변경 전 구조\n\nv5 요청의 원문 span.text 중복, response schema 반복, compose 탐색 메타데이터, 누적 phase 지침으로 토큰 및 호출 시간이 증가했다. 최종답변 작성은 compose이며 review는 후속 검토다. 이번 view는 과거 compose 실패 시 저장된 입력이며 의무 참조가 없다. 형식 보정은 검증 실패에만 발생한다. baseline은 r3 고정 지침과 변경 전 review suffix를 복원하고 두 arm 모두 현재 control flow를 사용했다.",f"## 3. 가설과 사전 판정 기준\n\n첫 작성 호출 입력 25% 이상 감소, 고정 원문 작성 논리 호출 p50 지연 20% 이상 감소, 신규 형식 실패 0, 원문·좌표 보존. 기준은 첫 model call 이전에 고정했다.\n\n```json\n{dump(summary['criteria_results'])}\n```","## 4. 실험 설계\n\n현재 v5 동일 runtime·공개 원문·provider·temperature=0·repair 한계. baseline은 변경 전 요청, compact는 축약 요청. 실제 공개 정관 질문의 20개 근거를 포함한 기존 compose view 하나에 작성 3쌍. AB/BA/AB 순서로 교차한다. 현재 E2E·review는 측정하지 않는다. candidate snapshot rev-001만 명시 import, registry 등록 없음.",f"## 5. 데이터·모델·재현성\n\n{design['generation']}, 공개145문서 범위. Gemma google/gemma-4-31b-it, Parasail FP8, thinking off, fallback 없음. [설계 해시](artifacts/frozen-design.json), [후보 해시](../../../../02_BACKEND/lawrag/research/candidates/adr_0548/compact/candidate.json), [모든 의존성 해시](artifacts/control-code-hashes.json). 법령 최신 버전·정답 기준은 확인하지 않았으며 성능 비교 조건만 고정했다.",f"## 6. 결과\n\n{table}\n첫 physical attempt의 동일 입력 비교와 각 쌍의 수치는 [전체 요약](artifacts/summary.json)에 있다. 법률 정확도·paired 신규 정답/회귀는 미측정이다.","## 7. 사례별 오류 분석\n\n1문항의 실제 모든 요청·응답·사용량·형식 보정·에러를 [질문 인덱스](실험/README.md)에 기록했다. 원문 view의 의무 참조 목록이 없어 obligation_refs를 빈 배열로 생성하고 runtime의 non-empty 검증에 실패하는지 원시 events에서 확인한다. 이는 정상 최종답변 속도 검증을 막는다. schema_repairs raw 필드는 invalid event 개수이며 실제 보정 호출 수는 최초 호출 뒤 physical attempt 수로 계산했다.",f"## 8. 비용·지연·회수 규모\n\n```json\n{dump(summary['provider'])}\n```\n\nprovider usage의 실제 입력·출력·비용을 사용했다. p95는 작은 표본의 nearest-rank이며 통계적 추론에 사용하지 않는다. 현재 전체 E2E·review는 미측정이다. ADR-0547 전체 실행은 색인 스키마 불일치·code hash drift로 모델 호출 전 실패했다. 회수 구현 변경 없음, 고정 compose/review replay에는 회수 단계가 없다. 원문 generation 및 retrieval 코드 해시를 고정했다. Golden recall은 미측정.","## 9. 해석\n\n고정 view의 최초 요청 입력 차이는 중복 제거 효과를 직접 측정한다. 논리 호출 시간에는 출력 생성량·형식 보정·provider 변동이 함께 들어간다. E2E는 선택 결과와 호출 경로가 달라질 수 있으므로 전체 시간 차이를 순수 프롬프트 효과로 주장하지 않는다. 출력 토큰을 함께 보고 원문 삭제 효과와 답변 길이 차이를 구분한다.","## 10. 한계와 일반화 가능 범위\n\n공개 정관 질문1개, 원문 view1개, arm별 작성3회의 in-sample probe. provider 캐시 수치는 요약에 기록했다. 생성 결과의 의미 비열등성은 미검증, GENOS 내부 모델·현장 latency는 미측정. 현재 local pinned r3 전체 릴리스와 신규 릴리스의 비교가 아니라 같은 현재 pipeline에서 복원한 이전 요청과 새 요청의 비교다.","## 11. 운영 결정·롤백 조건\n\n활성 MAIN 포인터/선택 릴리스·GENOS 리비전 변경 없음. 프롬프트 작업 코드의 기존 축약 변경 외 추가 제품 수정 없음. 외부 probe 단독으로 MAIN 승격하지 않는다. 향후 정답 누락·원문 손실·형식 실패 증가 검증 시 별도 ADR에서 후보를 재설계한다.","## 12. 재현 명령\n\n```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0548/report.py\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0548-gemma-recorded-compose-compaction --final\n```\n\n완료 artifact는 덮어쓰지 않는다. 신규 측정은 새 ADR에서 같은 frozen-design·snapshot 계보로 생성한다. [원시 파일 해시](artifacts/manifest.json)."]
 (A/'README.md').write_text('---'+front+'---\n\n'+'\n\n'.join(sections)+'\n')
 lines=['# ADR-0548 실험 질문 인덱스','실행 완료. MAIN unchanged, in-sample probe, decision_eligible=false. 법률 정답과 judge 미측정. 변경 가설·모델·frozen input은 [manifest](manifest.json)과 [설계](../artifacts/frozen-design.json)에 기록한다.','| 번호 | 질문 | 실행 | 원문 |\n|---:|---|---|---|']
 for q in manifest['questions']:lines.append(f"| {q['number']:03d} | {q['case_id']} | 저장된 동일 compose view의 작성3쌍 | [{q['file']}]({q['file']}) |")
 lines.append('회수 구현 변경 없음. E2E 회수 선택은 실제 journal에 보존. 고정 replay는 같은 저장 view. 정답/회귀 분류·golden recall 미측정. 비용·지연은 [요약](../artifacts/summary.json).')
 (A/'실험/README.md').write_text('\n\n'.join(lines)+'\n')
 # Only terminal files are hashed; artifact manifest itself is excluded.
 paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json']+[Path(__file__),R/'06_TOOLS/EXPERIMENTS/adr_0548/measure.py',R/'02_BACKEND/lawrag/research/candidates/adr_0548/compact/candidate.json']
 artifact={'schema_version':'adr-artifacts-v1','adr_id':'ADR-0548','created_at':now,'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact measured request/response/usage, frozen input, journal or reproducibility source','contains_raw_prompts_and_outputs':p.name in ['request.json','response.json','http-response.json','journal.sqlite']} for p in sorted(paths)]}
 write(A/'artifacts/manifest.json',artifact)
 print(dump(summary))
if __name__=='__main__':main()
