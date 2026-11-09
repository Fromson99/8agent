"""Finalize ADR-1424 (financial CM51 on MAIN161) from recorded evidence; no model calls."""
from common import *
import statistics,csv,html
from collections import Counter
batch=read(ART/'batch-completed.json');audit=read(ART/'source-wire-audit.json');review=read(ART/'direct-review.json')
rows={r['case_id']:r for r in read(ART/'review-input.json')['rows']};cases=read(DES/'live-cases.json')
baseline=read(DES/'baseline.json');rel=baseline['release']
assert all(sha(ROOT/rel['code_root']/n)==h for n,h in rel['files'].items())
data=ROOT/rel['data_path'];assert sha(data/'store.sqlite')==read(data/'manifest.json')['store_sha256']
mism={k:sum(len(a[k]) for a in audit['cells']) for k in ('source_mismatches','acl_violations','wire_mismatches')};assert not any(mism.values()),mism
assert all(a['budget_matches'] for a in audit['cells'])
bound={read(ART/'public-live'/(c['id']+'-selected')/'binding.json')['selected_pointer']['generation'] for c in cases};assert bound=={161},bound
physical=[c for case in cases for c in read(ART/'public-live'/(case['id']+'-selected')/'calls.json')]
out=[]
for case in cases:
 r=rows[case['id']];v=review[case['id']]
 assert v['response_sha256']==r['response_sha256']
 out.append({'case_id':case['id'],'question':case['steps'][0]['question'],'grade':v['grade'],'failure_type':v['failure_type'],'reason':v['reason'],'answer':r['answer'],
  'seconds':r['request_seconds'],'physical_calls':r['physical_calls'],'claims':r['claims'],'needs_guidance':r['needs_guidance'],
  'required_acquired':r['required_acquired'],'required_cited':r['required_cited'],'required_total':r['required_total'],'registry_version_differs':r['registry_version_differs'],
  'same_section_reads':len(r['same_section_reads']),'unread_shown':r['unread']['shown']})
lat=[o['seconds'] for o in out];grades=Counter(o['grade'] for o in out)
allacq=[o for o in out if o['required_acquired']==o['required_total']];noneacq=[o for o in out if o['required_acquired']==0]
dups=[read(p) for p in (ART/'public-live').glob('*/turn-1/duplicate.json')];assert all(d['same_answer'] and d['extra_model_calls']==0 for d in dups)
result={'selected_MAIN':161,'release_id':baseline['pointer']['release_id'],'serving_files_unchanged':533,'source_unchanged':True,'all_cells_bound_generation':161,
 'active_pointer_at_finalization':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'],'pointer_changed_after_batch_by_other_session':True,
 'state':'COMPLETED_WITH_FAILURES','execution_state':batch['state'],'questions':51,'executed_responses':len(out),
 'pass':grades['PASS'],'partial':grades['PARTIAL'],'fail':grades['FAIL'],'pass_rate':grades['PASS']/51,
 'failure_types':dict(Counter(o['failure_type'] for o in out if o['grade']!='PASS')),
 'required_articles':{'total':sum(o['required_total'] for o in out),'acquired':sum(o['required_acquired'] for o in out),'cited':sum(o['required_cited'] for o in out),
   'cases_all_acquired':len(allacq),'pass_when_all_acquired':sum(o['grade']=='PASS' for o in allacq),'cases_none_acquired':len(noneacq),'pass_when_none_acquired':sum(o['grade']=='PASS' for o in noneacq)},
 'needs_guidance':sum(bool(o['needs_guidance']) for o in out),'zero_claims':[o['case_id'] for o in out if o['claims']==0],
 'same_section_auto_reads':sum(o['same_section_reads'] for o in out),'cases_with_same_section_reads':[o['case_id'] for o in out if o['same_section_reads']],
 'unread_items_shown':sum(o['unread_shown'] for o in out),
 'processing_errors':{'cm-028':'guided answer output repeated an evidence reference; verify raised Duplicate evidence reference; no repair; diagnostics recorded issues=[]',
                      'cm-029':'4th navigation decision repeated an unchanged structure lookup; rejected without repair; MODEL_DECISION_UNRESOLVED -> generic error; acquired 소득세법 시행령 163조 not used'},
 'display_findings':['when an answer has no claims, the unread-connection section is printed before the body (cm-002, cm-029)','generic "모델의 판단을 처리하는 과정에서 오류" hides the specific, repairable cause'],
 'physical_calls':len(physical),'unknown':sum(c['status'] in ('unknown','started') for c in physical),
 'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) or 0 for c in physical),
 'reported_prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) or 0 for c in physical),'reported_completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) or 0 for c in physical),
 'latency_seconds':{'min':min(lat),'median':statistics.median(lat),'p95':sorted(lat)[round((len(lat)-1)*.95)],'max':max(lat),'sum':sum(lat)},
 'source_checks':sum(a['source_checks'] for a in audit['cells']),'delivered_checks':sum(a['delivered_checks'] for a in audit['cells']),**mism,'budget_matches':True,
 'duplicate_checks':{'checked':len(dups),'extra_model_calls':0,'all_same_answer':True},
 'ontology':{'enabled':False},'product_changes':0,'new_judge_api_calls':0,'quality_certified':False,'in_sample':True,
 'scope':'Local actual MAIN161 root service, external Qwen3.8, financial CM51 known questions once each; graded against registered reference answers on the current stored originals. Not a holdout, repeatability rate, current-law certification or GENOS evaluation.',
 'rows':out}
