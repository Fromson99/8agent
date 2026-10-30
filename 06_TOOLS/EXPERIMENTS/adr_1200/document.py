"""Finalize saved experiment results only; never dispatch or mutate product code."""
from common import *
import re
r=read(RUN/'result.json');m=read(ADR/'실험/manifest.json');case_rows=r['cases'];full_pass=all(x.get('executed') and x['gate']['passed'] for x in case_rows)
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-supervisor-recovery-live';O.mkdir(parents=True,exist_ok=True)
observations=[]
for x in case_rows:
 if x['executed']:
  P=ART/'live'/x['case_id'];d=read(P/'diagnosis.json');s=read(P/'storage-audit.json');p=read(P/'prompt-audit.json');c=read(P/'composition-audit.json');review=read(P/'content-review.json')
  observations.append({'case_id':x['case_id'],'executed':True,'diagnosis':d,'storage':s,'prompts':p,'composition':c,'content_review':review,'gate':x['gate'],'answer_path':str((P/'answer.txt').relative_to(ROOT))})
 else:observations.append({'case_id':x['case_id'],'executed':False,'reason':x['reason']})
put(O/'observations.json',observations)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Proposed' if full_pass else 'Rejected'),('main_wiring','unchanged'),('in_sample','true'),('decision_eligible','false')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
notes=[]
for x in observations:
 if not x['executed']:notes.append(x['case_id']+': 미실행. '+x['reason']);continue
 d=x['diagnosis'];review=x['content_review'];gate=x['gate']
 notes.append(f"{x['case_id']}: 전체{d['elapsed_seconds']:.3f}초·모델{d['model_transport_seconds']:.3f}초·물리{d['model_calls']}회. 전체기준{'통과' if gate['passed'] else '미통과'}. "+review.get('reason','')+' / 실패 조건: '+', '.join(k for k,v in gate['checks'].items() if not v))
