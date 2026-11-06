"""Post-run audit index only; does not change any model inputs/results."""
from common import *
import re,statistics,shutil
assert (ART/'run-completed.json').exists(),'Runner must have terminated'
s=read(ART/'summary.json');aud=read(ART/'source-wire-audit.json');cases=read(DES/'live-cases.json');cases=[c for c in cases if c['id'] in read(DES/'criteria.json')['plan']['cases']];grades={x['id']:x for x in read(DES/'grading-only.json')}
s['integrity']={k:sum(len(a.get(k,[])) for a in aud['cells']) for k in ('source_mismatches','acl_violations','wire_mismatches')}
s['integrity'].update(source_checks=sum(a['source_checks'] for a in aud['cells']),delivered_checks=sum(a['delivered_checks'] for a in aud['cells']),all_budgets_match=all(a['budget_matches'] for a in aud['cells']))
s['main_unchanged']=read(DES/'baseline.json')['pointer']==read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
s['provider_metadata_url']='https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b/endpoints'
s['technical_verification']=read(ART/'technical-verification.json')
if (ART/'semantic-review.json').exists():s['semantic_review']=read(ART/'semantic-review.json')
put(RUN/'result.json',s)
m=read(ADR/'실험/manifest.json')
# The initial two scaffold index pages are retained; actual R4 questions get individual pages.
scaffold=ART/'initial-question-index';scaffold.mkdir(exist_ok=True)
for p in (ADR/'실험').glob('질문-*.md'):
 if p.name.endswith(('provider-screen.md','integration-r4.md')):shutil.move(str(p),scaffold/p.name)
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
m['questions']=[]
for i,c in enumerate(cases,1):
 ident=c['id'].lower();filename=f'질문-{i:03d}-{ident}.md';observations=[x for x in s['cells'] if x['case_id']==c['id']]
 vals=['run-001/matrix; independent provider sessions. Frozen R4 case '+c['id'],c['steps'][0]['question'] if c['steps'] else c['manual_action'],json.dumps(grades[c['id']],ensure_ascii=False),
 '### 회수·탈락 단계 원장 — run·arm별\n\nsource-wire-audit.json retains exact per-provider cells. retrieval-stage-ledger.json.gz is the explicit union of observed article identities per R4 case; not a provider comparison or independent repeat count.',
 '\n'.join('artifacts/public-live/'+x['cell']+'/raw/ (exact request.json.gz and response.json.gz)' for x in observations) or 'No model invocation for this case.',
 'Per-cell canonical/*.json.gz, generations.json, calls.json and runtime original/archival inventory. No original output rewritten.',
 'Original-source/ACL/wire/budget verification, separate manual semantics; no judge model and no answer-key product injection.',json.dumps(observations,ensure_ascii=False) if observations else c['execution']+'; unexecuted, never pass']
 (ADR/'실험'/filename).write_text('# '+c['id']+'\n\n'+'\n\n'.join(f'## {j}. {h}\n\n{v}' for j,(h,v) in enumerate(zip(qh,vals),1))+'\n')
 m['questions'].append({'number':i,'case_id':ident,'file':filename,'sha256':sha(ADR/'실험'/filename)})
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
inventory={(x[0],int(x[1])) for x in read(ART/'source-inventory.json')['article_roots']};captures=[];counts=[];acq_counts=[]
for c in cases:
 rows=[a for a in aud['cells'] if a['case_id']==c['id']]
 acq={(d,int(u)) for a in rows for d,u in a['acquired_articles']};pre={(d,int(u)) for a in rows for d,u in a['presented_articles']}
 assert pre<=acq<=inventory
 rec=StageLedgerRecorder(c['id'].lower(),'repaired',identity_canonicalizer)
 if rows:
  rec.record_stage('source','source',sorted(inventory))
  rec.record_stage('acquired','retrieve',sorted(acq),parent_stage_ids=('source',),discard_reasons={x:'Not acquired in observed cells; no legal absence inference' for x in inventory-acq})
  rec.record_stage('present','present',sorted(pre),parent_stage_ids=('acquired',),discard_reasons={x:'Not witnessed in actual provider input' for x in acq-pre})
 else:
  skip={'executed':False,'skip_reason':c['execution']+' or provider screening failed; no call'}
  rec.record_stage('source','source',[],**skip);rec.record_stage('acquired','retrieve',[],parent_stage_ids=('source',),**skip);rec.record_stage('present','present',[],parent_stage_ids=('acquired',),**skip)
 captures.append(grade_capture(rec.capture(),[]));counts.append(len(pre));acq_counts.append(len(acq))
