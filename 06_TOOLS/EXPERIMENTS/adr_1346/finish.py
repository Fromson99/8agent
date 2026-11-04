from common import *
import re
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-charter-review-retention-live';OUT.mkdir(exist_ok=True)
cases=read(DES/'live-cases.json');audit=read(ART/'source-wire-audit.json');semantic=read(ART/'semantic-review.json')
candidate=read(DES/'candidate-bounded.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/candidate['code_root']/n)==h for n,h in candidate['selected_files'].items())
assert all(sha(selected()/n)==h for n,h in baseline['release']['files'].items())
assert read(ART/'runtime-archives.json')['all_restore_hashes_verified']
turns=[];calls=[];resources=[]
for case in cases:
    base=ART/'public-live'/(case['id']+'-bounded')
    if not (base/'result.json').exists():continue
    turns.extend(read(base/'result.json')['turns']);calls.extend(read(base/'calls.json'))
    r=read(base/'resource-final.json');resources.append(r)
    assert r['selected_code_unchanged'] and r['candidate_code_unchanged']
    assert all(str(ROOT/candidate['code_root']) in p for p in r['loaded_modules'].values())
summary={'tested_parent':'ADR-1344/bounded; exact ADR-1342/checked product','frozen_files':528,'new_product_changes':0,
    'planned_independent_runs':2,'executed_runs':len(turns),'turns':turns,'semantic':semantic,'retention_audit':read(ART/'retention-audit-summary.json'),
    'physical_calls':len(calls),'http200':sum(c.get('http_status')==200 for c in calls),
    'unknown':sum(c.get('status')=='unknown' for c in calls),'http429':sum(c.get('http_status')==429 for c in calls),
    'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),
    'reported_tokens':sum((c.get('usage') or {}).get('total_tokens',0) for c in calls),
    'request_seconds':sum(t['request_seconds'] for t in turns),'model_seconds':sum(c.get('seconds',0) for c in calls),
    'source_checks':sum(a['source_checks'] for a in audit['cells']), 'delivered_checks':sum(a['delivered_checks'] for a in audit['cells']),
    'source_mismatches':sum(len(a['source_mismatches']) for a in audit['cells']),
    'acl_violations':sum(len(a['acl_violations']) for a in audit['cells']),
    'wire_mismatches':sum(len(a['wire_mismatches']) for a in audit['cells']),
    'budget_matches':all(a['budget_matches'] for a in audit['cells']),
    'duplicate_extra_model_calls':sum(t.get('duplicate',{}).get('extra_model_calls',0) for t in turns),
    'selected_main':142,'pointer_unchanged':baseline['pointer']==read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'source_storage':'SQLite','state_storage':'isolated SQLite','oracle_genos_tested':False,'quality_certified':False,
    'working_drift':{n:{'before':h,'after':sha(ROOT/n)} for n,h in baseline['working_before'].items() if sha(ROOT/n)!=h}}
put(RUN/'result.json',summary);put(OUT/'검증요약.json',summary)
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
m=read(ADR/'실험/manifest.json');inventory={(x[0],int(x[1])) for x in read(ART/'source-inventory.json')['article_roots']};captures=[];counts=[]
for a in audit['cells']:
    acquired={(x[0],int(x[1])) for x in a['acquired_articles']};presented={(x[0],int(x[1])) for x in a['presented_articles']}
    assert presented<=acquired<=inventory
    rec=StageLedgerRecorder(a['case_id'],'bounded',identity_canonicalizer)
    rec.record_stage('source','source',sorted(inventory))
    rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),discard_reasons={x:'Not acquired; no absence inference' for x in inventory-acquired})
    rec.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),discard_reasons={x:'Not delivered in actual input' for x in acquired-presented})
    captures.append(grade_capture(rec.capture(),[]));counts.append((len(acquired),len(presented)))
for case in cases:
    if any(a['case_id']==case['id'] for a in audit['cells']):continue
    rec=StageLedgerRecorder(case['id'],'bounded',identity_canonicalizer)
    skipped={'executed':False,'skip_reason':'Frozen global stop after unknown provider outcome; never executed'}
    rec.record_stage('source','source',[],**skipped)
    rec.record_stage('acquired','retrieve',[],parent_stage_ids=('source',),**skipped)
    rec.record_stage('present','present',[],parent_stage_ids=('acquired',),**skipped)
    captures.append(grade_capture(rec.capture(),[]));counts.append((0,0))
