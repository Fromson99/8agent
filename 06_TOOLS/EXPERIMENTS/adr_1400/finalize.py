"""Offline provider-cell interpretation; no model or product-state mutation."""
from common import *
import re,base64
m=read(ADR/'실험/manifest.json');baseline=read(DES/'baseline.json');candidate=read(DES/'candidate-repaired.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
assert all(sha(ROOT/baseline['release']['code_root']/n)==v for n,v in baseline['release']['files'].items())
assert all(sha(ROOT/candidate['code_root']/n)==h for n,h in candidate['selected_files'].items())
audits={a['case_id']:a for a in read(ART/'source-wire-audit.json')['cells']};cells=[]
for case in read(DES/'live-cases.json'):
 cid=case['id'];base=ART/'public-live'/(cid+'-repaired');measured=read(base/'result.json');calls=read(base/'calls.json') if (base/'calls.json').exists() else []
 a=audits[cid];assert a['budget_matches'];assert not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches'))
 turns=[]
 for step in case['steps']:
  d=base/('turn-'+str(step['number']))
  if not (d/'result.json').exists():turns.append({'number':step['number'],'question':step['question'],'executed':False,'reason':'Earlier failure or dependent knowledge gate'});continue
  r=read(d/'result.json');body=read(d/'response.json.gz')['body'];answer=body.get('answer') or {}
  turns.append({'number':step['number'],'question':step['question'],'executed':True,**{k:r.get(k) for k in ('status','http_status','goal_id','revision','method','executed','request_seconds','physical_calls','unknown','claims','duplicate')},'answer':answer.get('text','') if isinstance(answer,dict) else str(answer),'review':body.get('assembly',{}).get('term_agent',{}).get('review_explanation')})
  turns[-1]['executed']=True;turns[-1]['stages']=r['executed']
 assert len(read(base/'fixture.json'))==5
 assert turns[0]['http_status']==200 and turns[0]['physical_calls']==0
 assert turns[1]['http_status']==200 and turns[1]['physical_calls']==0 and turns[1]['stages']==[]
 b1=read(base/'turn-1/response.json.gz')['body'];b2=read(base/'turn-2/response.json.gz')['body'];ignore={'id','query_id'}
 same=all(b1.get(k)==b2.get(k) for k in ('goal_id','question_id','revision')) and {k:v for k,v in b1['answer'].items() if k not in ignore}=={k:v for k,v in b2['answer'].items() if k not in ignore}
 assert same
 unknown=[i for i,c in enumerate(calls) if c['status']=='unknown'];assert not unknown or unknown==[len(calls)-1]
 policy=read(DES/('provider-'+cid+'.json'));actual={c.get('actual_provider') for c in calls if c.get('http_status')==200 and c.get('actual_provider')};assert actual<={policy['providers'][0]['name']}
 continuity=[]
 for p in sorted((base/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  v=read(p);view=v['view']
  if view.get('source_stage')=='memory-resolve':
   out=p.with_name(p.name.replace('.json.gz','-output.json.gz'))
   continuity.append({'input_path':str(p.relative_to(ROOT)),'sha256':sha(p),'utterance':view.get('utterance'),'prior_goal_ids':[g.get('id') for g in view.get('goals',[])],'prior_response_present':any(g.get('previous_response',{}).get('text') for g in view.get('goals',[])),'literal_repeat_target':view.get('literal_repeat_target'),'actual_command':read(out) if out.exists() else None})
 knowledge={'attempted':(base/'knowledge/generations.json').exists(),'compiled':(base/'knowledge/compiled.json.gz').exists(),'published':(base/'knowledge/publication.json').exists(),'actual_usage':read(base/'knowledge/actual-usage.json') if (base/'knowledge/actual-usage.json').exists() else None,'conflict':read(base/'knowledge/conflict.json') if (base/'knowledge/conflict.json').exists() else None,'withdrawal':(base/'knowledge/withdrawal.json').exists(),'failure':read(base/'knowledge-failure.json') if (base/'knowledge-failure.json').exists() else None}
 diagnostics=[]
 for c in calls:
  if c['status']=='unknown':
   d=base/'raw'/f"call-{c['number']:03}";partial=read(d/'partial.json.gz') if (d/'partial.json.gz').exists() else None
   summary={'call':c['number'],'stage':c['stage'],'seconds':c.get('seconds'),'diagnostics':c.get('transport_diagnostics',{}),'error_type':c.get('error_type')}
   if partial:
    raw=base64.b64decode(partial['body_base64']);summary.update(partial_bytes=len(raw),partial_sha256=__import__('hashlib').sha256(raw).hexdigest(),partial_only_whitespace=not raw.strip())
   diagnostics.append(summary)
 usage={'physical_calls':len(calls),'normal':sum(c.get('http_status')==200 and c['status']=='responded' for c in calls),'known_rejected':sum(c.get('http_status')!=200 and c['status']=='responded' for c in calls),'unknown':len(unknown),'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),'reported_tokens':sum((c.get('usage') or {}).get('total_tokens',0) for c in calls),'saved_prefix_responses':5,'same_request_id_extra_calls':sum((t.get('duplicate') or {}).get('extra_model_calls',0) for t in turns),'sends_after_cell_unknown':0,'budget_reserved':a['budget_reserved'],'budget_matches':a['budget_matches']}
 cells.append({'provider':cid,'precision':policy['quantizations'][0],'actual_providers':sorted(actual),'turns':turns,'usage':usage,'repeat_equivalent':same,'continuity':continuity,'knowledge':knowledge,'unknown_diagnostics':diagnostics,'resources':read(base/'resource-final.json')})
usage={k:sum(c['usage'][k] for c in cells) for k in ('physical_calls','normal','known_rejected','unknown','reported_cost_usd','reported_tokens','saved_prefix_responses','same_request_id_extra_calls','sends_after_cell_unknown','budget_reserved')}
usage.update(grader_model_calls=0,unknown_unreported_cost=None if usage['unknown'] else 0,old_unknown_requests_resent=0)

for c in cells:
 base=ART/'public-live'/(c['provider']+'-repaired')
 command=read(base/'canonical/007-output.json.gz');check=read(base/'canonical/008-output.json.gz');intent=read(base/'canonical/009-output.json.gz')
 derivation=next(d for d in read(base/'authorized-derivations.json') if d['request_id'].endswith('turn-3'))
 previous=read(base/'turn-1/request.json')['question']
 assert command['method_id']=='PURPOSE_REVISE' and command['target']==c['turns'][0]['goal_id']
 assert check['request_relation']=='FOLLOWUP' and check['requested_task']==command['task']==derivation['task']==derivation['effective_question']
 assert derivation['effective_question']!=previous and '임시총회' in str(intent['issues'])
 c['current_state_transition']={'same_goal':True,'method':command['method_id'],'original_request':derivation['original_question'],'previous_task':previous,'actual_task':derivation['task'],'check':check,'new_issues':intent['issues'],'model_rewrote_task':True,'server_semantic_rewrite':False,'old_direct_scope_preserved':derivation['search_scope']}
rows=['| 제공자 | 실제 후속 목적·쟁점 | 최종 응답 | 초 | 새 물리 호출 |','|---|---|---|---:|---:|']
for c in cells:
 t=c['turns'][2];rows.append(f"| {c['provider']} {c['precision']} | 같은 goal / PURPOSE_REVISE / 임시총회 | HTTP{t['http_status']}·감독 UNKNOWN | {t['request_seconds']:.3f} | {t['physical_calls']} |")
details='\n'.join(rows)
verdict='명령 적용 후 현재 목적 검증을 수정했고 두 제공자에서 목적·쟁점 갱신을 실제 확인했다. 최종 답변은 두 조사 감독 응답의 UNKNOWN으로 전체 미통과다.'
limits='첫 대화의 성공5응답은 셀별 재생(합10)이며 후속부터 새 실제 Qwen이다. 각 제공자1회, REKA FP8/DeepInfra BF16로 순수 제공자 인과·반복 안정성 비교가 아니다. 이전 조항 범위를 현재 후속 목적에 과도하게 유지한 모델 판단이 남는다. 최종 답변·새주제/조건변경·새 지식 구축/승인/사용/충돌/철회는 실모델 완료를 주장하지 않는다. UNKNOWN의 원격 완료·취소·미보고 비용/내부 원인은 미확정이다. 법률 정답 검증은 별도다.'
tests={name:read(ART/name/'result.json')['passed'] for name in ('unit-r1','compatibility-r2','integrated-unit','native-state-boundary-r3')}
assert tests=={'unit-r1':11,'compatibility-r2':37,'integrated-unit':13,'native-state-boundary-r3':1}
observations=json.dumps([{'provider':c['provider'],'transition':c['current_state_transition'],'unknown':c['unknown_diagnostics'],'knowledge':c['knowledge']} for c in cells],ensure_ascii=False,indent=2)
report={'title':'멀티턴 현재 목적·실행 상태 검증 수정과 Qwen 재확인','verdict':verdict,'details':details,'cells':cells,'usage':usage,'limits':limits,'observations':observations,'tests':tests,'unique_contracts':51,'structural_transition_pass':{'correct':2,'total':2},'final_answer_pass':{'correct':0,'total':2},'main_unchanged_during_probe':True,'current_MAIN_at_probe':147,'product_modules':2}
put(ART/'final-review.json',report);put(RUN/'result.json',{k:report[k] for k in ('verdict','details','usage','limits','tests','structural_transition_pass','final_answer_pass')})
(ART/'수정과_Qwen_결과.txt').write_text(verdict+'\n\n'+details+'\n\n'+limits+'\n\n'+json.dumps({'usage':usage,'tests':tests,'unique_contracts':51},ensure_ascii=False,indent=2)+'\n\n'+observations+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical1398_only':True},'repaired':read(RUN/'result.json')},comparisons=[],judge_disagreements=0,usage=usage,latency={c['provider']:c['turns'][2]['request_seconds'] for c in cells},error_taxonomy={'remote_unknown':usage['unknown'],'original_mismatches':0,'acl_violations':0,'wire_mismatches':0,'test_fixture_preparation_failures_preserved':True});put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
sections=[('결정 요약',verdict),('문제와 변경 전 구조','1398은 후속을 기존 RESEARCH_REENTER/SELECT로 연결하고 task/queries를 유지했다. 검증자도 기존 목적을 실행하는 것을 승인했다. 수정은 요청 관계와 원하는 목적을 검토자가 함께 제출하고, 순수 상태 미리보기 및 실제 적용 상태와 대조한다.'),('가설과 사전 판정 기준',json.dumps(read(DES/'criteria.json'),ensure_ascii=False)),('실험 설계','기존528에 제품2+SQL메타/핀을 수정한 공식 후보에서 REKA/DeepInfra 독립 각1회. 성공 첫5응답 재생 후 실제 후속. 잘못된 valid=true도 요청 관계/명령 적용 후 목적이 모순이면 기존 bounded_decision 최초+보완1회로 전체 명령 재판단. 서버 의미 보정0. 현재MAIN147 공통감시자는 별도530 통합본으로 보존하고 PASS가 목적 검증을 대체하지 못하게 했다.'),('데이터·모델·재현성','공개 상법7bbe815ff43b6635/로컬SQLite. Qwen3.8 qwen/qwen3.8-27b, 추론none, 출력상한없음, 셀별제공자고정/fallback0. 코드/스키마/입출력/원응답/부분수신/저널/예산/실제원문 대조 보존. MAIN147 변경·운영게시·현장·메일0은 이 probe 당시 범위다. 후속 사용자 MAIN 반영 지시는 ADR1403으로 별도 기록.'),('결과',details),('사례별 오류 분석',observations+'\n\n초기 범위선점 relation 인자 오류, MAIN146→147 병행변경 전송전 차단, 현재/과거 fixture의 review_generate/선택단계/압축 필드 차이와 검사 모듈명 충돌을 보존했다. 전체 source fixture4회는 오래된 대역 응답이 현행 최소 스키마를 충족하지 못했다. 별도 실제 API 경계 검사는 INTENT에 의도한 오류를 주입해 잘못된 승인→원모델보완→상태저장→현재목적의 실제 RAG 진입을 검증했다. 완성 답변 시험으로 계산하지 않는다.'),('비용·지연·회수 규모',json.dumps({'usage':usage,'tests':tests,'unique_contracts':51},ensure_ascii=False)),('해석','현재 목적이 적용되는 기계적 연결은 실제2/2 확인했다. 공통 reason PASS만으로는 요청 목적 검증을 생략하지 않는다. 같은 이유·행동이 모두 틀린 경우와 법률 정답·검색범위 판단의 정확성은 이번 필드 계약만으로 보장되지 않는다.'),('한계와 일반화 가능 범위',limits),('운영 결정·롤백 조건','본 probe는 MAIN147 유지. 사용자 후속 지시로 통합530의 MAIN 반영은 별도ADR1403이 담당한다. 이 후보의 실제Qwen은528이고 현재공통감시자 보존530 통합본은13단위+API경계1 검사로 확인한 차이를 명시한다. 초기51검사는 Qwen 의미 정확도 보증이 아니다.'),('재현 명령','.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1400/audit.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1400/ledger.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1400/finalize.py\n새 실제 모델 호출은 새 ADR로 예약하며 기존 UNKNOWN을 재송신하지 않는다.')]
(ADR/'README.md').write_text('---'+front+'---\n\n# '+report['title']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
for q in m['questions']:
 c=next(c for c in cells if c['provider']==q['case_id']);case=next(c for c in read(DES/'live-cases.json') if c['id']==q['case_id'])
 parts=[('실행 메타',f"{c['provider']} {c['precision']}, fixed528, prefix5 saved responses; actual inference begins at T3."),('사용자 질문 원문','\n'.join(str(s['number'])+'. '+s['question'] for s in case['steps'])),('기준답변 — 채점 전용, 제품 입력 비공개','같은 목표의 새 목적이 task/쟁점/실제질의에 반영되어야 한다. 법률 답변은 상법365②/③ 등의 실제 원문에 대조하며 모델 입력으로 기대 조문/결론을 주입하지 않는다.'),('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz 및 source-wire-audit.json. 원문/ACL/전송/예산 직접 대조.'),('제품 모델 호출 — run·arm별 실제 원문',f"artifacts/public-live/{c['provider']}-repaired/raw, canonical, fixture, turn-* 원시 파일과 해시 보존."),('중간 LLM 호출 — router/compiler/verifier/repair','같은 셀 generations.json과 canonical 모든 요청/출력, 실패 부분 수신을 참조.'),('채점 호출과 반복 판정','새 채점모델0, 원문·계약·DB·실제 실행 필드를 직접 대조. 제공자별1회.'),('사례 최종 판정',json.dumps(c,ensure_ascii=False,indent=2))]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(parts,1))+'\n')
(ADR/'실험/README.md').write_text('# 질문 및 실제 결과\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
print(json.dumps({'verdict':verdict,'usage':usage,'tests':tests},ensure_ascii=False))