summary='\n'.join(notes)
sections=[('결정 요약','사용자 실제 실험 요청으로 MAIN117 선택service에서 CM007을1회 실행하고, 전체 사전 기준 통과 때만009를 실행한다. '+('두 사례 모두 사전 기준을 통과했다.' if full_pass else '사전 전체 기준을 충족하지 못한 사례가 있으며 실패·미실행을 보존한다.')),
 ('문제와 변경 전 구조','1195는 원문과 accepted claim에 있던 국내소재외국지주회사 분류 조건이 마지막 서술형 재작성에서 빠졌다.1197/MAIN117은 검증된 content/text를 서버가 조립하고 마지막COMPOSE 모델 호출을 생략한다.'),
 ('가설과 사전 판정 기준','[동결 기준](artifacts/design/criteria.json). 원문 확보·최종 인용·권한·예산·저장·요구검토·실제 내용·새 표시 계약을 모두 확인한다. 실패 시 같은 사례나 후속009를 자동 반복하지 않는다.'),
 ('실험 설계','완료1197/verified 부모, 실제 선택 릴리스와 동일466파일. cm007→조건부cm009 각1회. 같은65문서권한·새빈runtime. 기준답변/필수좌표는 평가전용이며 제품 입력·보완 입력에 넣지 않는다. known-case in_sample probe이고 품질 인증이 아니다.'),
 ('데이터·모델·재현성','같은MAIN117 데이터·Qwen3.8·Parasail FP8 기본·확정429만NearAI1회·물리별차감. 40/1024/1800·개별180초·출력상한없음·온톨로지OFF·자원기준 동일. frozen snapshot과 실제 선택 service466해시를 대조했다.'),
 ('결과',summary+'\n\n[전체 결과](artifacts/run-001/result.json) · [사용자 TXT](../../../09_ARTIFACTS/AUDITS/20261029-supervisor-recovery-live/실험결과.txt).'),
 ('사례별 오류 분석', '\n\n'.join(x['content_review'].get('reason','') for x in observations if x['executed']) or '미실행. 원본 기록 참조.'),
 ('비용·지연·회수 규모',f"물리{r['physical_calls']}회·평가모델0. 보고된 응답비용 {r['usage']['known_response_cost_usd']:.9f}달러. 미보고 사용량은0으로 단정하지 않는다. 호출/지연/회수 원장은 결과에 보존했다. p95·일반 성능 개선율은 산출하지 않는다."),
 ('해석','원문 확보, 모델 판단, 최종 표시, 저장은 각각 별도 확인한다. 새 표시 계약의 내용 보존이 ASSESS 의미 판단의 완전성을 보증하지 않는다. 공급자별 차이는 통제 실험이 아니므로 인과효과로 설명하지 않는다.'),
 ('한계와 일반화 가능 범위','알려진 두 질문의 현재 저장 원문 기준이다. 최신 법률 효력·일반 정확도·GENOS 성능을 인증하지 않는다. 같은7번자동재시험0. UNKNOWN은 원격 취소나 미과금의 증거가 아니다. 이전 실패는 소급 재판정하지 않는다.'),
 ('운영 결정·롤백 조건','작업 제품·MAIN117·GENOS 배포는 그대로 유지한다. 이번은 실험이며 코드 수정·MAIN 재승격·모델 비교·Git·메일을 수행하지 않았다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_1200/setup.py, live.py cm-007, 각 audit/prompt/composition/diagnose와 오프라인 content review, gate.py. 조건부cm009도 동일 순서. aggregate.py/document.py는 종료한 기록만 읽는다. 같은 dispatch를 재실행하면 거절한다.')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# MAIN117 실제007 및 조건부009\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 요청 기록\n\n'+ '\n'.join(f"- [{x['case_id']}](질문-{i:03}-{x['case_id']}.md): "+('기준 통과' if x.get('executed') and x['gate']['passed'] else '미통과' if x.get('executed') else '미실행') for i,x in enumerate(case_rows,1))+'\n')
a=read(ART/'manifest.json');paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and 'runtime' not in p.parts and 'snapshot' not in p.parts]
paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/read(DES/'freeze-preflight-002.json')['candidate_revision']['manifest_path']]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen live request, physical/canonical audit, result and failure evidence','contains_raw_prompts_and_outputs':p.suffix=='.gz' and ('raw' in p.parts or 'canonical' in p.parts)} for p in paths]
(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
text='MAIN117 실제 실험 결과\n\n'+summary+'\n\n'
for x in observations:
 if not x['executed']:continue
 d=x['diagnosis'];text+=f"{x['case_id']} 상세\nHTTP {d['return_http_status']}·저장 {x['storage'].get('stored_request_status')}·도구 {sum(z['tool_used'] for z in d['runs'])}회. 원문 {d['source_checks']} / 모델입력 {d['model_view_span_checks']}구간 대조, 불일치 {len(d['source_mismatches'])}·권한위반 {len(d['acl_violations'])}. 물리/예산 일치 {d['physical_budget_matches']}.\n최종 조립 보존 검사 {x['composition']['passed']}·내용 검토 {x['content_review']['passed']}. 자원중단 {d['resource']['resource_stop']}·스왑증가 {d['resource']['maximum_host_swap_growth_mib']:.3f}MiB·남은 통신프로세스 {d['remaining_worker_pids']}.\n실제 답변: {x['answer_path']}\n\n"
text+=f"물리 합계{r['physical_calls']}회. 보고 비용{r['usage']['known_response_cost_usd']:.9f}달러. 사용량 전체 보고 여부 {r['usage']['usage_complete']}. 미보고 비용은0이 아니다.\nMAIN117/제품 유지·GENOS/Git/메일 미수행. 같은 사례 자동재시험0·평가모델0. 알려진 사례 probe이며 일반 성능/속도/법률 정확도 인증이 아니다. 저장 원문 기준이며 최신 법령 효력을 별도 확인한 것은 아니다.\n"
(O/'실험결과.txt').write_text(text)
(O/'핵심결과.txt').write_text('MAIN117 실제 시험\n\n'+summary+f"\n\n물리{r['physical_calls']}회·MAIN117유지. 자세한 원문/입출력/내용 검토는 실험결과.txt와 ADR1200 참조.\n")
print(summary)
