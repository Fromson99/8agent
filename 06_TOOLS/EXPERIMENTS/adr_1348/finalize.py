"""Report preserved observations; never change model outputs or product state."""
from common import *
import re,statistics,collections
number=int(ADR.name.split('-')[1]);audit=read(ART/'source-wire-audit.json');semantic=read(ART/'semantic-review.json');cases=read(DES/'live-cases.json')
build=read(ART/'build-live/result.json') if (ART/'build-live/result.json').exists() else None
rows=[]
for d in sorted((ART/'usage-live').glob('*')):
 if not (d/'result.json').exists():continue
 x=read(d/'result.json');a=read(d/'audit.json');calls=read(d/'calls.json')
 for turn in x['turns']:
  score=next(s for s in semantic['rows'] if s['case_id']==x['case_id'] and s['arm']==a['arm'])
  rows.append({**turn,'arm':a['arm'],'correct_complete':score['correct_complete'],'review':score,'reported_tokens':a['reported_tokens'],'reported_cost_usd':a['reported_cost_usd'],'model_seconds':a['model_seconds'],'ontology_complete_inputs':sum(z.get('status')=='COMPLETE' for z in a['wire_ontology_inputs']),'ontology_input_count':len(a['wire_ontology_inputs']),'output_path':str((d/'turn-1/answer.txt').relative_to(ROOT))})
metrics={a:{'attempted':sum(r['arm']==a for r in rows),'correct_complete':sum(r['arm']==a and r['correct_complete'] for r in rows),**{k:sum(r[k] for r in rows if r['arm']==a) for k in ('request_seconds','physical_calls','reported_tokens','reported_cost_usd','model_seconds')}} for a in ('baseline','ontology-on')}
pairs=[]
for c in cases:
 off=next((r for r in rows if r['case_id']==c['id'] and r['arm']=='baseline'),None);on=next((r for r in rows if r['case_id']==c['id'] and r['arm']=='ontology-on'),None)
 eligible=bool(off and on and off['correct_complete'] and on['correct_complete'] and on['ontology_complete_inputs'])
 pairs.append({'case_id':c['id'],'eligible':eligible,'off_complete':bool(off and off['correct_complete']),'on_complete':bool(on and on['correct_complete']),'delta':{k:(on[k]-off[k] if eligible else None) for k in ('request_seconds','physical_calls','reported_tokens')},'reason':None if eligible else 'Missing/unfinished answer or no complete bundle delivered; failure time not improvement'})
candidate=read(DES/'candidate.json');b=read(DES/'baseline.json');code=ROOT/candidate['code_root']
assert all(sha(code/n)==h and sha(ROOT/n)==h for n,h in candidate['selected_files'].items())
assert all(sha(selected()/n)==h for n,h in b['release']['files'].items())
assert all(not a[k] for a in audit['cells'] for k in ('source_mismatches','acl_violations','wire_mismatches'))
summary={'status':semantic['status'],'conclusion_ko':semantic['conclusion_ko'],'main':142,'product_files':528,'product_changes':0,'main_pointer_unchanged':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer'],'candidate':candidate['pin'],'build':build,'build_audit':read(ART/'build-response-audit.json') if build else None,'usage_rows':rows,'metrics':metrics,'pairs':pairs,'physical_calls':sum(r['physical_calls'] for r in rows)+(build['physical_calls'] if build else 0),'unknown':sum(r['unknown'] for r in rows)+(build['unknown'] if build else 0),'reported_cost_usd':sum(r['reported_cost_usd'] for r in rows)+(build['reported_cost_usd'] if build else 0),'source_checks':sum(a['source_checks'] for a in audit['cells']),'delivered_checks':sum(a['delivered_checks'] for a in audit['cells']),'source_mismatches':0,'acl_violations':0,'wire_mismatches':0,'budget_matches':all(a['budget_matches'] for a in audit['cells']),'duplicate_extra_calls':sum(r.get('duplicate',{}).get('extra_model_calls',0) for r in rows),'oracle_calls':0,'genos_tested':False,'quality_certified':False}
put(RUN/'result.json',summary)
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
inventory={(x[0],int(x[1])) for x in read(ART/'source-inventory.json')['article_roots']};captures=[];counts={a:[] for a in metrics};before={a:[] for a in metrics};acq={a:[] for a in metrics}
ledger_cases=cases+[{'id':'authoring-contract'}]
for arm in metrics:
 for c in ledger_cases:
  a=next((x for x in audit['cells'] if x['case_id']==c['id'] and x['arm']==arm),None);rec=StageLedgerRecorder(c['id'],arm,identity_canonicalizer)
  if a:
   acquired={(x[0],int(x[1])) for x in a['acquired_articles']};presented={(x[0],int(x[1])) for x in a['presented_articles']};assert presented<=acquired<=inventory
   rec.record_stage('source','source',sorted(inventory))
   rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),discard_reasons={x:'Not acquired before run ended; no legal absence inference' for x in inventory-acquired})
   rec.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),discard_reasons={x:'Original not observed in actual wire' for x in acquired-presented})
  else:
   acquired=set();presented=set()
   for sid,kind,parents in [('source','source',()),('acquired','retrieve',('source',)),('present','present',('acquired',))]:rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Build dependency failure or declared global stop; no model dispatch')
  captures.append(grade_capture(rec.capture(),[]));counts[arm].append(len(presented));before[arm].append(len(inventory) if a else 0);acq[arm].append(len(acquired))
