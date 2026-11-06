"""Close the predeclared run using completed audits and separate semantic grading."""
from common import *
import re,statistics
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
m=read(ADR/'실험/manifest.json');cases=read(DES/'live-cases.json');grades={g['id']:g for g in read(DES/'grading-only.json')}
audit=read(ART/'source-wire-audit.json')['cells'];sem=read(ART/'semantic-review.json')
notes={r['id']:r for r in sem['cases']};trace={r['case_id']:r for r in read(ART/'supervisor-trace.json')['cells']}
criteria=read(DES/'criteria.json')
inv={(did,int(uid)) for did,uid in read(ART/'source-inventory.json')['article_roots']}
captures=[];acq_counts=[];counts=[];rows=[];questions=[]
for i,case in enumerate(cases,1):
    cid=case['id'];ident=cid.lower();ref=grades[cid]
    a=next((r for r in audit if r['case_id']==cid),None)
    recorder=StageLedgerRecorder(ident,'reviewed',identity_canonicalizer)
    acq={(d,int(u)) for d,u in a['acquired_articles']} if a else set()
    presented={(d,int(u)) for d,u in a['presented_articles']} if a else set()
    assert presented<=acq<=inv
    if a:
        recorder.record_stage('source','source',sorted(inv))
        recorder.record_stage('acquired','retrieve',sorted(acq),parent_stage_ids=('source',),discard_reasons={x:'Not acquired during the independent session' for x in inv-acq})
        recorder.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),discard_reasons={x:'No witnessed provider delivery' for x in acq-presented})
    else:
        for stage,kind,parents in [('source','source',()),('acquired','retrieve',('source',)),('present','present',('acquired',))]:
            recorder.record_stage(stage,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Frozen provider or resource stop')
    captures.append(grade_capture(recorder.capture(),[]));acq_counts.append(len(acq));counts.append(len(presented))
    key=notes[cid];row={'case_id':cid,'started':bool(a),'semantic_pass':key['pass'],'review':key['review']}
    if a:
        cell=ART/'public-live'/a['cell'];v=read(cell/'result.json')['turns'][0]
        outcome=read(cell/'turn-1/response.json.gz')['body'].get('assembly',{}).get('term_agent',{}).get('accepted_outcome',{})
        display=read(cell/'turn-1/display-review-data.json')
        if key['pass']:
            assert a['budget_matches'] and not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches','unknown'))
            assert display['accepted_complete_answer'] and display['expected_blocks'] and not display['missing_blocks'] and v['duplicate']['extra_model_calls']==0
        row.update(cell=cell.name,provider=v['provider_id'],elapsed=v['request_seconds'],calls=a['physical_calls'],unknown=a['unknown'],
            reported_cost=a['reported_cost_usd'],http=v['http_status'],disposition=outcome.get('disposition'),coverage=outcome.get('answer_coverage'),
            matched_expected_blocks=display['matched_blocks'],total_expected_blocks=display['expected_blocks'],claims=display['claims'],
            supervisor_calls=len(trace[cid]['review_inputs']),
            checked_directives=[{k:r.get(k) for k in ('directive','accepted','cancelled','route_matches')} for r in trace[cid]['trace'] if r['kind']=='SUPERVISOR_DECISION'])
    rows.append(row)
    file='질문-%03d-%s.md'%(i,ident)
    sections=[('실행 메타',f'run-001 / reviewed. {row.get("provider","미실행")}. 제품 모델 qwen/qwen3.8-27b.'),('사용자 질문 원문',case['steps'][0]['question']),
        ('기준답변 — 채점 전용, 제품 입력 비공개',ref['expected']),('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz, artifacts/source-wire-audit.json. '+str({'source':len(inv) if a else 0,'acquired':len(acq),'presented':len(presented)})),
        ('제품 모델 호출 — run·arm별 실제 원문',('artifacts/public-live/'+a['cell']+'/raw/ 에 실제 전송·응답 또는 수신 중단 원문 보관.') if a else '선언된 중단 조건으로 미실행.'),
        ('중간 LLM 호출 — router/compiler/verifier/repair','artifacts/supervisor-trace.json 및 문항별 canonical/ 에 단계별 질문·선택·실행 결과 보관.' if a else '미실행.'),
        ('채점 호출과 반복 판정','채점 모델 호출 0. 동결한 원문 기준과 사용자에게 반환한 답변을 직접 대조.'),
        ('사례 최종 판정',key['review']+'\n\n'+json.dumps(row,ensure_ascii=False))]
    (ADR/'실험'/file).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{body}' for n,(h,body) in enumerate(sections,1))+'\n')
    questions.append({'number':i,'case_id':ident,'file':file,'sha256':sha(ADR/'실험'/file)})
m['questions']=questions
run=build_run_artifact('run-001',captures,{'reviewed':['source','acquired','present']})
ledger=build_experiment_artifact(m['adr_id'],m['experiment_id'],[run])
lp=ART/'retrieval-stage-ledger.json.gz';put(ART/'retrieval-stage-ledger-ref.json',write_raw_json(lp,ledger))
per=lambda x:{'baseline':None,'reviewed':x}
m['retrieval_accounting']={'changed':False,'corpus_total':len(inv),'before_filter':per(len(inv)*len(audit)),'after_filter':per(sum(acq_counts)),
    'presented_total':per(sum(counts)),'presented_mean':per(statistics.mean(counts)),'presented_p50':per(statistics.median(counts)),'presented_p95':per(sorted(counts)[round((len(counts)-1)*.95)]),
    'golden_recall':per(None),'selectivity':per(statistics.mean(counts)/len(inv)),'not_applicable_reason':'No approved article-root gold; exact separately frozen block anchors reviewed after the run.',
    'stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
s={'cases':rows,'passed':sum(r['semantic_pass'] for r in rows),'started':len(audit),'planned':len(cases),'conclusion':sem['conclusion'],
    'physical_calls':sum(a['physical_calls'] for a in audit),'unknown':sum(a['unknown'] for a in audit),'reported_cost_usd':sum(a['reported_cost_usd'] for a in audit),
    'reported_tokens':sum(a['reported_tokens'] for a in audit),'input_tokens_reported':0,'output_tokens_reported':0,
    'integrity':{k:sum(len(a[k]) for a in audit) for k in ('source_mismatches','acl_violations','wire_mismatches')},
    'source_checks':sum(a['source_checks'] for a in audit),'delivery_checks':sum(a['delivered_checks'] for a in audit),'budget_matches':all(a['budget_matches'] for a in audit),
    'experiment_changed_main':False,'pointer_at_report':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'quality_certified':False}
for a in audit:
    for c in read(ART/'public-live'/a['cell']/'calls.json'):
        u=c.get('usage') or {};s['input_tokens_reported']+=u.get('prompt_tokens',0);s['output_tokens_reported']+=u.get('completion_tokens',0)
put(RUN/'result.json',s);put(ART/'summary.json',s)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'physical_calls':0},'reviewed':s},comparisons=[],judge_disagreements=0,
    usage={k:s[k] for k in ('physical_calls','unknown','reported_cost_usd','input_tokens_reported','output_tokens_reported')},
    latency={'p50':None,'p95':None,'reason':'One independent attempt per case, no repeated-estimate latency quantiles.'},
    error_taxonomy=[{'case_id':r['case_id'],'type':notes[r['case_id']]['category']} for r in rows if not r['semantic_pass']])
