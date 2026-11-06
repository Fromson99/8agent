from common import *
import shutil
aud=read(ART/'source-wire-audit.json');stop=read(ART/'STOP_reka.json');cells=[]
for a in aud['cells']:
    cell=ART/'public-live'/a['cell'];observed=read(cell/'result.json')
    calls=read(cell/'calls.json');active=sum(c['status']=='started' for c in calls)
    assert active==observed['unknown'] and a['budget_matches']
    a['unknown']=active
    state='UNKNOWN_AFTER_RESOURCE_STOP' if active else 'FINAL_REVIEW_REJECTED'
    cells.append({'case_id':a['case_id'],'cell':cell.name,'physical_calls':len(calls),'unknown':active,
                  'semantic_pass':False,'verdict':state,'turns':observed['turns']})
put(ART/'source-wire-audit.json',{**aud,'exit_reconciliation':'An in-flight started call at worker exit is UNKNOWN. Physical calls.json and request bytes remain unchanged.'})
plan=read(DES/'criteria.json')['plan']['cells']
missing=[c+'-'+p for p,ids in plan.items() for c in ids if not (ART/'public-live'/(c+'-'+p)).exists()]
assert len(cells)==2 and len(missing)==4
summary={'all_passed':False,'quality_certified':False,'diagnostic_cases_passed':0,'physical_calls':sum(c['physical_calls'] for c in cells),'unknown':1,'reported_cost_usd':sum(a['reported_cost_usd'] for a in aud['cells']),'selected_provider':None,'cells':cells,'not_started':missing,
    'conclusion':'계획 6건 중 REKA 의결권 원문 전용 1건. REKA 434조 두 번째 호출 도중 전역 스왑 증가 안전 기준으로 로컬 작업 종료, 원격 결과 UNKNOWN 1. 나머지 4건 미실행. 원래 요청 재전송 0.'}
put(ART/'summary.json',summary);put(ART/'run-completed.json',{'terminal':'RESOURCE_STOP','planned_cells':6,'completed_answers':0,'closed_worker':True,'unstarted':missing})
put(ART/'semantic-review.json',{'cases':cells,'unstarted':missing,'judging_model_calls':0,'product_response_rewritten':False})
(ART/'수정과_실제답변.txt').write_text(summary['conclusion']+'\n\nB03-12\n'+(ART/'public-live/B03-12-reka/turn-1/answer.txt').read_text())
dest=ART/'initial-question-index';dest.mkdir(exist_ok=True)
for p in (ADR/'실험').glob('질문-*-B0*-*.md'):shutil.move(str(p),dest/p.name)
print(summary['physical_calls'],summary['reported_cost_usd'],missing)
