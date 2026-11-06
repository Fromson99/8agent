"""Offline provider-cell interpretation; no model or product-state mutation."""
from common import *
import re,base64
m=read(ADR/'실험/manifest.json');baseline=read(DES/'baseline.json');candidate=read(DES/'candidate-repaired.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
assert all(sha(ROOT/baseline['release']['code_root']/n)==v for n,v in baseline['release']['files'].items())
assert all(sha(ROOT/candidate['code_root']/n)==h for n,h in candidate['selected_files'].items())
audits={a['case_id']:a for a in read(ART/'source-wire-audit.json')['cells']};cells=[]
for case in read(DES/'live-cases.json'):
 cid=case['id'];base=ART/'public-live'/(cid+'-provider-matrix');measured=read(base/'result.json');calls=read(base/'calls.json') if (base/'calls.json').exists() else []
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
rows=['| 제공자 | 턴 | 결과 | 초 | 새 물리 호출 |','|---|---:|---|---:|---:|']
for c in cells:
 for t in c['turns']:
  if not t['executed']:rows.append(f"| {c['provider']} {c['precision']} | {t['number']} | 미실행 | — | 0 |");continue
  label='저장 응답 재생' if t['number']==1 else '검증 답변 반복' if t['number']==2 else ('명령 검증 실패→CLARIFY' if t.get('status')=='CLARIFY' else '설명 답변' if t['claims'] else '원문/안내') if t['http_status']==200 else 'UNKNOWN/실패'
  rows.append(f"| {c['provider']} {c['precision']} | {t['number']} | HTTP{t['http_status']} · {label} | {t['request_seconds']:.3f} | {t['physical_calls']} |")
details='\n'.join(rows)
followups=[next(t for t in c['turns'] if t['number']==3) for c in cells]
verdict='다른 제공자2곳의 독립 재확인을 완료했다. '+('두 곳 모두 암묵적 후속 질문을 완료하지 못했다.' if all(t.get('http_status')!=200 or not t.get('claims') for t in followups) else '후속 질문과 이후 단계의 실제 완료 범위는 결과표와 기록을 따른다.')
limits='각 제공자 독립1회, 공개 상법1문서, 동일 코드·고정 성공 문맥을 사용했다. T1은 Parasail의 성공5응답을 재생한 시험 준비이며 새 제공자의 첫 답변 성공/속도로 계산하지 않는다. DeepInfra는 BF16, REKA는 FP8이므로 제공자만의 인과 비교가 아니다. UNKNOWN은 원격 완료·취소·미보고 비용을 확인하지 못한 상태다. 원격 내부 원인·전체 안정성·일반 법률 정답률·지식 수명 완료를 추정하지 않는다. 기존1397 UNKNOWN은 재전송하지 않았고 제공자별 새 대화·요청ID를 사용했다.'
diagnosis=read(ART/'command-and-execution-diagnosis.json')
observations=diagnosis['interpretation']+'\n\n실제 DeepInfra 질의: '+json.dumps(diagnosis['deepinfra'],ensure_ascii=False)+'\n\n'+json.dumps([{'provider':c['provider'],'continuity':c['continuity'],'knowledge':c['knowledge'],'unknown':c['unknown_diagnostics']} for c in cells],ensure_ascii=False,indent=2)
report={'title':'Qwen 다른 제공자 멀티턴 재확인','verdict':verdict,'details':details,'cells':cells,'usage':usage,'limits':limits,'observations':observations,'main_unchanged':True,'product_changes':0,'historical_parasail':'ADR1397 T3: 181.608초/2물리 중 memory-resolve UNKNOWN179.939초. 새로운 비교 셀로 계산하지 않는다.'}
put(ART/'final-review.json',report);put(RUN/'result.json',{k:report[k] for k in ('verdict','details','usage','limits','main_unchanged','product_changes')})
(ART/'제공자_비교결과.txt').write_text(verdict+'\n\n'+details+'\n\n'+limits+'\n\n'+json.dumps(usage,ensure_ascii=False,indent=2)+'\n\n'+observations+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'provider-matrix':read(RUN/'result.json')},comparisons=[],judge_disagreements=0,usage=usage,latency={c['provider']:{str(t['number']):t.get('request_seconds') for t in c['turns'] if t['executed']} for c in cells},error_taxonomy={'remote_unknown':usage['unknown'],'original_mismatches':0,'acl_violations':0,'wire_mismatches':0});put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
sections=[('결정 요약',verdict),('문제와 변경 전 구조','1397 Parasail FP8은 실제 첫 답변과 무호출 반복 뒤 memory-resolve에서 공백 응답으로 미완료됐다. 사용자 요청으로 제공자를 바꾸고 같은 후속 실행을 확인한다. 제품 코드528파일과 원문/법률/권한 검증은 그대로다.'),('가설과 사전 판정 기준',json.dumps(read(DES/'criteria.json'),ensure_ascii=False)),('실험 설계','REKA FP8, DeepInfra BF16 순서로 독립 세션. 각 성공5응답 재생→무호출 반복→T3부터 실제 native 실행. 성공한 경우에만 후속 대화/실제 구축/검토/사용/충돌/철회를 진행. UNKNOWN은 해당 제공자 셀 격리; 다른 사전 선언 셀은 독립 실행. 자원 중단은 전체 중단.'),('데이터·모델·재현성','Qwen3.8 qwen/qwen3.8-27b, 추론none, 출력상한없음. 제공자fallback0. 공개 상법7bbe815ff43b6635, 로컬SQLite, MAIN146 포인터·528해시 유지. 공식 endpoint 메타데이터와 scoped policy/input/candidate/runtime/raw/generation/journal을 보존. Oracle연결·운영승인/게시·GENOS현장·메일0.'),('결과',details),('사례별 오류 분석',observations),('비용·지연·회수 규모',json.dumps(usage,ensure_ascii=False)),('해석','REKA의 T3~T5는 HTTP200이어도 CLARIFY여서 대화 성공이 아니다. 최초·보완 명령과 command-check를 보존했다. 구축 시험기는 HTTP200만으로 선행 성공을 판단한 제한이 있었고 AUTHOR: 단계명의 로컬 형식 오류로 송신 전 중단했다. 이는 제품 구축의 새 Qwen 실패로 세지 않는다. 실제 제공자 응답과 명령 실행을 구분한다. 문맥 전달·원문 검증·경로 전달만으로 답변/지식 사용 성공을 인정하지 않는다.'),('한계와 일반화 가능 범위',limits),('운영 결정·롤백 조건','후보와 원시 기록을 격리 보존, MAIN 승격0·제품 변경0. 제공자 안정성 또는 정밀도 우열 판단을 운영 정책에 반영하지 않는다.'),('재현 명령','.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1398/audit.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1398/ledger.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1398/finalize.py\n위 명령은 오프라인 감사다. 새 실제 호출은 새 ADR로 예약해야 하며 기존 UNKNOWN은 재전송하지 않는다.')]
(ADR/'README.md').write_text('---'+front+'---\n\n# '+report['title']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
for q in m['questions']:
 c=next(c for c in cells if c['provider']==q['case_id']);case=next(c for c in read(DES/'live-cases.json') if c['id']==q['case_id'])
 parts=[('실행 메타',f"{c['provider']} {c['precision']}, same frozen528 source, reasoningnone; first5 provider responses are historical fixtures, subsequent physicals actual."),('사용자 질문 원문','\n'.join(str(s['number'])+'. '+s['question'] for s in case['steps'])),('기준답변 — 채점 전용, 제품 입력 비공개','상법365② 매결산기, 365③ 필요시 소집. 기존 문맥/새 주제/조건 변경/재검토와 승인 지식의 정확한claim사용을 실제 원문·state·route와 대조한다. 기준답변 주입0.'),('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz; source-wire-audit.json. 실제 원문·권한·전달 대조.'),('제품 모델 호출 — run·arm별 실제 원문',f"artifacts/public-live/{c['provider']}-provider-matrix/raw, canonical, fixture, turn-*에 요청·응답·일부수신·영수증 보존."),('중간 LLM 호출 — router/compiler/verifier/repair','같은 셀 generations.json 및 knowledge/canonical. 미실행 단계는 성공으로 세지 않는다.'),('채점 호출과 반복 판정','새 채점모델0. 실제 원문/계약/원장 직접 대조. 각 제공자1회, 안정성 인증 없음.'),('사례 최종 판정',json.dumps(c,ensure_ascii=False,indent=2))]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(parts,1))+'\n')
(ADR/'실험/README.md').write_text('# 질문 및 실제 결과\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
print(json.dumps({'verdict':verdict,'usage':usage},ensure_ascii=False))
