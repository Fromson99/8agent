"""Offline completion of the single user-authorized attempt; no model calls."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');out=ART/'known-query/candidate'
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/n)==h for n,h in f['working_files'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert all(sha(ROOT/s['base_release']['code_root']/n)==h for n,h in s['base_release']['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
r=read(out/'result.json');q=read(out/'response.json') if (out/'response.json').exists() else {}
stop=read(ART/'stop.json') if (ART/'stop.json').exists() else None
b=q.get('body',{});assembly=b.get('assembly',{});answer=b.get('answer',{});agent=assembly.get('term_agent',{})
text=answer.get('text','').replace(' ','');headings=set();trace=[];links=[]
for p in sorted((out/'model').glob('call-*/request.json')):
    request=read(p)
    for msg in request.get('messages',[]):
        if msg.get('role')!='user':continue
        try:view=json.loads(msg['content']).get('view',{})
        except (ValueError,AttributeError):continue
        src=view.get('sources',[])
        if isinstance(src,dict) and 'table_rows' in src:src=[dict(zip(src['table_columns'],row)) for row in src['table_rows']]
        headings.update(x.get('heading','') for x in src if isinstance(x,dict))
    raw=read(p.with_name('response.json')) if p.with_name('response.json').exists() else {};v={}
    try:v=json.loads(raw['choices'][0]['message']['content'])
    except (KeyError,ValueError,IndexError):pass
    trace.append({'call':p.parent.name,'provider_error':(raw.get('error') or {}).get('code'),'choice':v.get('choice'),'fields':list(v),'claims':len(v.get('claims',[])),'gaps':v.get('gaps',[])})
    for x in sorted(p.parent.glob('*.json')):links.append(f'[{p.parent.name}/{x.name}](../artifacts/{x.relative_to(ART)})')
completed=q.get('status')==200
checks={'service_200':completed,'source434':any(x.get('id')=='article:816aee85d53f84a3b2f322dd' for x in assembly.get('context',[])),
 'ratios':('3분의2' in text or '2/3' in text) and ('3분의1' in text or '1/3' in text),'claims':bool(answer.get('claims')),
 'citation_integrity':agent.get('citation_integrity')=='ORIGINAL_SPANS','no_unrelated_company_read':not any('제585조' in h or '제576조' in h for h in headings)}
passed=all(checks.values()) if completed else None
guard=read(ART/'guard-result.json')
summary={'status':'EVALUATED' if completed else 'MODEL_EVALUATION_UNAVAILABLE','passed':passed,'checks':checks,'trace':trace,'headings':sorted(headings),
 'physical_calls':r['model_calls'],'service_status':q.get('status'),'seconds':r['seconds'],'stop':stop,'guard':guard,
 'usage':r['usage'],'outcome':agent.get('accepted_outcome'),'integrity':{'candidate_files':419,'working_files':419,'selected_release_files':419,'main_pointer_unchanged':True},
 'limits':['Single in-sample retry; no paired accuracy/latency comparison or MAIN qualification.','Native call cap8/retries0/wall480 differs from MAIN100 profile; retained from ADR0989.','Unchanged stop policy and guard inherit ADR0989 seven contract checks; no duplicate test or model batch.'],
 'main_changed':False,'genos_changed':False}
save(ART/'result.json',summary)
m=read(ADR/'실험/manifest.json');assert m['design']['success_criteria']==f['design']['success_criteria']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','historical_reference_only':True,'new_calls':0},'candidate':{'status':'complete','passed':passed,'physical_calls':r['model_calls'],'checks':checks}},comparisons=[],judge_disagreements=0,usage={'physical_calls':r['model_calls'],'successful_model_responses':len(r['usage'])},latency={'service_seconds':r['seconds'],'completed_answer':completed},error_taxonomy=[] if passed else [{'kind':(stop or {}).get('reason','frozen_gate_failure'),'result_path':str((ART/'result.json').relative_to(ROOT))}])
front=(ADR/'README.md').read_text().split('---',2)[1]
if passed is False:front=front.replace('status: Proposed','status: Rejected')
parts=[f'Original question retry: {r["model_calls"]} physical requests, service{q.get("status")}, passed={passed}. MAIN100 unchanged.',
 'User asked to retry after ADR0990 provider429. Product419files and the bounded stop policy remain unchanged; no new baseline or synthetic batch.',
 m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
 'Same frozen parent candidate, source generation, public permissions, Qwen3.8 Parasail FP8, reasoning none, no fallback. Exact model inputs and outputs linked below.',
 json.dumps({'passed':passed,'checks':checks,'headings':sorted(headings)},ensure_ascii=False,indent=2),
 json.dumps({'trace':trace,'stop':stop,'guard':guard},ensure_ascii=False,indent=2),
 f'Calls {r["model_calls"]}, service interval {r["seconds"]:.3f}s. Completed answer: {completed}. Failure duration cannot establish answer speed; no LLM judge.',
 'Assessment and tool choice remain separate. Prior-source opinion context enriches existing calls; no new review stage or full phase fusion.',
 '\n\n'.join(summary['limits']),
 'No promotion. MAIN100, work code and selected release unchanged. Preserve this attempt; any further model retry requires a new ADR.',
 '06_TOOLS/EXPERIMENTS/adr_0991/guard.py; completed output prevents in-place rerun. [Frozen design](artifacts/design-freeze.json) · [Result](artifacts/result.json).']
(ADR/'README.md').write_text('---'+front+'---\n\n# 추가 탐색 후보 재실행\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
row=m['questions'][0]
values=['run-001; candidate once; historical reference only.',json.dumps(read(ART/'known-request.json'),ensure_ascii=False,indent=2),m['design']['success_criteria'],
 '[Frozen product binding](../artifacts/design-freeze.json). Source inputs are retained in the exact model payloads.',
 'Unchanged retrieval implementation, no new recall measurement. Actual read headings in result.json.','\n\n'.join(links),
 'Existing native phases only; no model health-check or judge. See exact requests above.',
 'Offline original-span/call accounting; no product-visible answer key or model evaluator.',
 '[Full result and phase trace](../artifacts/result.json). Passed='+str(passed)+'; completed='+str(completed)+'.']
qp=ADR/'실험'/row['file'];qp.write_text('# known-special-resolution\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)));row['sha256']=sha(qp)
(ADR/'실험/README.md').write_text('# 실험 질문\n\n- [원래 상법 질문]('+row['file']+')\n')
save(ADR/'실험/manifest.json',m)
items=[]
for p in sorted(ART.rglob('*')):
    if p.is_file() and p!=ART/'manifest.json' and 'runtime' not in p.relative_to(ART).parts:
        items.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Exact frozen inputs, native outputs and failure/result accounting','contains_raw_prompts_and_outputs':'model' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0991','files':items})
(ADR/'RESULT.txt').write_text(f'원래 상법 질문 재실행: 모델 {r["model_calls"]}회, 서비스 상태 {q.get("status")}, 기준 통과 {passed}.\n중단 사유: {json.dumps(stop,ensure_ascii=False)}\n후속 사례 실행0. 답변 완료 여부: {completed}. 정확도·속도 비교와 MAIN 반영은 수행하지 않았다.\n후보·작업 코드·선택 릴리스419파일과 MAIN100 포인터 불변. GENOS 변경 없음.\n')
print(json.dumps({k:summary[k] for k in ('status','passed','physical_calls','service_status','seconds','stop','headings')},ensure_ascii=False))
