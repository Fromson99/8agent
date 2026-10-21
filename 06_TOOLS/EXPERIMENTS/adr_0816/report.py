"""Report the frozen census without changing inputs, oracles or product code."""
from pathlib import Path
import hashlib,json,math,re,statistics
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0816-complete-contract-confirmation';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def identities(rows):
 d={canon(x):x for x in rows};return [d[k] for k in sorted(d)]
def check_values(row):
 value=row['checks']
 if isinstance(value,dict):values=list(value.values())
 else:
  assert isinstance(value,list) and all(isinstance(x,dict) and 'passed' in x for x in value),'invalid check records'
  values=[x['passed'] for x in value]
 assert all(type(x) is bool for x in values),'check outcome must be boolean'
 return values
def failure_class(row):
 if row['passed']:return None
 error=row.get('error') or {}
 infrastructure={'ImportError','ModuleNotFoundError','SyntaxError','NameError','UnboundLocalError','TypeError','KeyError','IndexError','OSError','FileNotFoundError','OperationalError'}
 if error.get('owner')=='fixture_or_runner' or error.get('type') in infrastructure:return 'harness_or_unclassified'
 return 'observed_contract_failure' if any(x is False for x in check_values(row)) else 'harness_or_unclassified'
def nonnegative(value):return type(value) in (int,float) and math.isfinite(value) and value>=0
def test_count(p):
 text=p.read_text();summaries=re.findall(r'(?m)^(?:=+\s*)?(\d+ passed[^\n]*)$',text)
 if not summaries or re.search(r'\b[1-9]\d* (?:failed|error|skipped|xfailed|xpassed)',summaries[-1]):return 0
 return int(summaries[-1].split()[0])
def timing(p):
 s=p.read_text();rss=int(re.search(r'Maximum resident set size \(kbytes\): (\d+)',s)[1]);v=re.search(r'Elapsed \(wall clock\) time .*?: (\S+)\n',s)[1];parts=list(map(float,v.split(':')));seconds=sum(x*60**i for i,x in enumerate(reversed(parts)));status=int(re.search(r'Exit status: (\d+)',s)[1])
 return {'elapsed_seconds':seconds,'max_rss_kib':rss,'exit_status':status,'passed':nonnegative(seconds) and seconds<=180 and 0<rss<=12582912 and status==0}
m=read(A/'실험/manifest.json');criteria=read(D/'criteria.json');f=read(D/'freeze.json')
assert m['reservation']['status']=='in_progress','completed ADR records are immutable'
assert all(sha(R/n)==h for n,h in f['files'].items()),'frozen input changed'
families=list(criteria['families']);obs={arm:{family:read(A/'artifacts/qualification'/arm/(family+'.json')) for family in families} for arm in ('baseline','connected')}
rows={arm:{x['case_id']:x for family in families for x in obs[arm][family]['results']} for arm in obs}
descriptors={family:read(D/(family+'-cases.json')) for family in families}
expected=[x['case_id'] for family in families for x in descriptors[family]['cases']]
assert len(expected)==len(set(expected))==128
for arm in obs:
 assert set(rows[arm])==set(expected)
 for family in families:
  observation=obs[arm][family];records=observation['results'];descriptor=descriptors[family];path=D/(family+'-cases.json')
  assert observation['arm']==arm and observation['family']==family,'arm/family receipt mismatch'
  assert len(records)==criteria['families'][family]['count'] and {x['case_id'] for x in records}=={x['case_id'] for x in descriptor['cases']},'family case inventory mismatch'
  if 'descriptor_hash' in observation:assert observation['descriptor_hash']==hashlib.sha256(canon(descriptor).encode()).hexdigest()
  elif 'case_inventory_sha256' in observation:assert observation['case_inventory_sha256']==sha(path)
  else:assert observation.get('case_manifest_sha256')==sha(path),'unbound case descriptor'
  assert nonnegative(observation['elapsed_seconds']) and nonnegative(observation['max_rss_kib'])
  assert type(observation['real_model_calls']) is int and observation['real_model_calls']>=0
  for row in records:
   values=check_values(row)
   assert type(row['passed']) is bool and row['passed']==(bool(values) and all(values) and not row.get('error')),'passed flag disagrees with nonempty checks/error'
   assert type(row['executed_retrieval']) is bool and nonnegative(row['elapsed_seconds'])
   assert all(type(row[k]) is int and row[k]>=0 for k in ('tool_calls','stub_model_calls'))
