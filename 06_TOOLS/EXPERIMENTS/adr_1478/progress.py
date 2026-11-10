"""After every question: registered required articles acquired/cited so far, next to ADR-1477 (read only).

ADR-1477 used the standalone strings r1 (cm-028 differs in r2) and the r3 code; a reference, not a
like-for-like baseline. Writes
artifacts/gold-progress.txt. No model call; reference answers stay in the grading-only file."""
from common import *
import collect_review as cr, os, fcntl
cr.put=lambda *a,**k:None
OLD=DES/'adr1477-review-rows.json'
def short(t):return t['law'].replace('에 관한 법률','법').replace('자본시장과 금융투자업법','자본시장법')[-14:]+' '+t['article']
def main():
    old={r['case_id']:r for r in read(OLD)['rows']} if OLD.exists() else {};rows=cr.collect();lines=[];ta=tc=tt=oa=oc=0;gain=loss=0
    for r in rows:
        o=old.get(r['case_id']);req=[t for t in r['targets'] if t['role']=='required']
        was={(t['law'],t['article']):t['acquired'] for t in (o['targets'] if o else []) if t['role']=='required'}
        g=[short(t) for t in req if t['acquired'] and not was.get((t['law'],t['article']),False)]
        l=[short(t) for t in req if not t['acquired'] and was.get((t['law'],t['article']),False)]
        still=[short(t) for t in req if not t['acquired'] and not was.get((t['law'],t['article']),False)]
        ta+=r['required_acquired'];tc+=r['required_cited'];tt+=r['required_total'];oa+=o['required_acquired'] if o else 0;oc+=o['required_cited'] if o else 0;gain+=len(g);loss+=len(l)
        lines.append(f"{r['case_id']} [{r.get('provider_profile')}] HTTP {r['http_status']} 확보 {r['required_acquired']}/{r['required_total']} (1477 {o['required_acquired'] if o else '-'}) 인용 {r['required_cited']} (1477 {o['required_cited'] if o else '-'}) 호출 {r['physical_calls']} {round(r['request_seconds'] or 0)}초"
            +(' | 새로 찾음: '+', '.join(g) if g else '')+(' | 잃음: '+', '.join(l) if l else '')+(' | 계속 누락: '+', '.join(still) if still else ''))
    head=f"{len(rows)}/50문항 · 확보 {ta}/{tt} (같은 문항 ADR-1477 {oa}) · 인용 {tc} (ADR-1477 {oc}) · 새로 찾음 {gain} · 잃음 {loss} · 참고 비교"
    out=ART/'gold-progress.txt';lock=open(ART/'.gold-progress.lock','a+');fcntl.flock(lock,fcntl.LOCK_EX)
    tmp=ART/('.gold-progress.%d.tmp'%os.getpid());tmp.write_text(head+'\n'+'\n'.join(lines)+'\n');os.replace(tmp,out)
    print(head)
if __name__=='__main__':main()
