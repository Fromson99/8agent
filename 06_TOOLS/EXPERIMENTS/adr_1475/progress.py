"""After every question: how the registered required articles changed vs ADR-1470 (read only).

Writes artifacts/gold-progress.txt (one line per finished question, totals on top). No model call;
reference answers stay in the grading-only file and never enter product input."""
from common import *
import collect_review as cr, os, fcntl
cr.put=lambda *a,**k:None
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1470-main182-source-closure-r5-cm51-qwen/artifacts/review-input.json'
def short(t):return t['law'].replace('에 관한 법률','법').replace('자본시장과 금융투자업법','자본시장법')[-14:]+' '+t['article']
def main():
    old={r['case_id']:r for r in read(OLD)['rows']};rows=cr.collect();lines=[];ta=tc=tt=oa=oc=0;gain=loss=0
    for r in rows:
        o=old[r['case_id']];req=[t for t in r['targets'] if t['role']=='required']
        was={(t['law'],t['article']):t for t in o['targets'] if t['role']=='required'}
        g=[short(t) for t in req if t['acquired'] and not was[(t['law'],t['article'])]['acquired']]
        l=[short(t) for t in req if not t['acquired'] and was[(t['law'],t['article'])]['acquired']]
        still=[short(t) for t in req if not t['acquired'] and not was[(t['law'],t['article'])]['acquired']]
        ta+=r['required_acquired'];tc+=r['required_cited'];tt+=r['required_total'];oa+=o['required_acquired'];oc+=o['required_cited'];gain+=len(g);loss+=len(l)
        lines.append(f"{r['case_id']} 확보 {r['required_acquired']}/{r['required_total']} (1470 {o['required_acquired']}, 1465 {r['adr1465']['required_acquired']}) 인용 {r['required_cited']} (1470 {o['required_cited']}) 호출 {r['physical_calls']} {round(r['request_seconds'] or 0)}초"
            +(' | 새로 찾음: '+', '.join(g) if g else '')+(' | 잃음: '+', '.join(l) if l else '')+(' | 계속 누락: '+', '.join(still) if still else ''))
    head=f"{len(rows)}/51문항 · 확보 {ta}/{tt} (같은 문항 ADR-1470 {oa}) · 인용 {tc} (ADR-1470 {oc}) · 새로 찾음 {gain} · 잃음 {loss}"
    out=ART/'gold-progress.txt';lock=open(ART/'.gold-progress.lock','a+');fcntl.flock(lock,fcntl.LOCK_EX)
    tmp=ART/('.gold-progress.%d.tmp'%os.getpid());tmp.write_text(head+'\n'+'\n'.join(lines)+'\n');os.replace(tmp,out)
    print(head)
if __name__=='__main__':main()
