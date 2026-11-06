"""Read-only interpretation of frozen live observations; no new model calls."""
from common import *
import re, statistics, tarfile

candidate=read(DES/'candidate-repaired.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/candidate['code_root']/n)==h for n,h in candidate['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
probe=ART/'probes';native=ART/'public-live/public-native-common-review'
cases=read(DES/'probe-cases.json');results=read(probe/'results.json');repairs=read(probe/'repairs.json')
pcalls=read(probe/'calls.json');ncalls=read(native/'calls.json');calls=pcalls+ncalls
audit=read(ART/'source-wire-audit.json')['cells'][0]
manual=read(ART/'manual-review.json')
assert not any(audit[k] for k in ('source_mismatches','acl_violations','wire_mismatches'))
assert audit['budget_matches']
unknown=[i for i,c in enumerate(calls) if c['status']=='unknown']
assert not unknown or unknown==[len(calls)-1]
nr=read(native/'turn-1/result.json');response=read(native/'turn-1/response.json.gz')['body']
answer=response.get('answer') or {};answer_text=answer.get('text','') if isinstance(answer,dict) else str(answer)
checks=[]
for row in results:
 case=next(c for c in cases if c['id']==row['case_id']);decision=row.get('receipt',{}).get('decision',{})
 checks.append({'case_id':row['case_id'],'group':case['group'],'decision':decision,'proposal':case['proposal'],
                'semantic_review':manual['probe'][row['case_id']],
                'reconsideration':next((r for r in repairs if r['case_id']==row['case_id']),None)})
put(ART/'case-audit.json',checks)
usage={'physical_calls':len(calls),'probe_calls':len(pcalls),'native_calls':len(ncalls),
 'normal':sum(c.get('http_status')==200 and c['status']=='responded' for c in calls),
 'unknown':len(unknown),'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),
 'reported_tokens':sum((c.get('usage') or {}).get('total_tokens',0) for c in calls),
 'unknown_unreported_cost':None if unknown else 0,'native_model_budget_reserved':audit['budget_reserved'],
 'same_proposal_or_request_extra_calls':sum(r.get('duplicate_extra_calls',0) for r in results+repairs)+(nr.get('duplicate') or {}).get('extra_model_calls',0),
 'response_replay':0,'sends_after_unknown':0,'grader_model_calls':0}
resources=[]
for base in (probe,native):
 with gzip.open(base/'resource-samples.jsonl.gz','rt') as f:samples=[json.loads(line) for line in f]
 start=read(base/'resource-baseline.json');samples=[start]+samples
 resources.append({'cell':base.name,'minimum_available_gib':min(s['available'] for s in samples)/1024**3,
 'max_swap_growth_mib':max(s['swap_used']-start['swap_used'] for s in samples)/1024**2,
 'peak_sample_rss_gib':max(s['rss'] for s in samples)/1024**3,'samples':len(samples)})
put(ART/'resources-audit.json',{'cells':resources,'background_experiment_overlap':True,
 'note':'Independent ADR1398 native worker was observed concurrently. ADR1399 ran one worker at a time with its frozen resource guard. Latency is not a controlled provider or speed comparison.'})
latency={'initial_probe_seconds':[r['seconds'] for r in results],
 'primary_plus_rereview_seconds':[r['seconds'] for r in repairs if 'seconds' in r],
 'native_request_seconds':nr['request_seconds'],'all_physical_seconds':sum(c.get('seconds',0) for c in calls),
 'population_p95':None,'controlled_speed_comparison':False}
for base in (probe,native):
 paths=list((base/'runtime').rglob('*')) if (base/'runtime').exists() else list(base.glob('case-*/*.sqlite'))
 rows=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(paths) if p.is_file()]
 rp=base/'runtime-files-sha256.json.gz'
 if rp.exists():assert read(rp)==rows
 else:write_raw_json(rp,rows)
 if not (base/'runtime-evidence.tar.gz').exists():
  with tarfile.open(base/'runtime-evidence.tar.gz','w:gz') as archive:
   for r in rows:archive.add(ROOT/r['path'],arcname=str((ROOT/r['path']).relative_to(base)),recursive=False)
put(ART/'code-integrity.json',{'candidate_files':len(candidate['selected_files']),
 'candidate_unchanged':True,'working_tree_differences_from_frozen':[n for n,h in candidate['selected_files'].items() if sha(ROOT/n)!=h],
 'main_pointer_unchanged':True,'selected_main_files_unchanged':all(sha(ROOT/baseline['release']['code_root']/n)==v for n,v in baseline['release']['files'].items()),
 'product_edits_by_this_experiment':0})
