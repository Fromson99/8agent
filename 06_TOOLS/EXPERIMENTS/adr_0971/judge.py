"""Offline only: paired semantic judge, never feeds product context."""
from common import *
import sys,time
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentCallError
SYSTEM='동일 질문에 대한 두 답변을 기준답변과 대조하라. 답변의 핵심 결론과 조건·예외·수치가 정확하고 요청한 쟁점을 충족하면 pass다. 문장 차이는 오류가 아니다. 중요한 누락이나 모순은 fail, 자료·기준답변의 버전 등으로 판정할 수 없으면 unknown이다. 검색률이나 답변 길이를 정답으로 간주하지 말라. A/B가 어떤 검색방식인지 알 수 없으며 독립적으로 판정하라.'
item={'type':'object','additionalProperties':False,'required':['verdict','reason'],'properties':{'verdict':{'enum':['pass','fail','unknown'],'type':'string'},'reason':{'type':'string'}}}
SCHEMA={'type':'object','additionalProperties':False,'required':['A','B'],'properties':{'A':item,'B':item}}
freeze=read(DES/'freeze.json');assert sha(Path(__file__))==freeze['files'][str(Path(__file__).relative_to(ROOT))]
refs={x['id']:x for x in read(DES/'offline-reference.json')};done=[]
assert not (RUN/'judge-summary.json').exists()
for i,case in enumerate(read(DES/'cases.json')):
    arms=['dense','dense-rerank'] if i%2==0 else ['dense-rerank','dense']
    paths=[RUN/case['id']/a/'result.json' for a in arms]
    if not all(x.exists() and read(x)['status']=='complete' for x in paths):continue
    results=[read(x) for x in paths];d=RUN/case['id']/'judge';assert not d.exists()
    c=ExperimentClient(ROOT,d/'raw',max_calls=1,max_output_tokens=2000,max_repairs=0)
    tick=time.monotonic();r={'case_id':case['id'],'labels':dict(zip(['A','B'],arms))}
    try:
        r['judgment']=c.generate(SYSTEM,{'question':case['question'],'reference':refs[case['id']]['reference_answer'],'as_of':'2026-08-27 references; source version checked in separate audit','A':results[0]['answer'],'B':results[1]['answer']},SCHEMA,phase='judge');r['status']='complete'
    except ExperimentCallError as exc:r.update(status='failed',error=str(exc))
    r.update(calls=c.calls,usage=c.usage,seconds=time.monotonic()-tick);put(d/'result.json',r);done.append(r)
    if r['status']!='complete':break
put(RUN/'judge-summary.json',{'pairs_judged':sum(x['status']=='complete' for x in done),'attempted':len(done),'calibration':'not performed; provisional same-model judge'})
