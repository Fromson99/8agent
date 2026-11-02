from pathlib import Path
import json,hashlib,sys,datetime
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1250-main129-oracle-live-retest';D=A/'artifacts/design';O=A/'artifacts/run-001';P=O/'live/gold-369';U=R/'09_ARTIFACTS/AUDITS/20261030-main129-oracle-live'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary as put
x=read(O/'audit-decoded.json');sql=read(O/'sql-audit.json');before=read(D/'capacity-before.json');cap=read(O/'capacity-after.json');size=read(O/'storage-size.json');calls=read(P/'calls.json');samples=[json.loads(v) for v in (P/'resource-samples.jsonl').read_text().splitlines()];stop=read(P/'resource-stop.json');binding=read(D/'before.json')['binding'];C=R/binding['engine_root'];core_exact=all(sha(C/n)==h for n,h in binding['engine_files'].items());assert core_exact
states=[r['status'] for j in x['journals'] for r in j.get('runs',[])];assert states==['RUNNING'] and x['physical_model_calls']==2 and x['unknown_outcomes']==0
shared_sql=sum(v['started'] for v in sql['groups'].values());passed={'main129_core495_exact':core_exact,'model2_complete_no_unknown':True,'fresh_oracle_readback':bool(x['journals']) and x['structured_proposals']==2,'acquired_original_hash_acl':x['source_checks']>0 and not x['source_mismatches'] and not x['acl_violations'],'raw_diag_exclusion':not x['raw_response_leaks'] and all(v['request_is_diagnostic_reference'] and v['capture_status']=='UNCONFIGURED' for v in x['attempts']),'no_disk_runtime':not x['physical_runtime_exists'],'reserved_physical_budget':x['physical_budget_matches'],'shared_sql_below10000':shared_sql<10000,'db_disk_below90':cap['within_limit'],'api_persisted_answer':False,'full_execution_without_resource_stop':False,'all_frozen_dependencies_unchanged':not x['changed_frozen_files']}
result={'status':'RESOURCE_INTERRUPTED','strict_success':False,'checks':passed,'main_generation':129,'release_id':'oracle-safe-records-20261030-r1','engine_files':495,'question_runs':1,'actual_model_calls':2,'complete_model_responses':2,'model_unknown':0,'reported_cost_usd':x['reported_cost_usd'],'reported_input_tokens':x['reported_input_tokens'],'reported_output_tokens':x['reported_output_tokens'],'http_response_returned':False,'answer_present':False,'final_stage_reached':False,'process_exit_code':125,'stop':stop,'last_durable_elapsed_seconds':samples[-1]['elapsed_seconds'],'normal_total_seconds_unavailable':True,'resources':x['resources'],'process_swap_peak_MiB':max(v['VmSwap'] for v in samples)/1024**2,'oracle_tables':x['oracle_tables'],'oracle_run_states':states,'source_checks':x['source_checks'],'storage':size,'sql_groups':sql['groups'],'shared_source_agent_started':shared_sql,'sql_unclosed':sql['unclosed_calls'],'capacity':cap,'capacity_before':before,'native_crash_observed':False,'same_question_redispatched_after_stop':False,'full_frozen_dependency_drift':x['changed_frozen_files'],'product_or_main_mutated_by_this_run':False,'nfs_mount_certified':False,'field_ords_19c_genos_certified':False,'quality_certified':False}
put(O/'result.json',result);U.mkdir(parents=True,exist_ok=True);put(U/'result.json',result)
text=f'''MAIN129 / DP=oracle 실제 LLM 재시험 — ADR1250 / 2026-10-30

결과: RESOURCE_INTERRUPTED / 전체미통과
질문: {read(D/'cases.json')[0]['request']['json']['question']}
선택MAIN129495파일·GoldR18/온톨로지ON DB·Oracle원문/Agent구조화기록으로질문1회.
실제Parasail FP8 {x['physical_model_calls']}회 모두HTTP200/stop, 모델UNKNOWN0·전환0.
입력{x['reported_input_tokens']}/출력{x['reported_output_tokens']}토큰, 보고${x['reported_cost_usd']:.8f}.
모델통신합{x['model_seconds']:.3f}초, 마지막내구자원표본 {samples[-1]['elapsed_seconds']:.3f}초.
마지막표본은정상finally의총시간이아니며실제중단시점보다앞이다. 약2분13초구간진행후중단.

중단 원인
호스트전체swap증가>128MiB 사전조건에서감시기가exit125.
트리거직전마지막성공표본host증가{x['resources']['max_host_swap_growth_MiB']:.3f}MiB;
한도초과검사는표본반환전에예외가나므로정확한초과값은내구기록에없다.
RSS최대{x['resources']['max_RSS_GiB']:.3f}GiB/가용RAM최저{x['resources']['min_available_GiB']:.3f}GiB/프로세스VmSwap표본최대{result['process_swap_peak_MiB']:.3f}MiB.
전체호스트지표이며이번실행단독원인·Oracle/LLM장애로단정하지않는다.
중단때진행중모델없음·정상모델worker모두회수. SIGSEGV/LLMtimeout 근거없음, native-stack0바이트.
이른중단으로SQLite충돌문제전체완치또는실제최종법률답변성공을인증하지않는다.
동일질문재전송/자동재시험0. 원래사전조건을완화해재호출하지않았다.

Oracle 기록 / 용량
새프로세스재조회4표: {json.dumps(x['oracle_tables'])}.
구조화응답2건, 확보원문{x['source_checks']}대조 불일치{len(x['source_mismatches'])}/권한위반{len(x['acl_violations'])}.
본문{size['parts']}조각/{size['unique_bodies']}고유본문, 모두v3, envelope{size['envelope_characters']}문자.
Oracle원장은마지막확정상태RUNNING그대로이며사후에FAILED/COMPLETED로바꾸지않았다.
최종ASSESS/답변/PUBLISHED·성공중복요청검증은미도달이다.
이전에실패한1245 scope행수1/2987/52742/52도그대로보존. 삭제/재압축/Gold/DDL0.
SIDDA할당 {before['sidda_used_percent']:.4f}%→{cap['sidda_used_percent']:.4f}% (+{(cap['sidda_used_bytes']-before['sidda_used_bytes'])/1024**2:.3f}MiB).
디스크 {cap['disk_used_percent']:.3f}%, 모두사용자한도90%이내. quota300MiB 그대로.
다음Agent쓰기전16MiB여유를확인하는별도연구guard 사용, 용량guard자체중단0.

SQL / 서빙 경계
공유원문+기록SQL시작{shared_sql}회 / 사전한도10000미도달.
원문{list(sql['groups'].values())[0]['started']}시작/2257완료, 경계64.024초.
Agent3120시작/완료·쓰기1388, 경계33.435초. 마지막원문SELECT1건완료로그미확인.
이경계는Oracle CPU만이아니며전송/직렬화/DB를포함한다. 용량관찰용관리SELECT는별도라실행SQL개선율로합산하지않는다.
실제Gold데이터포트+직접SQL기록어댑터의실험이며현장ORDS/GENOS/Oracle19 Factory검증은아니다.
NFS/CIFS mount없음, 진단UNCONFIGURED/로컬fallback없음. 연구raw/canonical증거는별도gzip으로보존.
기존1245는모델8회후종료, 이번은2회후중단으로단계가달라숫자를전체성능개선율로비교하지않는다.

코드 결속 / 한계
고정MAIN129 선택엔진495파일은전후정확히동일. 이실험이제품/MAIN을바꾼것은없다.
별도병행작업으로공통전송기파일02_BACKEND/lawrag/research/experiment_client.py의사후해시가동결값과달라졌다.
따라서모든동결의존성동일성은미충족이며, 로드된전송기의정확한중간수정시점/버전은확정하지않는다.
실제2요청의provider/model/schema/payload와응답은raw/experiment-client기록에보존했다.
최종답변없음·법률품질/전체속도/전체스토리지/실제GENOS인증없음.
사후독자namespace의MAIN128문자열잔재는실행영수증namespace직접참조로정정했다.
잘못된0행조회원본은audit-namespace-mismatch.json/log로보존, 실제모델/DB쓰기0인독자준비오류다.
원시실험과기준은결과뒤수정/재실행하지않았다.
''';(U/'실제실험_결과.txt').write_text(text)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','historical_only':True,'new_model_calls':0},'live':{'status':'complete',**result}},comparisons=[],judge_disagreements=0,usage={'physical_model_calls':2,'reported_cost_usd':x['reported_cost_usd'],'input_tokens':x['reported_input_tokens'],'output_tokens':x['reported_output_tokens']},latency={'last_checkpoint_seconds':samples[-1]['elapsed_seconds'],'normal_total_seconds':None,'p95':None,'model_seconds':x['model_seconds']},error_taxonomy=[{'category':'resource_guard_stop','reason':'HOST_SWAP_GROWTH','model_unknown':False},{'category':'external_dependency_drift','files':x['changed_frozen_files']},{'category':'incomplete_finalization','final_answer':False}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정'];vals=['run-001/live,MAIN129495·GoldR18/ON DB,DPoracle·실제모델2·공유SQL한도·용량관찰.',read(D/'cases.json')[0]['request']['json']['question'],'기준답변제품미제공·채점모델0.','[동결](../artifacts/design/freeze.json) · [Oracle감사](../artifacts/run-001/audit-decoded.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색정책변경/품질비교없음. 확보원문7·최종입력0·중도중단.','[원시전송gzip](../artifacts/run-001/live/gold-369/raw/)·[canonical](../artifacts/run-001/live/gold-369/canonical/). 연구증거이며NFS제품로그성공아님.','[물리2호출](../artifacts/run-001/live/gold-369/calls.json); 추가호출0.','독립judge/재채점0. 자원중단과전송기의존성변경범위는원본그대로기록.','RESOURCE_INTERRUPTED·최종0·새Oracle프로세스기록보존확인,법률정답률미측정.']
for q in m['questions']:
 p=A/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p)