ledger=build_experiment_artifact('ADR-1366',m['experiment_id'],[build_run_artifact('run-001',captures,{'repaired':['source','acquired','present']})])
ledger['audit']={'unit':'Per R4 question union across observed provider cells, not provider paired metric','per_provider_exact':'artifacts/source-wire-audit.json','unexecuted_not_failure_or_success':True}
ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
lp=ART/'retrieval-stage-ledger.json.gz';put(ART/'retrieval-stage-ledger-ref.json',write_raw_json(lp,ledger));per=lambda v:{'baseline':None,'repaired':v};ordered=sorted(counts)
m['retrieval_accounting']={'changed':False,'corpus_total':len(inventory),'before_filter':per(len(inventory)*sum(bool([a for a in aud['cells'] if a['case_id']==c['id']]) for c in cases)),'after_filter':per(sum(acq_counts)),'presented_total':per(sum(counts)),'presented_mean':per(statistics.mean(counts)),'presented_p50':per(statistics.median(counts)),'presented_p95':per(ordered[round((len(ordered)-1)*.95)]),'golden_recall':per(None),'selectivity':per(statistics.mean(counts)/len(inventory)),'not_applicable_reason':'Diagnostic R4 identity unions; not a retrieval algorithm comparison. No approved gold recall.','stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'physical_calls':0},'repaired':s},comparisons=[],judge_disagreements=0,usage={k:s[k] for k in ('physical_calls','reported_cost_usd','unknown')},latency={'p50':None,'p95':None,'reason':'Small deployment screen, differing precision; incomplete outcomes retained'},error_taxonomy=[{'type':x['verdict'],'cell':x['cell']} for x in s['cells'] if x['verdict']!='EXPLANATION_REVIEW_REQUIRED'])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
brief=s.get('conclusion','Actual365/434 outcomes retained; explanatory answers and integrity separately reviewed.')
vals=[brief,'기존 Parasail/NearAI 공백 응답과 검토 실패; R4는 시험계획이며 기존60개 통과 결과가 없었다.',json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'Completed1363 plus ASSESS question-scope guidance and representation-consistent prompts; observed1365 extra-date gap retained. ParasailFP8,180/1800second caps;365then434.','Completed1363 plus completion_execution.py/need_continuity.py/source_work_review.py and derived pins. Same strict SSE observation; each original reviewed once, no legal decisions inferred. Qwen3.8 ParasailFP8 reasoningnone, reference_bundle_reviewON and separate advisory final_review_enabledFalse unchanged, source immutable. Working integration recorded separately.',json.dumps({k:v for k,v in s.items() if k not in ('cases','technical_verification')},ensure_ascii=False),json.dumps(s.get('semantic_review',s['cells']),ensure_ascii=False),json.dumps({'calls':s['physical_calls'],'unknown':s['unknown'],'reported_cost_usd':s['reported_cost_usd'],'integrity':s['integrity']},ensure_ascii=False),'Provider metadata or HTTP200 alone is not sufficient. Raw-only, clarification, timeout, unexecuted remain nonpasses.','No GENOS UI/internal-model access. Provider resource capacity not certified. BF16/FP8/unknown differences preclude provider-only causal claims. Single samples not reliability certification.','MAIN142, original DB, field GENOS and mail unchanged. Working integration is recorded separately in working-integration.json; no MAIN promotion.','bash 06_TOOLS/COMMANDS/INTEGRATION_ONECLICK.txt --status ; completed run is never resent. For a new run reserve/freeze a new ADR.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 조항 경로·응답 반복·동일 원문 연결 수정과 실제 답변\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
(ADR/'실험/README.md').write_text('# R4 실제 시험 인덱스\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
(ART/'최종결과.txt').write_text(brief+'\n\n'+json.dumps({k:s[k] for k in ('physical_calls','unknown','reported_cost_usd','selected_provider','integrity','cells')},ensure_ascii=False,indent=2)+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*'))
paths=[p for p in paths if p.is_file()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1366','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen experiment, raw outcomes and observer records; failed preparations retained','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz') or 'raw' in p.parts or 'canonical' in p.parts} for p in sorted(paths)]})
print('Final records prepared; run hash/status/validate/graph')