m=read(ADR/'실험/manifest.json');ledger=build_experiment_artifact('ADR-'+str(number),m['experiment_id'],[build_run_artifact('run-001',captures,{a:['source','acquired','present'] for a in metrics})])
ledger['audit']={'meaning':'Canonical article-root acquired and literal-wire delivery counts; no independent golden recall claim.'};ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
lp=ART/('retrieval-stage-ledger-'+ledger['artifact_sha256'][:16]+'.json.gz')
if not lp.exists():write_raw_json(lp,ledger)
put(ART/'retrieval-stage-ledger-ref.json',{'path':str(lp.relative_to(ROOT)),'sha256':sha(lp)})
m['retrieval_accounting']={'changed':False,'corpus_total':len(inventory),'before_filter':{a:sum(v) for a,v in before.items()},'after_filter':{a:sum(v) for a,v in acq.items()},'presented_total':{a:sum(v) for a,v in counts.items()},'presented_mean':{a:statistics.mean(v) for a,v in counts.items()},'presented_p50':{a:statistics.median(v) for a,v in counts.items()},'presented_p95':{a:max(v) for a,v in counts.items()},'golden_recall':{a:None for a in metrics},'selectivity':{a:statistics.mean(v)/len(inventory) for a,v in counts.items()},'not_applicable_reason':'Same corpus, observed retrieval only; no independent gold recall','stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm=metrics,comparisons=pairs,judge_disagreements=0,usage={k:summary[k] for k in ('physical_calls','unknown','reported_cost_usd')},latency={'cells':[{'case_id':r['case_id'],'arm':r['arm'],'seconds':r['request_seconds']} for r in rows],'p95_population':None,'reason':'One attempt per fixed cell; no population p95 estimate'},error_taxonomy=semantic['errors']);put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
limits='소표본·기존 개발 질문·각1회. SQLite/외부 Qwen 시험이며 Oracle SQL 지연·GENOS 내부모델 성능이 아니다. 모델의 변동과 캐시/순서 영향을 통제한 반복시험이 아니므로 일반화하지 않는다. 원문/ACL/wire 및 완료 답변을 따로 판정한다.'
values=[semantic['conclusion_ko'],'사용자가 Qwen 온톨로지 구축과 활용 성능 확인을 요청했다. 초기 실패를 보존하고 구현·데이터·실답 효과를 분리한다.',json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'사전 동결 질문/순서/예산. 각 셀 독립 프로세스와 상태, 기본 최종검토 유지. 실제 provider 입력/출력과 오류를 원시 보존.','완료1347 작업528 동결; 선택 MAIN142 별도; 공개 상법 동일 원문 세대; Qwen3.8-27b FP8/추론none; Parasail 우선, 명시429에만 NearAI1회; 출력 cap 없음.',json.dumps({'build':build,'rows':rows,'pairs':pairs},ensure_ascii=False,indent=2),json.dumps(semantic,ensure_ascii=False,indent=2),json.dumps({k:summary[k] for k in ('physical_calls','unknown','reported_cost_usd','source_checks','delivered_checks','budget_matches')},ensure_ascii=False),semantic['conclusion_ko'],limits,'실험 중 제품변경0; 완료1347 작업수정은 별도. MAIN·원문·운영Gold·현장·메일 변경0. 실험용 생성물은 승인·게시되지 않았고 기존 승인묶음은 동일 바이트의 격리 복사본을 사용했다.','design/freeze.json 및 해당06_TOOLS/EXPERIMENTS/adr_'+str(number)+'의 실행기. 원시호출 재실행 금지. audit→semantic-review→finalize→archive→seal→adr_structure hash/status/validate --final/graph.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# Qwen 온톨로지 구축·활용 실제 확인\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 qv=['run-001; exact frozen code; see actual-cell mapping below',json.dumps(cases,ensure_ascii=False),'Stored Commercial Act originals; no grading answer supplied to product. Archived real investigation in build is an explicitly declared authoring input, not a hidden evaluation key.','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz and source-wire-audit.json; source coordinates/version preserved.','artifacts/usage-live/*/raw/call-*/request.json.gz and response.json.gz; build-live/raw if present. Exact saved provider inputs/outputs, including failures.','canonical/*.json.gz, generations.json, original runtime and archive inventory.','Offline source review semantic-review.json; no judge model, no response rewritten.',json.dumps({'rows':semantic['rows'],'build':build,'note':'Original scaffold use-charter-followup was replaced by existing365 in pre-call frozen live-cases/criteria; not executed as a hidden third question.' if number==1343 else ''},ensure_ascii=False)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,qv),1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 질문·판정\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-ontology-repair';OUT.mkdir(exist_ok=True)
report=semantic['conclusion_ko']+'\n\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n\n'+limits+'\n\n실제 답변\n'+'\n\n'.join(r['case_id']+' / '+r['arm']+'\n'+(ROOT/r['output_path']).read_text() for r in rows)
(OUT/f'ADR{number}_실제결과.txt').write_text(report)
print(json.dumps({k:summary[k] for k in ('status','physical_calls','unknown','reported_cost_usd','budget_matches')},ensure_ascii=False))