ledger=build_experiment_artifact('ADR-1346',m['experiment_id'],[build_run_artifact('run-001',captures,{'bounded':['source','acquired','present']})])
ledger['audit']={'meaning':'Prospective two independent sessions; skipped cell has executed=false and no candidates. Planned-cell descriptive metrics include its zero, never treat it as retrieval failure or successful execution.',
    'executed_case_count':len(audit['cells']),'skipped_cases':read(ART/'skipped-cells.json')['cells']}
ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
lp=ART/'retrieval-stage-ledger.json.gz';put(ART/'retrieval-stage-ledger-ref.json',write_raw_json(lp,ledger))
def per(v):return {'baseline':None,'bounded':v}
import statistics
presented_total=sum(p for a,p in counts);presented_values=sorted(p for a,p in counts)
# Stage-ledger uses nearest rank percentile; two-cell p95 is descriptive only.
import math
pct=lambda f:presented_values[max(0,math.ceil(f*len(presented_values))-1)]
m['retrieval_accounting']={'changed':False,'corpus_total':len(inventory),'before_filter':per(len(inventory)*len(audit['cells'])),
    'after_filter':per(sum(a for a,p in counts)),'presented_total':per(presented_total),'presented_mean':per(presented_total/len(counts)),
    'presented_p50':per(statistics.median(presented_values)),'presented_p95':per(pct(.95)),'golden_recall':per(None),'selectivity':per(presented_total/(len(inventory)*len(counts))),
    'not_applicable_reason':'Unchanged retrieval; executed acquisition/presentation only, no approved gold recall.',
    'stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'physical_calls':0},'bounded':summary},comparisons=[],judge_disagreements=0,
    usage={k:summary[k] for k in ('physical_calls','reported_cost_usd','reported_tokens','unknown')},
    latency={'request_seconds':summary['request_seconds'],'model_seconds':summary['model_seconds'],'p50':None,'p95':None,'reason':'Small probe; unfinished/skipped separated, no population inference'},error_taxonomy=semantic['error_taxonomy'])
put(ADR/'실험/manifest.json',m)
env='완료1342와 같은528파일·공개상법1·SQLite·Qwen3.8 FP8/추론none·Parasail 우선/확정429만 NearAI1회. 독립2세션 사전계획, 기본검토ON·온톨로지OFF·출력상한없음·요청당40/전체80상한. 조문번호/정답힌트 주입0. UNKNOWN 뒤 재전송0. 선택MAIN142 유지.'
cost=f"실행 {len(turns)}/2 · {summary['request_seconds']:.3f}초 · 물리{len(calls)}/정상{summary['http200']}/UNKNOWN{summary['unknown']} · 보고비용${summary['reported_cost_usd']:.9f} · 원문{summary['source_checks']}/전달{summary['delivered_checks']} · 원문/ACL/wire불일치 {summary['source_mismatches']}/{summary['acl_violations']}/{summary['wire_mismatches']} · 예산일치{summary['budget_matches']}"
answers=[]
for case in cases:
    p=ART/'public-live'/(case['id']+'-bounded')/'turn-1/answer.txt'
    answers.append(case['id']+': '+(p.read_text() if p.exists() else '사전 중단으로 미실행'))
notes=[semantic['conclusion_ko'],env,'질문: 정관을 변경할 때 주주총회 결의요건은 무엇인가요?', '\n'.join(semantic['findings_ko']),cost,'실제 응답\n'+'\n\n'.join(answers),
    '기술검사163통과/신규19는ADR1342의 결과이며 새 실모델 성공 횟수에 합산하지 않는다. 이번 두 세션은 알려진 같은 질문의 반복이며 일반화 평가가 아니다. 실제 호출에서 발동하지 않은 종료/보완 분기를 효과 입증으로 세지 않는다. 제품·MAIN·원문DB·현장·메일 변경0.']
(OUT/'실제질문_검증결과.txt').write_text('\n\n'.join(notes)+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[notes[0],'완료1344 통신 중단 이후 사용자가 새 독립 재실험과 확보 근거의 검토 탈락 확인을 요청. 완료1342 동일 코드로 실행.',json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'독립세션2회 동결. UNKNOWN 즉시 전역중단, 코드/질문 적응수정 없음.',env,json.dumps(summary,ensure_ascii=False),notes[3],cost,notes[0],notes[-1],'수정 작업코드는1342. 본ADR 제품수정/MAIN전환0. 미실행·실패를 성공으로 처리하지 않는다.','setup.py → live_public.py charter bounded --admission → charter/charter-repeat 순차(중단조건 우선) → audit.py/inspect_results.py/navigation_trace.py → semantic-review → archive_runtime.py → finish.py → hash/status/validate/graph. 실모델 재실행 금지.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if semantic['all_criteria_passed'] else 'Rejected'),front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 정관 질문 재실험과 확보 근거 검토 탈락 확인\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
    base=ART/'public-live'/(q['case_id']+'-bounded');executed=(base/'result.json').exists()
    vals=['run-001/bounded/rev001; '+('실행' if executed else '사전중단으로미실행'),cases[0]['steps'][0]['question'],'저장433/434와 수치·분모·동시충족의 오프라인 대조. 제품에 정답 힌트 없음.',
        '### 회수·탈락 단계 원장 — run·arm별\n\nretrieval-stage-ledger.json.gz와 source-wire-audit.json. 미실행은0개성공이아님.',
        str(base.relative_to(ROOT))+'/raw/ 실제 전송원문, canonical 별도 보존.' if executed else '실모델0·제품입출력없음.',
        'calls.json/generations.json 및 원문/탐색저널 runtime.tar.gz. 실패/UNKNOWN 포함.', '수동 의미 검토·기계 원문/ACL/wire 검증. 채점모델0.', json.dumps(semantic,ensure_ascii=False)]
    (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,vals),1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 질문 기록\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))+[p for p in OUT.glob('*') if p.is_file()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1346','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen1342 source, actual model records and source/navigation audits; all failures retained','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz') or 'raw' in p.parts or 'canonical' in p.parts} for p in sorted(paths)]})
print(json.dumps({k:summary[k] for k in ('physical_calls','unknown','request_seconds','reported_cost_usd','budget_matches')},ensure_ascii=False))