(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');(A/'실험/README.md').write_text('# 실험인덱스\n\n- [gold-369](질문-001-gold-369.md): RESOURCE_INTERRUPTED,답변0.\n')
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected');heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령'];vals=['Rejected: 자원감시중단·최종답변0. MAIN129코드변경/자동재시험0.','MAIN129 저장/메모리갱신수정후실제Oracle/LLM재시험.','[사전 기준](artifacts/design/criteria.json). 공유SQL1만·디스크/DB90%·호스트swap증가128MiB·첫실패/UNKNOWN중단.','알려진369질문1회·선택495명시고정·Gold실제원문/AgentOracle·NFS미설정.','현재모델/공급자정책 Qwen3.8/Parasail FP8·출력상한없음. MAIN129495변경0·공통전송기1의존성병행드리프트.','[결과](artifacts/run-001/result.json).\n\n'+text,'호스트스왑증가로exit125이며LLM/Oracle/SQLite오류로단정하지않는다. 원래진행상태RUNNING은사후에성공/실패로재작성하지않았다.','물리2/stop2·UNKNOWN0·보고$0.00456756·원문7대조. Oracle할당+8MiB/83.9375%·공유SQL5378시작.','기록재조회와실제최종답변성공은별개다. 불완전표본을이전전체실행과성능개선율로비교하지않는다.','실제최종/법률품질/현장GENOS/NFS/ORDS/19c 미검증. 호스트전역지표원인미확정·트리거정확값미저장·의존성파일드리프트.','MAIN129 선택유지·실행고유scope보존·기존실패삭제0·DDL/Gold/제품/MAIN/메일/Git변경0. 다음실험은새ADR/조건동결이필요하며이번재전송0.','preflight/checks/capacity/freeze→actual run1→resource stop125→read-only audit/sql/capacity/storage→finish→ADR검사. 완료실험재전송금지.'];(A/'README.md').write_text('---'+front+'---\n\n# MAIN129 실제Oracle/LLM 재시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
p=A/'artifacts/manifest.json';v=read(p);v['files']=[{'path':str(q.relative_to(R)),'sha256':sha(q),'bytes':q.stat().st_size,'description':'Frozen before-dispatch design, actual partial live evidence or read-only post-run audit; failure retained','contains_raw_prompts_and_outputs':any(k in str(q) for k in ('/raw/','/canonical/','/experiment-client/'))} for q in (A/'artifacts').rglob('*') if q.is_file() and q!=p];p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');print('RESOURCE_INTERRUPTED/Oracle readback done; core495 unchanged/one external helper drift');print(U/'실제실험_결과.txt')
