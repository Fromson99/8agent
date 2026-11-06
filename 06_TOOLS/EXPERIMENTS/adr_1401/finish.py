"""Seal actual local cutover and native Qwen observations after workers exit."""
from common import *
import statistics,tarfile
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path']);baseline=read(DES/'baseline.json')
candidate=read(DES/'candidate-selected.json');assert active['generation']==147 and release['files']==candidate['selected_files']
assert all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
activation=read(ART/'main/activation.json');assert activation['active']==active
gold=read(ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json');assert gold['engine_files']==release['files'] and gold['engine_manifest_sha256']==sha(ROOT/active['manifest_path'])
audit=read(ART/'source-wire-audit.json');manual=read(ART/'manual-review.json');cases=[];calls=[];reviews=[];resources=[]
for case in read(DES/'live-cases.json'):
 b=ART/'public-live'/(case['id']+'-selected-scope-r3')
 if not (b/'result.json').exists():
  cases.append({'case_id':case['id'],'question':case['steps'][0]['question'],'executed':False,'reason':'Local resource guard stopped before first model call' if (b/'resource-stop.json').exists() else 'Declared global stop before this independent case'});continue
 r=read(b/'turn-1/result.json');response=read(b/'turn-1/response.json.gz')['body'];cs=read(b/'calls.json');calls.extend(cs)
 answer=response.get('answer') or {};text=answer.get('text','') if isinstance(answer,dict) else str(answer)
 rs=[]
 for p in sorted((b/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  v=read(p)['view']
  if v.get('contract_version')!='reason-decision-review-v1':continue
  op=p.with_name(p.name.replace('.json','-output.json'));out=read(op) if op.exists() else None
  rs.append({'case_id':case['id'],'stage':v['stage'],'source_stage':v['source_stage'],'input':str(p.relative_to(ROOT)),'input_sha256':sha(p),'output':out,'proposal':v['proposal'],'previous_rejections':v.get('previous_rejections',[])})
 reviews.extend(rs)
 cases.append({'case_id':case['id'],'question':case['steps'][0]['question'],'executed':True,'result':r,'answer':text,'reviews':len(rs),'repair':sum((x['output'] or {}).get('decision')=='REPAIR' for x in rs),'manual':manual['cases'][case['id']]})
 with gzip.open(b/'resource-samples.jsonl.gz','rt') as stream:samples=[json.loads(line) for line in stream]
 initial=read(b/'resource-baseline.json');samples=[initial]+samples
 resources.append({'case_id':case['id'],'minimum_available_gib':min(s['available'] for s in samples)/1024**3,'max_swap_growth_mib':max(s['swap_used']-initial['swap_used'] for s in samples)/1024**2,'peak_sample_rss_gib':max(s['rss'] for s in samples)/1024**3})
 a=next(x for x in audit['cells'] if x['case_id']==case['id']);assert a['budget_matches'] and not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches'))
 paths=[p for p in (b/'runtime').rglob('*') if p.is_file()];rows=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(paths)]
 hp=b/'runtime-files-sha256.json.gz'
 if hp.exists():assert read(hp)==rows
 else:write_raw_json(hp,rows)
 if not (b/'runtime-evidence.tar.gz').exists():
  with tarfile.open(b/'runtime-evidence.tar.gz','w:gz') as tar:
   for p in paths:tar.add(p,arcname=str(p.relative_to(b)),recursive=False)
put(ART/'review-observations.json',reviews);put(ART/'case-results.json',cases);put(ART/'resource-summary.json',resources)
unknown=[i for i,c in enumerate(calls) if c['status']=='unknown'];assert not unknown or unknown==[len(calls)-1]
usage={'physical_calls':len(calls),'normal':sum(c['status']=='responded' and c.get('http_status')==200 for c in calls),'unknown':len(unknown),'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),'reported_tokens':sum((c.get('usage') or {}).get('total_tokens',0) for c in calls),'common_reviews':len(reviews),'review_repair_count':sum((r['output'] or {}).get('decision')=='REPAIR' for r in reviews),'same_request_extra_calls':sum(c['result'].get('duplicate',{}).get('extra_model_calls',0) for c in cases if c['executed']),'sends_after_unknown':0,'response_replay':0,'grader_calls':0,'native_budget_reserved':sum(a['budget_reserved'] for a in audit['cells'])}
latency={'requests_seconds':{c['case_id']:c['result']['request_seconds'] for c in cases if c['executed']},'physical_model_seconds':sum(c['seconds'] for c in calls),'controlled_speed_comparison':False}
rows=['| 질문 | 실제 결과 | 시간 | 호출 | 공통 감시 |','|---|---|---:|---:|---:|']
for c in cases:
 if not c['executed']:rows.append(f"| {c['case_id']} {c['question']} | 미실행 | — | 0 | 0 |");continue
 r=c['result'];rows.append(f"| {c['case_id']} {c['question']} | HTTP{r['http_status']} / {r['status']} / 주장{r['claims']} | {r['request_seconds']:.3f}초 | {r['physical_calls']} | {c['reviews']}회/REPAIR {c['repair']} |")
details='\n'.join(rows)
verdict='로컬 MAIN147 반영 완료. 선택한 실제 Risk팀 질문의 답변·감시 성능은 별도 결과이며 전체 성공으로 인증하지 않는다.'
observations='\n\n'.join(c['case_id']+': '+c['manual']['monitor_assessment'] for c in cases if c['executed'])
limits='Risk팀 등록 질문 027·078·029는 question_only이며 정답 승인/holdout이 아니다. 문항별1회로 일반 탐지율·오거절률·성능 향상을 인증하지 않는다. 이유와 선택이 함께 틀린 의미 오류는 이 감시자의 일치 검사와 구분한다. 정상 반환/HTTP200을 답변 성공으로 세지 않는다. 선택 메인의 기본 온톨로지OFF를 그대로 사용했으므로 온톨로지 구축/비교/실사용 검증은 이번 실제 질문 범위 밖이다. 기본 감시 enforce, 원문·권한·형식 검증과 선택형 추가 LLM 검토의 기존 설정을 유지했다.'
environment='MAIN147 / reason-decision-review-20261105-r1; 완료1399와 정확히 같은530파일, MAIN146대비58변경·실행SQL640동일. 실제 ROOT service.py→선택 릴리스→/v1/rag/ask. Qwen3.8 Parasail FP8/추론none·출력상한 없음, 확정429만 기존 NearAI1회 전환 규칙. 로컬 원문 SQLite·Risk팀 공개 교집합28문서·격리 실행DB. 원래 질문 그대로 외규 모드에서 실행, 기준답변/근거 후보 주입0.'
cutover={'active':active,'files':530,'changed':58,'candidate_tests':69,'prepared_tests':69,'unique_contract_tests':69,'root_service_checks':23,'gold_loader_checks':9,'executable_sql':640,'quality_certified':False,'deployment_basis':'USER_DIRECTED_CUTOVER','rollback_manifest':baseline['pointer']['manifest_path'],'rollback_gold':activation['old_gold_binding'],'genos_deployed':False}
errors={'preparation_scope_denial_before_model':1,'observer_preflight_normalization_error':1,'unknown':len(unknown),'confirmed_reason_decision_misses':sum(c['manual'].get('known_missed_conflicts',0) for c in cases if c['executed']),'observed_false_rejections':sum(c['manual'].get('observed_false_rejections',0) for c in cases if c['executed'])}
report={'verdict':verdict,'cutover':cutover,'details':details,'observations':observations,'limits':limits,'environment':environment,'usage':usage,'latency':latency,'error_taxonomy':errors,'cases':cases}
put(ART/'result.json',report)
(ART/'메인반영과_실제질문_결과.txt').write_text(verdict+'\n\n'+environment+'\n\n'+details+'\n\n'+observations+'\n\n'+limits+'\n\n'+json.dumps({'usage':usage,'latency':latency,'resources':resources,'cutover':cutover},ensure_ascii=False,indent=2)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'selected':report},comparisons=[],judge_disagreements=0,usage=usage,latency=latency,error_taxonomy=errors);put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1].replace('main_wiring: unchanged','main_wiring: user-directed-cutover')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
contents=[verdict,'MAIN146에는 공통 감시가 선택되지 않았다. 사용자 지시로 이전1399 시험 코드와 알려진 한 글자 진단/모순 누락을 보존해 선택하고 실제 등록 질문으로 확인했다. 별도1400 진행 수정과 작업 파일을 덮어쓰지 않았다.',json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'69계약→같은 준비릴리스69계약→공식 apply→기본서비스23/Gold9→세 질문 순차 실제 실행. 최초 범위65의 팀권한 거절422와 정규화 이전 관측검사 실패를 새 모델0에서 보존/정정, 실제28문서로 실행했다.',environment,details,observations,json.dumps({'usage':usage,'latency':latency,'resources':resources},ensure_ascii=False),'반영 완료와 답변 성공·감시 효과를 구분한다. [실제 결과](artifacts/메인반영과_실제질문_결과.txt)·[문항별 검토](artifacts/manual-review.json)·[공통 감시 원기록](artifacts/review-observations.json).',limits,'사용자 지시 USER_DIRECTED_CUTOVER, quality_certified=false. 이전 MAIN146과 Gold 원본 바이트를 함께 원복할 수 있다. GENOS 현장·운영DB·메일0. 의미 실패를 구조적 릴리스 실패로 바꿔 자동 원복하지 않는다.','adr_1401/setup.py→check.py→prepare.py→준비본 check.py→activate.py→live.py(각 사례1회)→audit.py→ledger.py→finish.py. 실제 반복·수정 후 평가에는 새 ADR을 사용한다.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 공통 감시 MAIN147 반영과 실제 Risk 질문\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,contents),1))+'\n')
index=[]
for q in m['questions']:
 c=next((c for c in cases if c['case_id']==q['case_id']),None)
 question=c['question'] if c else read(DES/'criteria.json')['authorization']
 outcome=json.dumps(c if c else cutover,ensure_ascii=False,indent=2)
 parts=[('실행 메타',environment),('사용자 질문 원문',question),('기준답변 — 채점 전용, 제품 입력 비공개','등록 질문은 question_only. 독립 승인 정답률 없음; 실제 원문과 이유/판단/기록 직접 대조. 제품 입력에는 질문과 실제 허용 문서만 전달.'),('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz, source-wire-audit.json, design/live-cases.json과 각 public-live의 binding/scope-selection 참조.'),('제품 모델 호출 — run·arm별 실제 원문','artifacts/public-live/'+q['case_id']+'-selected-scope-r3/raw 및 canonical. 입출력 무손실 gzip·각 해시 참조. main-cutover 외부모델0.'),('중간 LLM 호출 — router/compiler/verifier/repair','artifacts/review-observations.json과 각 generations.json에 공통 감시와 기존 구조 보완을 구분해 기록.'),('채점 호출과 반복 판정','추가 채점 모델0. 같은 요청 ID 중복 결과와 물리 호출0을 확인. 과거 실패/준비오류 보존.'),('사례 최종 판정',outcome)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(parts,1))+'\n');index.append(f"- [{q['case_id']}]({q['file']})")
(ADR/'실험/README.md').write_text('# 실제 결과\n\n'+'\n'.join(index)+'\n')
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'};paths.update(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1401','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Local selected MAIN, raw actual Qwen, preserved preparation error or read-only audit','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts)} for p in sorted(paths)]})
print(json.dumps({'main':active['generation'],'usage':usage,'cases':[(c['case_id'],c.get('result',{}).get('claims')) for c in cases]},ensure_ascii=False))
