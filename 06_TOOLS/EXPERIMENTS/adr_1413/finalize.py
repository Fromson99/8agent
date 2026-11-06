"""Seal actual results and direct review. No model, no product mutation."""
from common import *
import re
base=ART/'public-live/photo-conversation-selected'
details=read(ART/'turn-details.json');reviews=read(ART/'direct-review.json')
audit=read(ART/'source-wire-audit.json')['cells'][0];calls=read(base/'calls.json')
baseline=read(DES/'baseline.json');candidate=read(DES/'candidate-selected.json')
current_pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
pointer_unchanged=current_pointer==baseline['pointer']
assert read(base/'binding.json')['selected_pointer']==baseline['pointer']
if not pointer_unchanged:
 assert read(ART/'postprocessing-pointer-drift.json')['run_binding_matches_frozen']
assert all(sha(ROOT/baseline['release']['code_root']/n)==h for n,h in candidate['selected_files'].items())
assert not any(audit[k] for k in ('source_mismatches','acl_violations','wire_mismatches'))
assert audit['budget_matches']
turns=[]
for t in details['turns']:
 if t['executed']:
  grade=reviews[str(t['number'])];assert grade['response_sha256']==t['response_sha256']
  turns.append({**t,'direct_review':grade})
 else:turns.append(t)
unknown=[i for i,c in enumerate(calls) if c['status'] in ('unknown','started')]
usage={'physical_calls':len(calls),'normal_model_responses':sum(c.get('http_status')==200 and c['status']=='responded' for c in calls),
 'confirmed429':sum(c.get('http_status')==429 for c in calls),'unknown':len(unknown),
 'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) or 0 for c in calls),
 'reported_prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) or 0 for c in calls),
 'reported_completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) or 0 for c in calls),
 'model_seconds':sum(c.get('seconds',0) for c in calls),'budget_reserved':audit['budget_reserved'],
 'same_request_id_extra_calls':sum((t.get('result',{}).get('duplicate') or {}).get('extra_model_calls',0) for t in turns),
 'sends_after_unknown':len(calls)-unknown[0]-1 if unknown else 0,'response_replay':0,'judge_model_calls':0}
assert usage['sends_after_unknown']==0 and usage['same_request_id_extra_calls']==0
latency={'by_turn':{str(t['number']):t.get('result',{}).get('request_seconds') for t in turns},'population_p95':None,'reason':'One fixed conversation; no population latency inference'}
summary=reviews['summary']
result={'verdict':summary,'MAIN':152,'code_files_unchanged':532,'active_pointer_unchanged':pointer_unchanged,'current_active_generation_at_postprocessing':current_pointer['generation'],'turns':turns,'usage':usage,'latency':latency,
 'field_photo_context_contract':details['field_photo_contract'],'source_checks':audit['source_checks'],'delivered_checks':audit['delivered_checks'],
 'source_mismatches':len(audit['source_mismatches']),'acl_violations':len(audit['acl_violations']),'wire_mismatches':len(audit['wire_mismatches']),
 'budget_matches':audit['budget_matches'],'product_changes':0,'deployment_changes':0,'quality_certified':False,
 'scope':'Local actual MAIN152 root service, public financial corpus, Qwen3.8 FP8/none, default ontologyOFF. GENOS internal model and the additional shareholder sequence were not executed.'}
put(ART/'result.json',result)
lines=[summary,'','실제 MAIN152 root service · 공개 원문 SQLite · Qwen3.8 FP8/none · 기본 온톨로지OFF.','사진의 첫 두 질문은 그대로 실행하고, 세 번째 명시 범위 확장 질문은 별도 진단으로 사전 동결했다.','']
for t in turns:
 lines.extend([f"턴{t['number']}: {t['question']}"])
 if t['executed']:
  r=t['result'];lines.extend([f"HTTP{r['http_status']} · {r['request_seconds']:.3f}초 · 모델{r['physical_calls']}회",'실제 답변: '+t['answer'],'판정: '+t['direct_review']['reason'],''])
 else:lines.extend(['미실행: '+t['reason'],''])
