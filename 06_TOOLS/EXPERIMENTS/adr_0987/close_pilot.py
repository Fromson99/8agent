"""Close the earlier single-call pilot; never present it as native agent E2E."""
from report_common import *
import sys,math
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import grade_capture,build_run_artifact,build_experiment_artifact
A=ROOT/'04_EXPERIMENTS/ADR/ADR-0984-cm-knowledge-reuse-pilot';art=A/'artifacts';run=art/'agent_layer/run-001-model'
m=read(A/'실험/manifest.json');raw=read(run/'result.json');sources={s['id']:s for s in read(art/'gold_layer/sources.json')};criteria=read(art/'offline/criteria.json')
arms=['baseline','evidence_bundle','structured_knowledge'];cases=read(art/'design/questions.json')
passes={'baseline':['cm-010','cm-036'],'evidence_bundle':['cm-008','cm-010','cm-036'],'structured_knowledge':['cm-051','cm-008','cm-010','cm-036']}
notes={'cm-051':{'baseline':'증권별 환산과 CB 단수 제외 누락','evidence_bundle':'증권별 환산 누락·인용 문자열 불일치','structured_knowledge':'준용 범위·증권별 환산·제외·간접 보유를 설명. 분모는 미확인 보존'},
 'cm-008':{'baseline':'세칙의3년·2년·사유 미확보','evidence_bundle':'두 요건·3년·2년·지정/폐지 사유 포함','structured_knowledge':'두 요건·3년·2년·지정/폐지 사유 포함'},
 'cm-038':{'baseline':'사전 사유문서·대면보고/보고서 작성 누락','evidence_bundle':'사전 사유문서는 보완했으나 대면보고/보고서 작성 누락','structured_knowledge':'사전 사유문서는 보완했으나 대면보고/보고서 작성 누락'},
 'cm-010':{a:'제6조제3항과 제13조제5항제1호의 보유제외 범위 설명' for a in arms},
 'cm-007':{'baseline':'사모취득·잔여 인수 포함 누락, 인용 문자열 불일치','evidence_bundle':'본문은 필수항목을 포함하나 인용 문자열 불일치로 기술적 미통과','structured_knowledge':'수량·기간·사모취득은 설명했으나 미청약 잔여 인수수량 포함 누락'},
 'cm-036':{a:'상근이사 원칙·담당 이사 부재시 업무 집행자 예외. 등기임원 자체의 별도 해석은 전문가 미검토' for a in arms}}
rows=[];graded=[];counts={a:[] for a in arms};capture_by={}
for row in raw['records']:
 cid=row['case_id'];arm=row['arm'];p=run/cid/arm;capture=read(p/'capture.json');capture_by[(cid,arm)]=capture
 gold=[{'doc_id':sources[s]['document_id'],'node':int(sources[s]['node'])} for s in criteria[cid]['source_ids']]
 graded.append(grade_capture(capture,gold));counts[arm].append(len(capture['stages'][-1]['after']))
 app=read(p/'application.json');out=read(p/'output.json')
 rows.append({**row,'core_pass':cid in passes[arm],'technical_valid':app['technical_status']=='valid','review':notes[cid][arm],
    'selected_knowledge':app.get('model_selected_knowledge_refs',[]),'whole_answer_certified':False})
