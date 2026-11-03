from common import *
import re,statistics
audit=read(ART/'source-wire-audit.json');semantic=read(ART/'semantic-review.json');progress=read(ART/'execution-progress.json')
rows=[read(d/'result.json') for d in sorted((ART/'live').iterdir()) if (d/'result.json').exists()];aa=audit['cells']
all_semantic=len(semantic['rows'])==4 and all(x['verdict']=='PASS' for x in semantic['rows'])
source_ok=all(not a[k] for a in aa for k in ('source_mismatches','acl_violations','wire_mismatches','output_caps'))
duplicates_ok=len(rows)==4 and all(r.get('duplicate',{}).get('same_answer') and r.get('duplicate',{}).get('extra_model_calls')==0 for r in rows)
resources_ok=all(a['peak_rusage_below5GiB'] and not a['resource_stop'] for a in aa)
settings={a:read(ART/'live'/('ontology-365-'+a)/'binding.json')['profile'] for a in ('baseline','ontology-on') if (ART/'live'/('ontology-365-'+a)/'binding.json').exists()}
def model_ontology(a):
 return any(x['bundle'].get('status')=='COMPLETE' and x['bundle'].get('payload',{}).get('bundle_id') for x in a.get('wire_ontology_inputs',[]))
on_aa=[a for a in aa if a['arm']=='ontology-on'];ontology_visible=len(on_aa)==2 and all(model_ontology(a) for a in on_aa)
metrics={}
for arm in ('baseline','ontology-on'):
 ar=[r for r in rows if r['arm']==arm];au=[a for a in aa if a['arm']==arm]
 metrics[arm]={'completed_cells':sum(s['arm']==arm and s['verdict']=='PASS' for s in semantic['rows']),'attempted_cells':len(ar),'request_seconds':sum(r['request_seconds'] for r in ar),'physical_calls':sum(a['physical_calls'] for a in au),'reported_tokens':sum(a['reported_tokens'] for a in au),'reported_cost_usd':sum(a['reported_cost_usd'] for a in au),'source_sql_calls':sum(r['source_sql_calls_before_requery'] for r in ar)}
eligible=all_semantic and source_ok and duplicates_ok and resources_ok and ontology_visible and all(a['budget_matches'] and a['unknown']==0 for a in aa)
changes={k:((metrics['baseline'][k]-metrics['ontology-on'][k])/metrics['baseline'][k] if eligible and metrics['baseline'][k] else None) for k in ('request_seconds','physical_calls','reported_tokens','reported_cost_usd','source_sql_calls')}
improved=eligible and any(changes[k]>=.10 for k in ('request_seconds','physical_calls','reported_tokens'))
if improved:conclusion='MAIN133의 고정 질문2개 ON/OFF 쌍에서 원문 대조·답변 완료를 유지하며 사전 기준의 성능 개선을 관측. 아래 개별 시간/호출/토큰 수치 범위의 결과이며 일반 성능 보장은 아님.'
elif eligible:conclusion='MAIN133의 두 질문 ON/OFF 답변과 원문 연결은 확인했지만 사전 기준(시간·호출·토큰 중10% 개선)의 성능 향상은 확인하지 못함.'
else:conclusion=f'MAIN133 실제 답변 완료: OFF {metrics["baseline"]["completed_cells"]}/{metrics["baseline"]["attempted_cells"]}건, ON {metrics["ontology-on"]["completed_cells"]}/{metrics["ontology-on"]["attempted_cells"]}건. 전체 답변 완료·원문 품질 조건을 충족하지 못해 성능 향상은 입증하지 못함. 미완료 시간을 개선율로 계산하지 않음.'
f=read(DES/'freeze.json');drift=[n for n,h in f['files'].items() if sha(ROOT/n)!=h];code=ROOT/f['code_root'];code_drift=[n for n,h in f['selected_files'].items() if sha(code/n)!=h]
result={'status':'PASS' if improved else 'NOT_PASSED','performance_improved':improved,'comparison_eligible':eligible,'conclusion':conclusion,'cells':rows,'cell_audits':aa,'execution':progress,'metrics':metrics,'observed_reduction_fraction':changes,
 'semantic_review':semantic,'source_integrity':source_ok,'duplicate_checks':duplicates_ok,'ontology_visible_both_on_cells':ontology_visible,'resource_checks':resources_ok,
 'ontology_display_mismatches':[a['cell'] for a in aa if a.get('ontology_display_vs_wire_mismatch')],
 'physical_calls':sum(a['physical_calls'] for a in aa),'unknown':sum(a['unknown'] for a in aa),'reported_cost_usd':sum(a['reported_cost_usd'] for a in aa),'reported_tokens':sum(a['reported_tokens'] for a in aa),'model_seconds':sum(a['model_seconds'] for a in aa),'request_seconds':sum(r['request_seconds'] for r in rows),
 'frozen_input_drift':drift,'frozen_code_drift':code_drift,'tested_release':'MAIN133/scenario-cumulative-20261102-r1','current_pointer_at_final':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'main_changes_by_this_task':0,'product_changes':0,'oracle_writes':0,'quality_certified':False,
 'replay':'Preserved prior response used solely for offline native authorization admission; replay physicalcalls0, excluded from real model metrics. No actual live response modified.',
 'limits':'Two fixed questions/single paired attempts, fresh processes; Oracle and OS caches not reset. Endpoint request time excludes store/application setup; separate process wall recorded. Reported usage may omit429/UNKNOWN. MAIN134 is a separate concurrent release; current-field/GENOS results not inferred.'}