reg={arm:test_count(A/'artifacts'/('regression-'+arm+'.txt')) for arm in obs}
api={arm:read(A/'artifacts'/(( 'candidate' if arm=='connected' else arm)+'-consumer-v2.json')) for arm in obs}
cost={arm:timing(A/'artifacts'/('consumer-'+arm+'.time')) for arm in obs}
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0813-evidence-first-comparison/artifacts/design/freeze.json')
parent_root=R/'04_EXPERIMENTS/ADR/ADR-0813-evidence-first-comparison';parent_artifacts=read(parent_root/'artifacts/manifest.json')
retained=[]
for name in ('boundary-tests.txt','regression-tests.txt'):
 path=parent_root/'artifacts'/name;entry=next(x for x in parent_artifacts['files'] if Path(x['path']).name==name)
 retained.append({'path':str(path.relative_to(R)),'sha256':sha(path),'hash_matches_parent_record':sha(path)==entry['sha256'],'passed':test_count(path),'inherited':True})
baseline_binding=read(D/'baseline.json')['manifest'];data_binding=read(D/'data-binding.json')
for arm,value in api.items():
 assert isinstance(value['checks'],dict) and all(type(x) is bool for x in value['checks'].values())
 assert type(value['model_calls']) is int and value['model_calls']>=0
real_model_calls=sum(v['real_model_calls'] for arm in obs.values() for v in arm.values())+sum(v['model_calls'] for v in api.values())
checks={'candidate_128_cases':all(x['passed'] for x in rows['connected'].values()),'no_paired_regressions':not any(rows['baseline'][cid]['passed'] and not rows['connected'][cid]['passed'] for cid in expected),'both_170_shared_regressions':all(v==170 for v in reg.values()),'retained_399_parent_regressions':sum(x['passed'] for x in retained)==399 and all(x['hash_matches_parent_record'] for x in retained),'actual_service_both_arms':all(len(v['checks'])==12 and all(v['checks'].values()) and v['status']=='PASS' for v in api.values()),'same_service_code_and_data_binding':all(v['code_root']==(f['code_root'] if arm=='connected' else baseline_binding['code_root']) and v['data']==data_binding for arm,v in api.items()),'identical_338_parent_serving_files':f['serving_files']==parent['serving_files'] and len(f['serving_files'])==338,'zero_real_model_calls':real_model_calls==0,'resources_bounded':all(v['elapsed_seconds']<=180 and 0<v['max_rss_kib']<=12582912 for arm in obs.values() for v in arm.values()) and all(v['passed'] for v in cost.values()),'frozen_inputs_unchanged':True}
limits=['Finite software contract census, not unseen legal questions or a legal accuracy estimate; quality_certified=false.','Actual selected1547 documents lack verified workflow_version/valid_from; legal version validity remains gated.','Needed internal regulation availability remains unconfirmed.','Initial planner overflow is explicit incomplete; automatic initial-location pagination is not implemented.','Unmapped missing user facts still conservatively gate all issues.','Full real-data RAG/model comparison and GENOS execution were not run.','Parent0815 rejected116/128 due to root-introduced undefined helper-only metric in issue recording; that metric alone is removed and all cases rerun; original results remain unchanged.','Parent0814 was rejected122/128 because the test harness omitted the typed invalid-citation rejection; all inputs/oracles/products remain identical and every case is rerun here. Known finite conditions, not an unseen legal holdout.','Completed0813 final metadata validation failed; parent history is retained unchanged. This ADR has its own prospectively enumerated cases and accounting.']
summary={arm:{'passed':sum(x['passed'] for x in rows[arm].values()),'total':128,'families':{family:{'passed':sum(x['passed'] for x in obs[arm][family]['results']),'total':len(obs[arm][family]['results'])} for family in families}} for arm in obs}
resources={arm:{family:{k:v[k] for k in ('elapsed_seconds','max_rss_kib','real_model_calls')} for family,v in observed.items()} for arm,observed in obs.items()}
usage={arm:{'stub_model_calls':sum(x['stub_model_calls'] for x in rows[arm].values()),'tool_calls':sum(x['tool_calls'] for x in rows[arm].values())} for arm in obs}
classifications={arm:{cid:failure_class(row) for cid,row in records.items() if not row['passed']} for arm,records in rows.items()}
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'by_arm':summary,'regressions':reg,'retained_parent_regressions':retained,'actual_api':{arm:len(v['checks']) for arm,v in api.items()},'service_cost':cost,'qualification_resources':resources,'usage_by_arm':usage,'quality_certified':False,'real_model_calls':real_model_calls,'limitations':limits,'failure_classification':classifications,'paired':{'improved':sum(failure_class(rows['baseline'][c])=='observed_contract_failure' and rows['connected'][c]['passed'] for c in expected),'baseline_harness_or_unclassified':sum(failure_class(rows['baseline'][c])=='harness_or_unclassified' for c in expected),'regressed':sum(rows['baseline'][c]['passed'] and not rows['connected'][c]['passed'] for c in expected)}}
put(A/'artifacts/run-001/result.json',result)
# Mechanical records are question-level cases for the standard, not legal gold.
questions=[];heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for family in families:
 for case in descriptors[family]['cases']:
  cid=case['case_id'];i=len(questions)+1;filename=f'질문-{i:03d}-{cid}.md';p=A/'실험'/filename
  texts=[f'run-001 / baseline, connected / {family} / {cid}',f'합성 기술 계약 사례. 정의: ../artifacts/design/{family}-cases.json 의 {cid}. 실제 법률 질문이 아니다.',f'동결 descriptor의 oracle와 criteria.json을 적용한다. 법률 정답·골든 좌표는 없다.',f'입력·생성 규칙·oracle 정본: ../artifacts/design/{family}-cases.json. 양쪽 동일 입력.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json 의 동일 case_id. 해당 없는 가족은 executed=false와 사유를 보존한다.',f'실제 모델 호출0. ../artifacts/qualification/baseline/{family}.json 및 connected/{family}.json 에 원문 좌표·체크·오류·시간이 있다.','실제 모델 호출0. 복구 가족의 stub 응답은 원장/어댑터 기술 동작만 검사한다.','동결한 결정적 oracle 1회씩; 모델 채점 없음.',json.dumps({arm:{'passed':rows[arm][cid]['passed'],'checks':rows[arm][cid]['checks']} for arm in obs},ensure_ascii=False,indent=2)]
  p.write_text(f'# {cid}\n\n'+'\n\n'.join(f'## {j}. {h}\n\n{t}' for j,(h,t) in enumerate(zip(heads,texts),1))+'\n');questions.append({'number':i,'case_id':cid,'file':filename,'sha256':sha(p)})