lines.extend(['추가 사진의 대화 연결 결함 검사','MAIN152의 실제 명령 검증 경로에 합성 모순을 넣어 거절을 재현했다. 거절 응답은 request에 저장되지만, 거절된 사용자 질문과 시스템 되물음은 다음 context/dialogue에서 빠졌다. 실제 현장 명령이 무엇이었는지는 미확인이고 이 검사는 외부 모델0회다.','',json.dumps({'usage':usage,'latency':latency,'source_checks':audit['source_checks'],'delivered_checks':audit['delivered_checks'],'source_mismatches':result['source_mismatches'],'acl_violations':result['acl_violations'],'wire_mismatches':result['wire_mismatches']},ensure_ascii=False,indent=2),'','이 작업의 제품 수정/MAIN 승격/현장 배포0. 시험은 MAIN152 고정 코드532개로 실행됐다. 결과 정리 시 별도 작업의 활성 MAIN153 전환을 발견했으며 최초 포인터 동일성 검사 실패와 실제 실행 binding을 보존했다. MAIN153 성능으로 해석하지 않는다. 독립 질문의 일반 성능·GENOS 내부 모델·모든 멀티턴 품질을 인증하지 않는다. 원격 완료/취소와 UNKNOWN 미보고 비용은 확인할 수 없다.'])
(ART/'실제_멀티턴_결과.txt').write_text('\n'.join(lines)+'\n')
put(RUN/'result.json',{'verdict':summary,'result_path':str((ART/'result.json').relative_to(ROOT)),'result_sha256':sha(ART/'result.json'),'usage':usage,'latency':latency})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',artifact_path=str((RUN/'result.json').relative_to(ROOT)),sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'selected':{'verdict':summary,'primary_two_turn_success':reviews['primary_two_turn_success'],'turn_grades':reviews,'usage':usage}},comparisons=[],judge_disagreements=0,usage=usage,latency=latency,error_taxonomy=reviews['error_taxonomy'])
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
sections=[('결정 요약',summary),('문제와 변경 전 구조','사용자 사진에서 정기총회 후속 질문이 기존 답변과 모순되며 원문 확인을 사용자에게 요구했다. 같은 질문을 현재 로컬 MAIN으로 실제 실행하라는 요청이다.'),
 ('가설과 사전 판정 기준',json.dumps(read(DES/'criteria.json'),ensure_ascii=False,indent=2)),('실험 설계','동일 세션의 사진 질문2개와 사전 선언한 명시 범위 확대1개. UNKNOWN/비200 후 종속 턴 중단. 한 번만 실행, 정답·이전 모델 응답 주입0. 추가 사용자 사진은 동결된 제품 입력을 바꾸지 않고 별도 합성 계약 확인으로 기록했다.'),
 ('데이터·모델·재현성',result['scope']),('결과','[실제 질문별 결과](artifacts/실제_멀티턴_결과.txt)와 [원시 대조](artifacts/turn-details.json). '+summary),
 ('사례별 오류 분석',json.dumps(reviews,ensure_ascii=False,indent=2)+'\n\n추가 사진의 거절 후 문맥 누락: artifacts/field-photo-context-contract.json. 초기 설계 검사에서 회수원장 mode/기준 arm 계획 메타2건을 송신 전에 정정했고 실패 기록을 보존했다.'),
 ('비용·지연·회수 규모',json.dumps({'usage':usage,'latency':latency,'source_checks':audit['source_checks'],'delivered_checks':audit['delivered_checks']},ensure_ascii=False,indent=2)),
 ('해석','실제 선택 명령, 적용 상태, 최종 원문 전달과 답변 의미를 구분한다. HTTP200이나 형식 검증만으로 정답을 판정하지 않는다. 세 번째 명시 범위 요청의 성공으로 두 번째 턴 실패를 상쇄하지 않는다.'),
 ('한계와 일반화 가능 범위','사진을 본 뒤 설계한 단일 대화 인샘플 probe. 외부 Qwen과 GENOS 내부 모델은 별도이며 현장 코드·세대 동일성 미확인. 최대주주 추가 사진의 전체 실모델 시퀀스는 실행하지 않았다.'),
 ('운영 결정·롤백 조건','이 작업의 제품수정/MAIN승격/원문DB변경/GENOS배포/메일0. 고정 MAIN152 코드532와 실제 실행 binding을 대조했다. 후처리 시 별도 작업의 MAIN153 전환으로 포인터 동일성 assertion이 실패했고 이를 artifacts/postprocessing-pointer-drift.json에 보존했다. 실제 시험 대상은 MAIN152이며 MAIN153 검증이 아니다. 실험 상태는 별도 runtime에 보존.'),
 ('재현 명령','.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1413/audit.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1413/inspect_turns.py\n실제 live 재실행은 새 ADR에서 사전 동결해야 한다. 기존 UNKNOWN 요청을 다시 보내지 않는다.')]
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN152 사진 멀티턴 실제 시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
q=m['questions'][0];p=ADR/'실험'/q['file'];p.write_text(p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\n'+summary+'\n\n'+json.dumps(reviews,ensure_ascii=False,indent=2)+'\n')
(ADR/'실험/README.md').write_text('# 실제 대화 결과\n\n- [photo-conversation]('+q['file']+') — '+summary+'\n')
print(json.dumps({'summary':summary,'usage':usage,'latency':latency},ensure_ascii=False,indent=2))
