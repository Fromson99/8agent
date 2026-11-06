"""Read-only final interpretation, then seal the ADR's actual observations."""
from common import *
import re,json,statistics,sqlite3
base=ART/'public-live/conversation-verified-lifecycle'
measured=read(base/'result.json');calls=read(base/'calls.json');audit=read(ART/'source-wire-audit.json')['cells'][0]
case=read(DES/'live-cases.json')[0];candidate=read(DES/'candidate-repaired.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/candidate['code_root']/n)==h for n,h in candidate['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
assert not any(audit[k] for k in ('source_mismatches','acl_violations','wire_mismatches'))
assert audit['budget_matches']
turns=[]
for step in case['steps']:
 p=base/('turn-'+str(step['number']))
 if not (p/'result.json').exists():turns.append({'number':step['number'],'question':step['question'],'executed':False,'reason':'Earlier declared failure or unmet dependency gate'});continue
 r=read(p/'result.json');v=read(p/'response.json.gz')['body'];a=v.get('answer') or {};text=a.get('text','') if isinstance(a,dict) else str(a)
 turns.append({'number':step['number'],'question':step['question'],'executed':True,'http_status':r['http_status'],'goal_id':r['goal_id'],'revision':r['revision'],'method':r['method'],'stages':r['executed'],'seconds':r['request_seconds'],'physical_calls':r['physical_calls'],'unknown':r['unknown'],'claims':r['claims'],'answer':text,'duplicate':r.get('duplicate'),'review':v.get('assembly',{}).get('term_agent',{}).get('review_explanation')})
first=turns[0];repeat=turns[1]
same=False
if first['http_status']==200 and repeat.get('http_status')==200:
 v1=read(base/'turn-1/response.json.gz')['body'];v2=read(base/'turn-2/response.json.gz')['body']
 # A new native request legitimately has new answer/query IDs. Compare every
 # other answer field exactly; never normalize originals, claims or conclusions.
 ignored={'id','query_id'}
 same=(all(v1.get(k)==v2.get(k) for k in ('goal_id','question_id','revision')) and
       {k:v for k,v in v1['answer'].items() if k not in ignored}==
       {k:v for k,v in v2['answer'].items() if k not in ignored})
 put(ART/'repeat-equivalence.json',{'same_goal_revision_and_substantive_answer':same,
     'all_claims_evidence_and_text_exact':same,'fresh_request_identity_fields':{
         k:{'first':v1['answer'].get(k),'repeat':v2['answer'].get(k)} for k in ignored},
     'raw_responses_modified':False,'new_physical_calls':repeat['physical_calls']})
 assert same and repeat['physical_calls']==0 and repeat['stages']==[]
last_unknown=next((i for i,c in enumerate(calls) if c['status']=='unknown'),None)
assert last_unknown is None or last_unknown==len(calls)-1
usage={'physical_calls':len(calls),'normal':sum(c.get('http_status')==200 and c['status']=='responded' for c in calls),'known_rejections':sum(c.get('http_status')!=200 and c['status']=='responded' for c in calls),'unknown':sum(c['status']=='unknown' for c in calls),'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),'reported_tokens':sum((c.get('usage') or {}).get('total_tokens',0) for c in calls),'unknown_cost_reported':None if last_unknown is not None else 0,'budget_reserved':audit['budget_reserved'],'same_request_id_extra_calls':sum((t.get('duplicate') or {}).get('extra_model_calls',0) for t in turns),'sends_after_unknown':0,'response_replay':0,'grader_model_calls':0}
latency={'first_turn_seconds':first['seconds'],'repeat_seconds':repeat.get('seconds'),'followup_seconds':turns[2].get('seconds'),'all_physical_model_seconds':sum(c.get('seconds',0) for c in calls),'population_p95':'not estimated from this one conversation'}
put(ART/'turn-audit.json',{'turns':turns,'usage':usage,'same_literal_repeat':same})
rows=['| 턴 | 질문/행동 | 실제 결과 | 초 | 새 모델 호출 |','|---|---|---|---:|---:|']
for t in turns:
 if not t['executed']:rows.append(f"| {t['number']} | {t['question']} | 미실행 | — | 0 |");continue
 status='답변' if t['claims'] else '원문/안내' if t['http_status']==200 else 'UNKNOWN/실패'
 rows.append(f"| {t['number']} | {t['question']} | HTTP{t['http_status']} · {status} | {t['seconds']:.3f} | {t['physical_calls']} |")
details='\n'.join(rows)
meaning='첫 턴부터 새 실제 Qwen이며, 저장 응답 재생은 0회다. 같은 문장·현행 상태의 반복은 기존 검증 답변을 모델 없이 재표시했다.'
if usage['unknown']:
 verdict='실제 첫 답변과 무호출 반복은 통과. 암묵적 후속 질문에서 외부 명령 선택 응답이 미완료되어 전체 멀티턴/지식 수명 시험은 미통과.'
else:verdict='실제 Qwen의 단계별 결과를 원문·주장 사용 기록으로 확인했다. 전체 성공 여부와 실행 범위는 아래 표를 따른다.'
observations=[]
if usage['unknown']:
 c=calls[last_unknown];observations.append('마지막 미확정 물리 호출은 '+str(c['stage'])+'이다. 수신/회수 진단: '+json.dumps(c.get('transport_diagnostics',{}),ensure_ascii=False)+'. 원격 완료·취소·미보고 비용과 공급자 내부 원인은 확인하지 못했다. 원응답을 재전송하지 않았다.')
# The actual command input provides continuity evidence, not a legal truth claim.
inputs=[]
for p in sorted((base/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 v=read(p)
 if v.get('view',{}).get('source_stage')=='memory-resolve':
  view=v['view'];inputs.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'utterance':view.get('utterance'), 'prior_goal_ids':[g.get('id') for g in view.get('goals',[])],'prior_response_present':any(g.get('previous_response',{}).get('text') for g in view.get('goals',[])),'literal_repeat_target':view.get('literal_repeat_target')})
put(ART/'continuity-input-check.json',inputs)
observations.append('대화 문맥 입력 확인: '+json.dumps(inputs,ensure_ascii=False)+'. 응답을 받기 전에는 어떤 명령을 선택했는지 추정하지 않는다.')
knowledge={'build_attempted':(base/'knowledge/generations.json').exists(),'compiled':(base/'knowledge/compiled.json.gz').exists(),'published':(base/'knowledge/publication.json').exists(),'actual_usage':read(base/'knowledge/actual-usage.json') if (base/'knowledge/actual-usage.json').exists() else None,'conflict':read(base/'knowledge/conflict.json') if (base/'knowledge/conflict.json').exists() else None,'withdrawal':(base/'knowledge/withdrawal.json').exists()}
put(ART/'knowledge-result.json',knowledge)
observations.append('지식 단계 실행 여부: '+json.dumps(knowledge,ensure_ascii=False)+'. 선행 대화 실패 때문에 시작하지 않은 단계는 성공 또는 새 모델 실패로 세지 않는다.')
limits='공개 상법 한 문서·동일 대화 한 번의 인샘플 probe다. 이후 계획 턴/구축/사용/충돌/철회가 미실행이면 이번 결과로 해당 기능의 실모델 성공을 주장하지 않는다. 기준답변은 제품에 주입하지 않았고 오프라인 원문 대조에만 사용했다. FIRST 실제 답변은 상법 제365조 제2항의 매기 소집과 대조했다. 반복이 빨라진 것은 검증된 저장 답변의 재표시이며, 일반 RAG/모델 속도 향상·제공자 안정성·법률 정답률 인증은 아니다.'
report={'title':'멀티턴·지식 수명 수정본 Qwen 실제 시험','verdict':verdict,'context':'앞선 일반 구현은 고정 코드70계약과 로컬 API 대역을 통과했다. 사용자 요청으로 그 정확한 범위의 코드를 공식 ADR candidate로 동결하고 첫 질문부터 실제 Qwen으로 실행했다. 현재 공유 트리의 병행 공통 감시자/구축 변경은 이 후보에 섞지 않았다.',
 'design':'같은 native API 대화에서 최초→같은 문구 반복→암묵적 후속→새 주제→조건 변경→재검토. 모두 완료한 경우에만 실제 T1 불변 원문/판단을 구축하고 별도 실험용 검토·승인 뒤 같은 대화에서 실제 claim 사용 및 충돌/철회 재검토를 실행하도록 사전 동결했다. UNKNOWN 뒤는 전역 송신 중단이다.',
 'environment':'2026-11-05, 후보528파일·고정70계약 수정본·공개 상법7bbe815ff43b6635/로컬 SQLite·Qwen3.8(qwen/qwen3.8-27b), Parasail FP8 우선/추론none/출력 상한 없음. 확정429만 NearAI1회 전환 허용. DB 온톨로지는 빈 격리 저장소에서 시작. 원문/운영 DB·MAIN146/Gold·GENOS 변경0.',
 'details':details,'observations':'\n\n'.join(observations),'meaning':meaning,'limits':limits,
 'release':'제품 추가 수정0. 선택 MAIN146 포인터 및528파일 보존. 실제 운영 지식 승인/게시·GENOS 현장배포·메일0. 후보는 격리 상태로 보존한다.',
 'commands':'.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1397/audit.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1397/finalize.py\n실제 live 재실행은 새 ADR이 필요하며 기존 UNKNOWN을 다시 보내지 않는다.',
 'usage':usage,'latency':latency,'error_taxonomy':{'remote_incomplete_outcome':usage['unknown'],'source_mismatch':len(audit['source_mismatches']),'acl_violation':len(audit['acl_violations']),'wire_mismatch':len(audit['wire_mismatches']),'unexecuted_planned_turns':sum(not t['executed'] for t in turns),'organic_ontology_conflict_observed':False},
 'cases':{'conversation':{'questions':'\n'.join(str(s['number'])+'. '+s['question'] for s in case['steps']), 'expected':'소집 시기는 원문 제365조제2항의 매기/제3항의 필요시와 대조. 의결권은 제369조제1항 1주1개와 실제 새 사실/예외를 대조. 같은 대화·새 주제·조건 변경·검토 대상은 실제 goal/revision/원문과 대조한다. 기준답변은 제품 입력에 전달하지 않는다.','raw':'artifacts/public-live/conversation-verified-lifecycle/raw 및 canonical의 무손실 원시 요청/응답, turn별 API 응답과 실제 사용자 본문을 참조. '+str(base.relative_to(ROOT)), 'result':details},
 'knowledge-reuse':{'questions':'실제 첫 판단 축적 → 승인 지식의 경로/노드/claim 실제 사용 → 명시 반례 비교 → 게시 철회 후 같은 질문 재검토', 'expected':'문장·원문·관찰 이력을 보존하고 실제 claim 사용과 승인 상태를 구분한다. 명시 반례는 사전 선언한 시험 입력이며 자연 발생 Qwen 오판이 아니다. 기대 상태를 모델 입력으로 주입하지 않는다.','raw':'artifacts/knowledge-result.json; 실행한 경우 knowledge/canonical·compiled·publication·conflict·withdrawal 영수증을 참조.', 'result':json.dumps(knowledge,ensure_ascii=False)}}}
put(ART/'final-review.json',report)
(ART/'실제_Qwen_결과.txt').write_text(verdict+'\n\n'+details+'\n\n'+report['observations']+'\n\n'+limits+'\n\n'+json.dumps({'usage':usage,'latency':latency},ensure_ascii=False,indent=2)+'\n')
put(RUN/'result.json',{k:report[k] for k in ('verdict','details','observations','limits','usage','latency','error_taxonomy')})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'verified-lifecycle':read(RUN/'result.json')},comparisons=[],judge_disagreements=0,usage=usage,latency=latency,error_taxonomy=report['error_taxonomy']);put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
sections=[('결정 요약',verdict),('문제와 변경 전 구조',report['context']),('가설과 사전 판정 기준',json.dumps(read(DES/'criteria.json'),ensure_ascii=False)),('실험 설계',report['design']),('데이터·모델·재현성',report['environment']),('결과',details),('사례별 오류 분석',report['observations']),('비용·지연·회수 규모',json.dumps({'usage':usage,'latency':latency},ensure_ascii=False)),('해석',meaning),('한계와 일반화 가능 범위',limits),('운영 결정·롤백 조건',report['release']),('재현 명령',report['commands'])]
(ADR/'README.md').write_text('---'+front+'---\n\n# '+report['title']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
index=[]
for q in m['questions']:
 d=report['cases'][q['case_id']];parts=[('실행 메타',report['environment']),('사용자 질문 원문',d['questions']),('기준답변 — 채점 전용, 제품 입력 비공개',d['expected']),('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz 및 source-wire-audit.json 참조.'),('제품 모델 호출 — run·arm별 실제 원문',d['raw']),('중간 LLM 호출 — router/compiler/verifier/repair',d['raw']),('채점 호출과 반복 판정','새 채점 모델0. 원문과 실제 응답·상태·저널·물리 전송을 직접 대조했다.'),('사례 최종 판정',d['result'])]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(parts,1))+'\n');index.append(f"- [{q['case_id']}]({q['file']})")
(ADR/'실험/README.md').write_text('# 질문 및 실제 결과\n\n'+'\n'.join(index)+'\n')
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'};paths.update(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1397','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen source, actual Qwen raw/API/journal or audit evidence','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts)} for p in sorted(paths)]})
print(json.dumps({'verdict':verdict,'usage':usage,'latency':latency},ensure_ascii=False))