details='| 항목 | 실제 결과 |\n|---|---|\n| 사전 모순 5건 | REPAIR 4, 잘못된 PASS 1 |\n| 정상 대조 7건 | PASS 7, 오거절 0 |\n| 모순 진단 설명 | REPAIR 4건의 5개 issue 모두 한 글자 설명·인용; 의미 있는 진단 0/4 |\n| 원래 Qwen 재판단 | 검출된 4건 모두 실제 행동/상태/사용 기록 변경, 재검토 PASS와 작업 저널 수락 |\n| 놓친 충돌 1건 | 보완 미실행; 온톨로지 저장 미실행 |\n| 실제 공개 RAG | '+manual['native']['summary']+' |'
verdict='공통 감시의 실제 Qwen 시험은 전체 미통과다. 사전 모순 5건 중 4건 검출·정상 7건 통과지만, 온톨로지 충돌 1건을 놓치고 진단 설명이 한 글자로 나왔다. 실제 RAG에서도 답변은 원문과 맞았으나 요구 상태 모순 1건을 통과시켜 저장했다.'
observations=(
 'case-09는 기존 지식과 충돌한다는 동일한 이유에 relation=SAME/verdict=SUPPORTED를 제출했지만 PASS였다. 정상 case-04의 CONTRADICTION/SUPPORTED는 PASS이므로 두 비교 축을 구분하는 정상 대조는 유지했다.\n\n'
 '검출 4건은 실제 필드를 가리켰지만 reason_quote가 목/핵/승/S, explanation이 모두 이였다. 이 응답을 현행 서버 검증이 수락했다. case-07은 실제 모순인 action=FINISH 외에 이유와 일치하는 sufficiency=NEEDS_SOURCE도 지적했다. 모순 여부 4/5와 유용한 진단 성공을 혼동하지 않는다.\n\n'
 '전송 원문에서 reason_quote/explanation에는 pattern=\\S가 있고 두 필드 모두 한 글자였다. 여러 글자인 pointer와 보완 본문은 정상 수신됐다. 스키마/공급자 문법 처리의 영향은 후속 가설이며, 이번 시험만으로 원인을 확정하지 않는다. 제품·프롬프트·스키마를 고치고 같은 시험을 통과로 덮어쓰지 않았다.\n\n'
 '보완은 CONTINUE+G1, INSUFFICIENT+확정불가, P1/N1→C1 사용 기록, READ+S2로 실제 변경됐다. 이유만 바꾼 사례는 없다. 기존 bounded_decision과 실제 WorkRepository 이벤트로 수락을 확인했지만, 합성 probe에서 실제 원문 도구 실행이나 온톨로지 저장까지 수행한 것은 아니다.\n\n'+manual['native']['detail'])
limits='각 사례 독립1회, 합성 모순5/정상7과 공개 원문 native1의 인샘플 probe다. 자연 발생 오류 빈도·일반 탐지율/오거절률·법률 정답률·반복 안정성·속도 개선을 인증하지 않는다. 정상 7건에는 부분 답변, 경로 미사용, 다음 평가 단계로 이관, 원문 지지/기존 지식 충돌의 서로 다른 축이 포함된다. 실제 온톨로지 생성·비교·게시·사용의 전체 수명과 후속 대화는 이번 native 시험 범위 밖이다. 기본 원문/권한/형식/법률 검증은 유지했다.'
environment='2026-11-05. 공통 감시 및 병행 멀티턴 작업 코드530파일 동결, Qwen3.8(qwen/qwen3.8-27b) Parasail FP8/추론none·temperature0, 출력 상한 없음. 제공자 목록1개로 실제 전환0. 공개 상법7bbe815ff43b6635/선택 원문 SQLite, 온톨로지ON·초기 빈 격리DB. 실물 모델 호출은 모두 새 응답이며 모의 최초 제안12건은 사전 선언한 시험 자극이다.'
release='제품 변경·선택 MAIN146 변경·운영 지식 승인/게시·GENOS 배포·메일0. 신규 실험 실행기 import 누락은 외부 호출 전 수정하고 준비 실패를 보존했다. 실제 결과를 본 뒤 제품/runner/동결 사례 수정0. 실험 상태 completed는 측정·기록 완료이며 기능 성공/운영 채택을 뜻하지 않는다.'
errors={'seeded_missed_conflict':1,'native_organic_missed_conflict':1,'native_stale_read_reason_observation':1,'initial_normal_false_rejection':0,'unusable_repair_diagnosis':4,
 'extra_noncontradictory_issue':1,'unknown':len(unknown),'source_mismatch':len(audit['source_mismatches']),
 'acl_violation':len(audit['acl_violations']),'wire_mismatch':len(audit['wire_mismatches'])}
report={'verdict':verdict,'details':details,'observations':observations,'limits':limits,'environment':environment,
 'release':release,'usage':usage,'latency':latency,'error_taxonomy':errors,'native':nr,'native_manual_review':manual['native']}