runled=build_run_artifact('run-001',graded,{a:['source','select','present'] for a in arms});led=build_experiment_artifact('ADR-0984',m['experiment_id'],[runled]);put(art/'offline/retrieval-ledger.json',led)
usage={k:sum(u.get(k) or 0 for u in raw['usage']) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']}
summary={'status':'complete','native_e2e':False,'primary_unit':'Earlier question-derived packs; superseded by user source-first steering in ADR0987',
 'product_model_calls':raw['calls'],'technical_valid':sum(x['technical_valid'] for x in rows),'total_outputs':len(rows),'usage':usage,'rows':rows,
 'by_arm':{a:{'status':'complete','correct':len(passes[a]),'total':6,'accuracy':len(passes[a])/6,'criteria_met':len(passes[a])==6,
      'mean_seconds':statistics.mean(r['seconds'] for r in rows if r['arm']==a),'technical_valid':sum(r['technical_valid'] for r in rows if r['arm']==a)} for a in arms},
 'review':'Frozen required items and quote consistency; partial improvements retained; no independent legal review','main_changed':False}
put(art/'offline/review.json',summary)
m['runs'][0].update(status='complete',artifact_path=str((art/'offline/review.json').relative_to(ROOT)),sha256=sha(art/'offline/review.json'))
m['results'].update(status='complete',by_arm=summary['by_arm'],comparisons=[],judge_disagreements=0,usage={'product_model_calls':raw['calls'],'offline_evaluator_calls':0,**usage},
 latency={'by_arm':{a:summary['by_arm'][a]['mean_seconds'] for a in arms}},error_taxonomy=[{'case':r['case_id'],'arm':r['arm'],'note':r['review']} for r in rows if not r['core_pass']])
account=m['retrieval_accounting'];account.update(corpus_total=6,before_filter={a:36 for a in arms},after_filter={a:sum(counts[a]) for a in arms},
 presented_total={a:sum(counts[a]) for a in arms},presented_mean={a:statistics.mean(counts[a]) for a in arms},presented_p50={a:statistics.median(counts[a]) for a in arms},
 presented_p95={a:max(counts[a]) for a in arms},selectivity={a:statistics.mean(counts[a])/6 for a in arms},golden_recall={})
for a in arms:
 hits=total=0
 for c in cases:
  gold={(sources[s]['document_id'],int(sources[s]['node'])) for s in criteria[c['id']]['source_ids']};present={(x['doc_id'],x['node']) for x in capture_by[(c['id'],a)]['stages'][-1]['after']};hits+=len(gold&present);total+=len(gold)
 account['golden_recall'][a]=hits/total
account['stage_ledger']['sha256']=sha(art/'offline/retrieval-ledger.json');put(A/'실험/manifest.json',m)
table='| arm | 필수항목·인용 통과 | 평균 초 |\n|---|---:|---:|\n'+'\n'.join(f'|{a}|{len(passes[a])}/6|{summary["by_arm"][a]["mean_seconds"]:.2f}|' for a in arms)
parts=['단일 모델 호출 기반6문항×3arm의 사전 파일럿을 종료했다. 전체 에이전트 E2E가 아니며 후속 사용자 요청은 ADR0987에서 수행한다.',
 'CM 실패 로그에서 보완한 공개 원문·검토 지식을 명시적으로 전달하면 필수항목 누락이 줄어드는지 살폈다.',
 '[동결 입력·기준](artifacts/design/freeze.json), [평가 항목](artifacts/offline/criteria.json). 원문 인용 일치와 필수항목을 별도 기록했다.',
 'baseline은 루트 원문만, evidence_bundle은 연결 원문, structured_knowledge는 동일 연결 원문+검토 지식. 모든 arm은 독립1회 호출이다.',
 '공개 CM6·원문6개, Qwen3.8/Parasail FP8. seed3/reuse3 모두 알려진 사례이며 holdout 아님. 질의당1회 소비자라 native검색·재조사 전체 경로는 미실행.',
 table,
 'CM051 산정 세부항목과 CM008 세칙조건은 보완됐다. CM038 대면보고와 CM007 잔여수량처럼 이미 제공한 원문·지식에서도 누락이 남았다. 출력3건의 정확 인용 검사가 실패했다.',
 json.dumps({'calls':raw['calls'],'usage':usage,'technical_valid':summary['technical_valid'],'sampled_peak_rss_bytes':raw['sampled_peak_rss_bytes']},ensure_ascii=False,indent=2),
 '숏컷으로 근거를 전달하는 것과 모델이 전부 반영하는 것은 다르다. 추가 지식이 답변을 길게 만들어 지연이 늘기도 했다.',
 '작은 사전 선택 사례·단발 비교. 원문 기반 일차 저장 구조로 완성된 실험이 아니므로 이 결과를 목표 구조의 E2E 성능으로 설명하지 않는다.',
 'MAIN·Oracle·GENOS 변경 없음. 최초0호출 자원 중단과 이후 실제18호출을 별도 보존. 사용자 정정은 후속 ADR0987에 적용.',
 '완료된 입력·출력을 보존한다. [후속 원문 중심 E2E](../ADR-0987-cm-source-ontology-native-e2e/README.md). 새 모델 실행은 새 ADR이 필요하다.']
cp={c['id']:['run-001 three arms; each1model call',c['question'],json.dumps(criteria[c['id']],ensure_ascii=False),
 '[공개 원문과 지식](../artifacts/gold_layer/knowledge.json), [동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/offline/retrieval-ledger.json).',
 'agent_layer/run-001-model/'+c['id']+'/*/input.json,output.json; wire/call-*/ 원문·usage 보존.',
 '별도 router/compiler/retry 없음. 도구 기반 원문 검증과 계산 계약20개 검사.',
 '채점 모델0회. 동결된 필수항목과 정확인용을 자체 검토; 독립 심사 아님.',
 json.dumps([r for r in rows if r['case_id']==c['id']],ensure_ascii=False,indent=2)] for c in cases}
finish_documents(A,'CM 지식 재사용 단일 호출 파일럿',parts,cp);seal(A)
print(table)