assert not drift and not code_drift
parents=[]
for num,name in [(1293,'local-integration-ontology-ab'),(1294,'local-ontology-ab-memory-map'),(1296,'local-ontology-ab-derived-grant')]:
 p=ROOT/f'04_EXPERIMENTS/ADR/ADR-{num}-{name}/artifacts/run-001/result.json';x=read(p);parents.append({'adr':num,'physical_calls':x['physical_calls'],'reported_cost_usd':x['reported_cost_usd'],'status':x['status']})
result['prior_failed_probes']=parents;result['all_task_probes_physical_calls']=result['physical_calls']+sum(x['physical_calls'] for x in parents);result['all_task_probes_reported_cost_usd']=result['reported_cost_usd']+sum(x['reported_cost_usd'] for x in parents)
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['retrieval_accounting']=read(ART/'retrieval-metrics.json')
m['results'].update(status='complete',by_arm=metrics,comparisons=[{'comparison_eligible':eligible,'performance_improved':improved,'reduction_fraction':changes,'semantic':semantic}],judge_disagreements=0,usage={k:result[k] for k in ('physical_calls','reported_cost_usd','reported_tokens')},latency={'request_seconds':result['request_seconds'],'model_seconds':result['model_seconds']},error_taxonomy=[{'cell':a['cell'],'errors':a['failures']} for a in aa if a['failures']]);put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[conclusion,'사용자 요청은 기본20기능에 대사표와 온톨로지 성능 확인을 추가해 총22개로 만들고 로컬 검증하는 것이다. 초기1293의대사실제실패와시험기가상주소제한,1294·1296의파생문맥승인실패를보존했다. 이번에는제품동일513파일에서native내부사건/외부세션연결을검증한실험승인만사용했다.',
 '실행전 design/criteria.json 동결. 같은두질문에양쪽답변완료·원문품질보존·ON게시본실제전달확인후 요청시간/물리호출/보고토큰중하나10%이상감소. 실패와UNKNOWN 또는미실행을빠른성공으로간주하지않음.',
 '365OFF→ON,369ON→OFF 각1회. 기존공개상법원문/승인게시본, GoldOracle읽기전용·새프로세스·격리SQLite기록. 실제전에는이전원응답을재생하여두번째gateway승인통과·물리호출0을확인했다. 실제모델실행에서응답주입0.',
 'Qwen3.8-27b·Parasail FP8 우선/기존확정429 NearAI전환, 출력상한없음. 코드/질문/정책/전송기design/freeze.json. 정답원문은scoring-only-originals.json이며사후대조에만사용. 법령현행성심사가아님.',
 json.dumps({k:result[k] for k in ('status','comparison_eligible','metrics','observed_reduction_fraction','physical_calls','unknown','ontology_visible_both_on_cells')},ensure_ascii=False,indent=2),
 '\n'.join(a['cell']+': '+(a['failure'] or 'API결과와수동원문검토참조') for a in aa)+'\n\n원문/실제전송/예산은source-wire-audit.json, 의미판정은semantic-review.json. 온톨로지 표시 PREPARED_NOT_SENT와 실제 요청의 ontology_bundles 전달이 다른 셀: '+str(result['ontology_display_mismatches'])+'. 전송과 채택을 구분하며 실제 wire를 기준으로 전달 여부를 확인했다. 이전대사감독오류및모의기대문구실패는다른ADR원본보존.',
 f'이번물리{result["physical_calls"]}/보고${result["reported_cost_usd"]:.8f}/보고토큰{result["reported_tokens"]}/UNKNOWN{result["unknown"]}. 이전실패시험포함이번작업합계{result["all_task_probes_physical_calls"]}회/보고${result["all_task_probes_reported_cost_usd"]:.8f}. 회수단계는retrieval-stage-ledger.json: 같은artifact의상법조문root 전체→journal확보원문→실제wire의정확원문. 반복span회수와고유조문root수구분. 미실행은관측전달0이며법률오답아님.',
 'HTTP200·모델JSON수신·주장채택·답변완성·온톨로지수신·온톨로지의인과효과를구분했다. 개선비율은사전전체요건충족시에만계산한다. 단순ON설정이나기존Oracle게시조회9검사만으로성능향상을판정하지않았다.',
 result['limits']+' 작업중현재선택은MAIN134로별도변경됐다. 그별도169계약/root16/Gold9 및실제합성기준주장4기록은확인했지만이번MAIN133결과와합산하지않는다.',
 '이작업은제품/MAIN/Gold설정/원문·게시/운영DB·DDL/Gitpush/메일/현장변경0. 실패/시간초과원응답과기록을보존하고실패셀재실행0. 기본22개엑셀에실데이터/모의/부분/미통과구분.',
 'prepare→live --grant-replay(이전원응답재생/새모델0)→freeze→run_all(실제)→audit→원문수동검토→ledger→finalize→hash/status/validate/graph. 완료실험실제셀재실행금지. 재현은새ADR/새runtime.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if improved else 'Rejected'),front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 로컬 온톨로지 native 실제 검증1298\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
for q in m['questions']:
 c=next(c for c in read(DES/'cases.json') if c['id']==q['case_id']);sr=[r for r in semantic['rows'] if r['case_id']==c['id']]
 sections=[('실행 메타','run-001/baseline,ontology-on;design/freeze.json;실제와replay분리'),('사용자 질문 원문',c['question']),('기준답변 — 채점 전용, 제품 입력 비공개','scoring-only-originals.json의저장판본3요건과최종주장·원문을사후수동대조. 기준답변/좌표로모델선택수정0.'),('제품 입력을 구성한 원값','design/cases.json·live/<cell>/canonical및raw전체무손실보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json. 원문동일artifact조문root→확보→실제wire전달;이탈이유전부보존. 미확보를규정부재로판정하지않음.'),('제품 모델 호출 — run·arm별 실제 원문','live/<cell>/raw/call-*/request.json.gz,response.json.gz,finished.json. HTTP/사용량/공급자/UNKNOWN은calls.json. 재생은replay/별도,물리0.'),('중간 LLM 호출 — router/compiler/verifier/repair','live/<cell>/generations.json과calls.json에서전단계기록. 모델추가보완은기존예산대로. UNKNOWN후중단.'),('채점 호출과 반복 판정','외부채점0;사후source-wire-audit과수동semantic-review. 같은요청재조회는동일결과/추가0검사이며확률반복표본아님.'),('사례 최종 판정',json.dumps(sr,ensure_ascii=False,indent=2))]
 (ADR/'실험'/q['file']).write_text('# '+c['id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 기록\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1298','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved native probe record','contains_raw_prompts_and_outputs':'raw' in p.parts or 'canonical' in p.parts} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json']})
out=ROOT/'09_ARTIFACTS/AUDITS/20261103-local-integration-verified';out.mkdir(exist_ok=True)
(out/'로컬검증결과.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
print(json.dumps({k:result[k] for k in ('status','performance_improved','physical_calls','unknown','reported_cost_usd','conclusion')},ensure_ascii=False))