put(ART/'final-review.json',report);put(RUN/'result.json',report)
(ART/'실제_Qwen_결과.txt').write_text(verdict+'\n\n'+details+'\n\n'+observations+'\n\n'+environment+'\n\n'+limits+'\n\n'+release+'\n\n'+json.dumps({'usage':usage,'latency':latency,'resources':resources},ensure_ascii=False,indent=2)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['dataset'].update(legal_version_checked=True,reference_version_checked=True)
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'executed':False},'common-review':report},comparisons=[],judge_disagreements=0,usage=usage,latency=latency,error_taxonomy=errors)
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
sections=[('결정 요약',verdict),('문제와 변경 전 구조','모의 계약 검사는 공통 감시와 원래 LLM 보완 연결을 확인했으나 새 실제 Qwen 의미 탐지/진단 품질은 미측정이었다. 작업 코드와 선택 MAIN146은 별개다.'),
 ('가설과 사전 판정 기준',json.dumps(read(DES/'criteria.json'),ensure_ascii=False)),
 ('실험 설계','고정12건→검출된 사전 모순의 원래 담당 재판단→native API1. 최종 판단·기준답변은 감시자에 주입하지 않는다. 합성 최초 제안과 실제 보완/감시 응답을 구분한다. UNKNOWN 후 모든 추가 송신 중단.'),
 ('데이터·모델·재현성',environment),('결과',details),('사례별 오류 분석',observations),('비용·지연·회수 규모',json.dumps({'usage':usage,'latency':latency,'resources':resources},ensure_ascii=False)),
 ('해석','검출 후 원래 모델 보완 연결은 관측했으나, 누락과 진단 설명 결함 때문에 사용자 완료 기준 미충족. 상세 근거는 [실제 결과](artifacts/실제_Qwen_결과.txt)와 [검토 기록](artifacts/manual-review.json)에 보존한다.'),
 ('한계와 일반화 가능 범위',limits),('운영 결정·롤백 조건',release),
 ('재현 명령','.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1399/audit.py\n\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1399/finalize.py\n\n위는 저장 자료의 읽기 전용 재분석이다. 실제 모델 재실행/수정 가설 시험은 새 ADR에서 수행하며 기존 원응답을 덮어쓰지 않는다.')]
(ADR/'README.md').write_text('---'+front+'---\n\n# 공통 판단 이유–실제 판단 감시 Qwen 실험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
index=[]
for q in m['questions']:
 selected_cases=[c for c in cases if c['group']==q['case_id']];actual=[r for r in checks if r['group']==q['case_id']]
 is_native=q['case_id']=='public-native'
 question=read(DES/'live-cases.json')[0]['steps'][0]['question'] if is_native else '\n\n'.join(c['id']+': '+str(c['context'].get('request',c['context'].get('new_judgment',c['context'].get('current_request','현재 제안의 이유와 판단 일치 검사')))) for c in selected_cases)+'\n\n전체 원문 context·proposal·schema는 [동결 입력](../artifacts/design/probe-cases.json)의 해당 case id를 참조한다. 값/해시를 변경하지 않았다.'
 raw='artifacts/public-live/public-native-common-review/raw·canonical·turn-1 및 runtime 저널' if is_native else 'artifacts/probes/raw·canonical 및 case-NN/journal.sqlite. case-audit.json으로 물리 호출과 제안을 대조한다.'
 outcome=json.dumps({'result':nr,'manual':manual['native'],'answer':answer_text},ensure_ascii=False,indent=2) if is_native else json.dumps([{k:r[k] for k in ('case_id','decision','semantic_review','reconsideration')} for r in actual],ensure_ascii=False,indent=2)
 parts=[('실행 메타',environment),('사용자 질문 원문',question),('기준답변 — 채점 전용, 제품 입력 비공개','artifacts/design/offline-expectations.json과 manual-review.json. 합성 원문/현재 사실에서 이유와 행동 일치만 판정하며 native는 저장된 제365조 제2항 원문과 대조한다.'),
 ('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz·source-wire-audit.json 참조. 합성6그룹은 RAG 미실행, 공개 native1만 실제 회수/전달 측정.'),
 ('제품 모델 호출 — run·arm별 실제 원문',raw),('중간 LLM 호출 — router/compiler/verifier/repair',raw),('채점 호출과 반복 판정','추가 채점 모델0. 보존한 원응답/원문/구조 검증과 실제 필드 변경을 직접 확인. 법률 정답과 감시 일치를 혼동하지 않는다.'),('사례 최종 판정',outcome)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(parts,1))+'\n');index.append(f"- [{q['case_id']}]({q['file']})")
(ADR/'실험/README.md').write_text('# 질문 및 실제 결과\n\n'+'\n'.join(index)+'\n')
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'};paths.update(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1399','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input, actual Qwen transport/API/journal, preparation failure, or read-only audit','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts)} for p in sorted(paths)]})
print(json.dumps({'verdict':verdict,'usage':usage},ensure_ascii=False))
