from pathlib import Path
import json,hashlib,gzip
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1235-gold-ontology-transport-live';D=A/'artifacts/design';O=A/'artifacts/run-001';P=O/'live/gold-369';U=R/'09_ARTIFACTS/AUDITS/20261030-gold-ontology-on'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(P/'result.json');a=read(P/'audit.json');e=read(O/'ontology-e2e.json');f=read(D/'freeze.json');same={p:sha(R/p)==h for p,h in f['files'].items()};assert all(same.values());put(O/'post-run-integrity.json',same)
with gzip.open(P/'audit-detail.json.gz','rt') as fp:detail=json.load(fp)
failures=[{'kind':x['kind'],'payload':x['payload']} for x in detail['events'] if 'REJECT' in x['kind'] or 'FAILED' in x['kind']]
provider_switches=sum(x['kind']=='MODEL_PROVIDER_STATE' for x in detail['events']);calls=read(P/'calls.json');complete=all(e['gates'].values())
result={'status':e['status'],'actual':r,'audit':a,'ontology':e,'provider_switches':provider_switches,'failure_events':failures,'integrity_unchanged':True,'connector':'ON/DB; two local runtime compatibility patches installed in ADR1234','main_promoted':False,'quality_certified':False,'protocol_deviation':{'declared':'UNKNOWN ends run','observed':'Supervisor call7 UNKNOWN was caught by native handoff; calls8/9 ASSESS and repair executed before driver ended. Same supervisor request was not retried, but the intended stop rule was not enforced.','after_unknown_calls':2,'further_runs':0}};put(O/'result.json',result)
conclusion='알려진 공개질문1건에서 실제 전체 연결을 확인했다.' if complete else '실제 전체 추론은 여전히 미통과다.'
report=f'''골드 온톨로지 ON 최종 확인 — 2026-10-30 / ADR1235

결론: 골드 연결기는 ON/DB로 반영됐다. {conclusion}
현재 Oracle: ACTIVE_MAPPING.json → mapping_local_dtls_current.json,13테이블/60컬럼.
기존 게시3건(상법365·368·369조) 유지. 이번질문은369조 게시물1건에 대한 기능검증이다.
질문: 상법 제369조에 따른 1주당 의결권 수와 자기주식·주식 상호보유의 의결권 제한은 어떻게 되나요?

직접 중단 원인: 최종 최초/보완 모두 NEED_TARGET_INCOMPLETE. 모델이 선언한 조사 필요를 RESOLVED로 처리했으나 대상 원문 전체와 결속되지 않았다.
원문이 있는341조의3의 필수근거 일부를 연결하지 않았고, 미확보 목표를 해결 처리한 항목도 있었다. 정규화된 제369조 C1/C2/C3 초안 자체는 서로다른 ID와 올바른 원문refs를 유지했으나 최종승인은 거절됐다.
감독7번째 호출은HTTP200헤더/공백60조각660바이트 후179.921초 기한종료 UNKNOWN이었다.
사전UNKNOWN종료기준이 실제native감독인계에서 강제되지 않아 최종8/보완9 두호출이 추가진행됐다. 같은UNKNOWN요청 재시도는 아니지만 중단규칙 이탈이며 기록상실패로 판정한다. 이 run 후 새실모델0.

실제 최종 실행
- 시간 {r['seconds']:.3f}초 / SQL {r['sql_calls']:,}회 / 모델 물리 {r['model_calls']}회 / 도구 {a['tool_actions']}회.
- 모델대기 {a['model_seconds']:.3f}초, 기타 {a['other_seconds']:.3f}초. 기타를 순수SQL시간으로 해석하지 않는다.
- HTTP {r.get('http_status')} / 실행 {r.get('status')} / 최종답변 {e['answer_chars']}자.
- 공급자 {a['provider_counts']}, HTTP {a['http_counts']}, finish {a['finish_reason_counts']}.
- 정책상확인429전환 {provider_switches}회, UNKNOWN {r['unknown']}, 자원중단 {a['resource']['stop']}, swap증가 {a['resource']['max_host_swap_growth_MiB']}MiB.
- 보고비용 ${a['reported_cost_usd']:.8f}; 토큰 입력 {a['input_tokens']:,}/출력 {a['output_tokens']:,}. 미보고요청비용은0원으로 단정하지 않는다.
- 원문대조: 확보{a['source_checks']}/중첩입력{a['nested_view_checks']}/평면최종{a['flat_view_checks']}, 불일치{len(a['source_mismatches'])}/권한위반{len(a['acl_violations'])}.
- 실제전송 {a['wire_request_matches']}개 일치, 불일치 {len(a['wire_request_mismatches'])}; 원문corpus SQLite우회 {a['sqlite_corpus_fallback']}.

단계별 결과
{json.dumps(e['gates'],ensure_ascii=False,indent=2)}

수정·재실행 이력
- ADR1233: 실제573.871초/7물리/3196SQL/답변0. 원문은있는데2경로보류, C1/C2/C3→C3/C2/C3 서버별칭충돌 확인.
- ADR1234: 동일원문 새조회ID 재결속 및 새claim ID namespace 분리,40관련검사통과. 실제271.660초/4물리/2770SQL.
  원문4개·경로3개 최종전송 확인했으나429. 시험전송기가 예외envelope를성공처럼return해 기존gateway 미할당exc 오류를 유발.
- ADR1235: 시험전송기의실패상태를 native TransportError로유지. 알려진429는KNOWN_REJECTED,5xx는UNKNOWN,성공HTTP정책거절/형식오류구분.
  실패분류/기존정책1회전환7검사통과 후 위 새실행1회. 저장모델응답 재생0. 원래 엔진의 검증·예산·정책을 우회하지 않았다.
- 앞선 실패와 원시결과는 보존했다. 이번결과를 다른질문/모든게시물/법률품질 인증으로 확대하지 않는다.

적용·한계
- 별도Gold connect.py + ontology_settings.json + runtime_patch_binding.json + runtime_patches2파일만 반영했다.
- connect.open_store의 store.gold_profile을 create_app(..., data_store=store, legal_agent_profile=store.gold_profile, ...)에 전달한다.
- 실제적용health는 ON/DB·21문서·13테이블/60컬럼 통과. 현재 MAIN123 선택/프로필 및 원래MAIN120엔진파일은 유지한다.
- 새DB쓰기/재게시/GENOS/Git/메일0. 기존벡터16,085개 유지, 이번질문은 원문탐색 경로이며 새벡터최종답변E2E를 주장하지 않는다.
- 일반 ASSESS가 온톨로지카드·원문을함께받는경로다. 별도SCENARIO_SELECTED 강제선택경로가아니다.
  모델이 온톨로지 때문에 답변을 개선했다는 인과효과는 미측정이다.
- rollback과 설치해시는 applied.json, 설정방법은 연결기 ONTOLOGY_ON_GUIDE.txt.

실패 상세(있으면)
{json.dumps(failures,ensure_ascii=False,indent=2)[:16000]}

증거
{O.relative_to(R)}/result.json
{O.relative_to(R)}/ontology-e2e.json
{P.relative_to(R)}/audit.json
{P.relative_to(R)}/raw/ 및 canonical/
'''
(U/'ON_최종확인결과.txt').write_text(report);put(U/'latest-result.json',{'adr':'ADR-1235','status':result['status'],'report':str((U/'ON_최종확인결과.txt').relative_to(R)),'ontology_enabled':True,'mode':'DB','actual':r,'stages':e['gates']})
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True},'live':result},comparisons=[],usage={'physical_calls':r['model_calls'],'provider_switches':provider_switches,'unknown':r['unknown'],'reported_cost_usd':a['reported_cost_usd']},latency={'seconds':r['seconds'],'population_claim':False},error_taxonomy=failures)
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정'];q=m['questions'][0];vals=['run-001/live; frozen rev001',read(D/'cases.json')[0]['request']['json']['question'],'기준답변 비공개·채점모델0.', '[동결입력](../artifacts/design/cases.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n순위/회수정책불변; ontology-lineage.json.gz의원문/경로/claim/답변결속.', '[실제raw/canonical](../artifacts/run-001/live/gold-369/) 모든본문보존.', str([(x['number'],x['stage'],x.get('http_status')) for x in calls]),'전송계약7검사·실제원문/wire대조. 새채점모델0.', result['status']];p=A/'실험'/q['file'];p.write_text('# gold-369\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p);put(A/'실험/manifest.json',m);(A/'실험/README.md').write_text('# 실험 인덱스\n\n- [gold-369]('+q['file']+'): '+result['status']+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령'];vals=[conclusion,'실제429 envelope를시험전송기가성공처럼return해전환경로가막힘.','호출전 criteria.json 동결; 원문·경로·claim·저장답변.', '기존Gold2패치동일·시험전송기1경계수정. 알려진공개질문1회.', '공개원문/실제Oracle/Qwen3.8. 정답주입없음.',report,'failure_events와원시응답을보존. 모델/서버/전송오류구분.',f"{r['seconds']:.3f}초·물리{r['model_calls']}·SQL{r['sql_calls']}·보고${a['reported_cost_usd']:.8f}",'원문전달/모델채택/최종저장 게이트분리.', 'in-sample 기능검증. 별도scenario선택·인과효과·법률정확성인증없음.', '앞선사용자요청으로별도GoldON반영; 이번제품추가변경0/MAIN123유지.','checks.py; preflight.py; audit.py gold-369; ontology_audit.py. 완료run재실행금지.']
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+('Accepted' if complete else 'Rejected'));(A/'README.md').write_text('---'+front+'---\n\n# ADR-1235: Gold ON 최종 실검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
p=A/'artifacts/manifest.json';v=read(p);v['files']=[{'path':str(f.relative_to(R)),'sha256':sha(f),'bytes':f.stat().st_size,'description':'Actual request or read-only contract/audit evidence','contains_raw_prompts_and_outputs':'/raw/' in str(f) or '/canonical/' in str(f)} for f in (A/'artifacts').rglob('*') if f.is_file() and f!=p];v.pop('notes',None);put(p,v)
print(result['status'])