put(ART/'result.json',result);RUN.mkdir(exist_ok=True)
put(RUN/'result.json',{'result_path':str((ART/'result.json').relative_to(ROOT)),'result_sha256':sha(ART/'result.json')})
summary=f"MAIN161 · financial CM 51문항: 기준답변 일치 {grades['PASS']}개, 부분 {grades['PARTIAL']}개, 실패 {grades['FAIL']}개. 응답 51/51 HTTP200, 모델 {len(physical)}회, UNKNOWN {result['unknown']}회."
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',artifact_path=str((RUN/'result.json').relative_to(ROOT)),sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'selected':{'correct':grades['PASS'],'total':51,'accuracy':grades['PASS']/51,'partial':grades['PARTIAL'],'decision_eligible':False,'scope':'direct review against registered reference answers; one run per question'}},
 comparisons=[],judge_disagreements=0,usage={k:result[k] for k in ('physical_calls','unknown','reported_cost_usd','reported_prompt_tokens','reported_completion_tokens')},latency=result['latency_seconds'],
 error_taxonomy=[{'type':o['failure_type'],'case_id':o['case_id'],'grade':o['grade']} for o in out if o['grade']!='PASS'])
for q in m['questions']:
 p=ADR/'실험'/q['file'];own=next(o for o in out if o['case_id']==q['case_id'])
 p.write_text(p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\n'+json.dumps(own,ensure_ascii=False,indent=2)+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
grade_ko={'PASS':'통과','PARTIAL':'부분','FAIL':'실패'}
lines=[summary,'','선택 MAIN161 실제 root service · 로컬 SQLite 원문 · Qwen3.8 Parasail FP8/none · 출력상한 없음 · 외규 모드 · public∩financial 44문서. 51개 요청 모두 MAIN161에 결속(실행 뒤 다른 세션이 MAIN164 선택).',
 '기준답변과 현재 저장 원문을 직접 대조. 알려진 질문(holdout 아님), 질문당 1회. 법률 일반 품질 인증 아님.','',json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2),'']
for o in out:
 lines+=[f"{o['case_id']} · {grade_ko[o['grade']]}{(' · '+o['failure_type']) if o['failure_type'] else ''} · 필수조문 확보 {o['required_acquired']}/{o['required_total']} · {o['seconds']:.1f}초 · 호출 {o['physical_calls']}",
         o['question'],'판정: '+o['reason'],'실제 답변: '+o['answer'],'']