m['questions']=questions
plans=m['design']['retrieval_stage_plan']['stages_by_arm'];arms=[];universe=[];fixed_inventory=[];metrics={k:{} for k in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')}
for arm in obs:
 cases=[];counts=[];initial_total=0
 for cid in expected:
  record=rows[arm][cid];executed=record['executed_retrieval'];skip=None if executed else record['skip_reason']
  raw_available=record['available'];raw_presented=record['presented']
  if not executed:
   # Fixed original consumers did run, but no retrieval ran. Preserve their
   # exact block/span coordinates separately instead of inventing article roots
   # or describing supplied source consumption as executed source retrieval.
   if not skip:
    assert not record['passed'] and record.get('error'),'unexplained non-execution'
    skip='Retrieval did not execute because the recorded fixture/runner failed: '+canon(record['error'])
   if raw_available or raw_presented:
    fixed_inventory.append({'arm_id':arm,'case_id':cid,'executed_retrieval':False,'skip_reason':skip,
      'available':raw_available,'presented':raw_presented,
      'available_occurrences':len(raw_available),'presented_occurrences':len(raw_presented),
      'available_unique':len(identities(raw_available)),'presented_unique':len(identities(raw_presented)),
      'observation_path':str((A/'artifacts/qualification'/arm/(next(family for family in families if cid in {x['case_id'] for x in descriptors[family]['cases']})+'.json')).relative_to(R))})
   raw_available=[];raw_presented=[]
  available=identities(raw_available);presented=identities(raw_presented);universe.extend(available)
  assert all(set(x)=={'doc_id','node'} and type(x['node']) is int for x in available+presented)
  assert {canon(x) for x in presented}<={canon(x) for x in available}
  before=[];before_occurrences=0;stages=[];assert executed or (skip and not available and not presented)
  assert len(plans[arm])==2,'source/present stage plan changed'
  for plan,after,after_occurrences in zip(plans[arm],(available,presented),(len(raw_available),len(raw_presented))):
   bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())];reason='Not retained by actual arm under the frozen scope/budget/identity contract; detailed native checks and errors in family observation.'
   stages.append({**plan,'executed':executed,'skip_reason':skip,'before':before,'added':added,'discarded':discarded,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),'occurrence_counts':{'before':before_occurrences,'after':after_occurrences,'canonical_collapsed_before':before_occurrences-len(before),'canonical_collapsed_after':after_occurrences-len(after)},'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]});before=after;before_occurrences=after_occurrences
  cases.append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':cid,'gold_total':0,'gold_identities':[],'stages':stages});counts.append(len(presented));initial_total+=len(available)
 arms.append({'arm_id':arm,'declared_stage_ids':[x['stage_id'] for x in plans[arm]],'cases':cases,'aggregate':{'cases':len(cases),'presented_total':sum(counts),'gold_total':0}})
 metrics['before_filter'][arm]=initial_total;metrics['after_filter'][arm]=sum(counts);metrics['presented_total'][arm]=sum(counts);metrics['presented_mean'][arm]=statistics.mean(counts);metrics['presented_p50'][arm]=statistics.median(counts);metrics['presented_p95'][arm]=sorted(counts)[round((len(counts)-1)*.95)];metrics['golden_recall'][arm]=None
corpus=len(identities(universe));assert corpus>0
for arm in obs:metrics['selectivity'][arm]=metrics['presented_mean'][arm]/corpus
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'scope':'Synthetic native source locations only. Nonretrieval stage snapshots are empty; exact fixed inventory consumption is retained separately here.','presentation_semantics':'retrieval: native reader output; navigation: initial planner hints. Neither is model adoption; all real model calls are zero.','metric_population':'Required manifest aggregates cover all 128 cases including skipped retrieval cases; they are not mean retrieval size among executed cases or a legal recall measure.','denominator':'Union of synthetic structured native source coordinates; source-only groups verified by whole-block checks separately, no invented coordinates.','fixed_inventory_consumption':fixed_inventory}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();p=A/'artifacts/run-001/retrieval-ledger.json';put(p,ledger)
m['retrieval_accounting'].update(corpus_total=corpus,**metrics);m['retrieval_accounting']['stage_ledger']['sha256']=sha(p)
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={arm:{'status':'complete',**v} for arm,v in summary.items()},comparisons=[result['paired']],usage={'product_model_calls':real_model_calls,'offline_evaluator_calls':0,'synthetic_by_arm':usage},latency={'service':cost,'qualification':resources},error_taxonomy=[{'kind':'other','detail':arm+'/'+cid+': '+classification} for arm,values in classifications.items() for cid,classification in values.items()]);put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[('Accepted, promotion-candidate' if result['strict_success'] else 'Rejected, MAIN unchanged')+'. 유한 기술 계약 전수 검사이며 법률 정확도 인증은 아니다. 검증과 실제 MAIN 적용은 별도 기록한다.','정의 위치의 임의 제한, 계층 원문 누락, 쟁점 연결 소실, 대사 필드 충돌과 중단된 제안의 재개 결함.','실행 전 동결한128개 조건 전부 통과, 기존 통과→후보 실패0, 양쪽170회귀 및 실제API12, 가족/서비스180초·12GiB 이내.','MAIN75 baseline와 완료0813의 동일338개 serving 코드. 여섯 가족의 모든 선언된 조합, 조건 교체·결과 후 oracle 변경 없음.','freeze.json과 각 family-cases.json에 입력/코드/예산/판정 고정. 기술 stub만 사용, 실제 모델0회, 선택 데이터 세대 동일. 알려진 회귀 검사와 신규 유한 계약 검증을 구분한다.',json.dumps(result,ensure_ascii=False,indent=2),'실험/질문-*.md 와 artifacts/qualification의 각 사례 실제 checks/error가 정본. baseline 미지원 동작도 실패로 계수. 누락·실패를 성공이나 미실행으로 감추지 않는다.','artifacts/run-001/retrieval-ledger.json 에128개 모든 사례×양쪽 arm의 실제 좌표/미실행 사유를 보존. 법률 골든0; recall 미측정. 시간·메모리는 결과 및 consumer 시간 기록 참조.','기계적으로 보장할 계약 개선만 판정한다. 의미 판단은 모델 소유이고 법률 정답 향상률로 바꾸지 않는다.','\n'.join(limits),'성공한 경우에만 hash 고정 prepare/apply로 동일 후보를 선택한다. 권한·원문·상태·해시 회귀 시 MAIN75로 롤백. 부모0813 메타 검증 실패는 보존하고 이 ADR의 최종 검사를 독립 수행한다.','repin.py → candidate freeze/validate → freeze.py → 세 qualification runner 각 arm → shared run_tests.py 각 arm → consumer_check.py baseline/candidate → report.py → validate → status completed → validate --final → graph → prepare_promotion.py → stable apply --confirm-main → consumer_check.py active.']
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$', 'status: '+('Accepted' if result['strict_success'] else 'Rejected'),meta);meta=re.sub(r'(?m)^decision_eligible:.*$','decision_eligible: true',meta);meta=re.sub(r'(?m)^main_wiring:.*$','main_wiring: '+('promotion-candidate' if result['strict_success'] else 'unchanged'),meta)
(A/'README.md').write_text('---'+meta+'---\n\n# 원문 완전성·대사 기술 계약 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');(A/'RESULT.txt').write_text('\n\n'.join(texts)+'\n')
(A/'실험/README.md').write_text('# 유한 기술 계약128개\n\n실제 법률 질문이나 골든 채점이 아니다. 동결 사례별 양쪽 관측과 판정은 각 질문 파일과 artifacts/qualification에 연결된다.\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in questions)+'\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ('manifest.json','report.log') and not p.name.endswith(('-wal','-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0816','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen finite census input, observed contract results and service checks','contains_raw_prompts_and_outputs':p.suffix=='.sqlite'} for p in files]})
print(json.dumps({k:result[k] for k in ('strict_success','checks','by_arm','paired')},ensure_ascii=False))