put(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 질문별 실행 결과\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in questions)+'\n')
report=sem['conclusion']+'\n\n'+'\n\n'.join(c['case_id']+'  '+c['review'] for c in rows)
(ART/'사용자답변_품질검토.txt').write_text(report+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[sem['conclusion'],'이전에 원문 전용·잘못된 항 표기·조사 중단이 있었던 공개 질문을 선정했다.',json.dumps(criteria,ensure_ascii=False),'동결 작업본 단일 arm, 세 질문의 독립 요청. 미확정은 원장을 보존하고 제공자 송신 중단.',
    '수정된 서빙 528파일, 공개 SQLite 원문, Qwen3.8-27B 추론 none. 제공자·예산·질문 사전 동결.',report,'감시자 의도와 실제 행동은 [원장 대조](artifacts/supervisor-trace.json)에 분리했다.',
    json.dumps({k:s[k] for k in ('reported_cost_usd','physical_calls','unknown','reported_tokens','source_checks','delivery_checks','budget_matches','integrity')},ensure_ascii=False),
    '현재 답변 충족과 마지막 승인 경로의 실제 실행은 별도 판정했다.','소표본이며 동시 비교군·반복 안정성·GENOS 성능은 검증 범위 밖이다.',
    '이 시험의 MAIN 포인터 쓰기·현장 배포 0.','동일 입력·원응답은 artifacts/public-live, 재생산 가능한 실행기와 핀은 artifacts/design/freeze-public.json에 보관.']
front=(ADR/'README.md').read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if s['passed']==len(cases) else 'Rejected'),front)
(ADR/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' 이전 실패 문항 Qwen 재검증\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(heads,vals),1))+'\n')
print(s['started'],s['planned'],s['passed'],s['physical_calls'],s['reported_cost_usd'])