(ART/'CM51_결과.txt').write_text('\n'.join(lines))
with (ART/'CM51_결과.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['case_id','grade','failure_type','required_acquired','required_total','seconds','physical_calls','question','reason','answer']);w.writeheader()
 for o in out:w.writerow({k:o[k] for k in w.fieldnames})
front=(ADR/'README.md').read_text().split('---',2)[1]
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
ft=result['failure_types'];ra=result['required_articles']
vals=[summary,
 '사용자 지시로 financial CM 51문항을 선택 MAIN161에 실제 실행. R5 30문항(ADR-1423)은 조항을 지정한 질문이었고, CM은 업무 문맥이 붙은 실무 질문이다.',
 json.dumps(read(DES/'criteria.json'),ensure_ascii=False),
 '51문항 순차 독립 실행(새 세션·격리 runtime), 질문 문자열만 전송. 등록 기준답변·근거 좌표는 채점 전용. 작업 트리 파생 핀31은 실행 중만 MAIN161 바이트로 교체 후 복원. 범위 밖 필수 문서(cm-050의 중소기업기본법·창업지원법 시행령)는 첫 호출 전 기록.',
 'MAIN161 533파일, 같은 원문 세대. 등록부 문서 ID는 이전 세대라 법령명·조문으로 현재 문서에 대응시켜 확보/인용을 대조.',
 json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2),
 f"실패 유형: 필수 조문 미확보 {ft.get('NOT_READ',0)}, 확보했지만 다른 조문을 근거로 답함 {ft.get('WRONG_BASIS',0)}, 원문을 잘못 읽음 {ft.get('MISREAD',0)}, 처리 오류 {ft.get('PROCESSING_ERROR',0)}; 부분: 핵심 누락 {ft.get('INCOMPLETE',0)}, 용어 오인 {ft.get('MISLABEL',0)}, 근거 일부 다름 {ft.get('BASIS_DIFFERS',0)}. 처리 오류 2건은 재생 진단(diag-cm-028/029)으로 원인 확인: 근거 참조 중복 검증 거절과 바뀌지 않은 구조 조회 반복 거절, 둘 다 보완 없이 일반 오류 문구로 끝남. 문항별 내용은 CM51_결과.txt.",
 f"물리 {len(physical)}회, 보고비용 ${result['reported_cost_usd']:.6f}, 중앙값 {result['latency_seconds']['median']:.1f}초.",
 f"필수 조문을 모두 확보한 {ra['cases_all_acquired']}문항 중 {ra['pass_when_all_acquired']}개 통과, 하나도 확보하지 못한 {ra['cases_none_acquired']}문항 중 {ra['pass_when_none_acquired']}개 통과. 주된 병목은 업무 문맥 질문에서 필요한 조문을 찾아 읽지 못하는 탐색 단계다. 같은 절 자동 읽기는 CM에서 {len(result['cases_with_same_section_reads'])}문항에서 발동.",
 '알려진 질문 51개(holdout 아님), 1회 실행, 온톨로지 OFF. 등록부 기준일(2026-08-27) 이후 개정된 조문은 현재 원문 기준으로 판정. 멀티턴 이어 찾기·GENOS 현장·Oracle 미검증.',
 '제품수정/MAIN승격/원문변경/GENOS배포/메일 없음. 같은 요청 재전송 없음.',
 '원본: artifacts/public-live/{case}-selected/raw·canonical. 읽기 전용 후처리: audit.py → ledger.py → collect_review.py → direct-review.json → finalize.py → manifest.py. 처리 오류 재생: replay_diag.py <case> <out> (MAIN161 스냅숏, 네트워크0).']
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN161 financial CM 51문항 실제 실행\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
(ADR/'실험/README.md').write_text('# financial CM 51문항 결과\n\n'+summary+'\n\n| 질문 | 결과 |\n|---|---|\n'+'\n'.join('| ['+o['case_id']+']('+next(q['file'] for q in m['questions'] if q['case_id']==o['case_id'])+') | '+grade_ko[o['grade']]+(' · '+o['failure_type'] if o['failure_type'] else '')+' |' for o in out)+'\n')
put(ART/'FINAL_VALIDATION.json',{'main':161,'source_store_unchanged':True,'source_acl_wire_mismatches':0,'budgets_match':True,'pass':grades['PASS'],'partial':grades['PARTIAL'],'fail':grades['FAIL'],'quality_certified':False})
print(summary);print(json.dumps(result['required_articles'],ensure_ascii=False));print(json.dumps(result['failure_types'],ensure_ascii=False))
