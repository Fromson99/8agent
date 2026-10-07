"""Read-only review of completed outputs against frozen failure criteria; no regrade."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0594-rag-chain-strict-contracts'

def main():
    run=ADR/'artifacts/run-001';result=json.loads((run/'result.json').read_text())
    summary={};issues=[]
    for arm in ['PARENT','STRICT']:
        unexpected=[];extra=[];bad_text=[];binding_errors=[];total=0
        for case in result['products']:
            for item in case['arms'][arm]:
                total+=1;t=item['product_input'];o=item['observed'];status=o['status']
                allowed={'ERROR'} if t.get('fault') else {'FIXTURE'} if t.get('action')=='wrong_link' else {'REUSED'} if t.get('action') in ('reuse','reingest') else {'READY','INSPECTED'}
                if status not in allowed:unexpected.append({'case':case['case_id'],'turn':item['turn'],'status':status,'reason':o.get('reason',o.get('error'))})
                if case['case_id']=='SEQ01' and 3<=item['turn']<=14 and o.get('executed')!=['COMPOSE']:
                    extra.append({'case':case['case_id'],'turn':item['turn'],'executed':o.get('executed'),'command':o.get('command')})
                for check in item.get('text_audits',[]):
                    if not check['consistent']:bad_text.append({'case':case['case_id'],'turn':item['turn'],'reason':check['reason'],'contradictions':check['contradictions']})
                b=item['measurement']
                if status in ('READY','INSPECTED','REUSED') and (o.get('route_id')!=b['route_id'] or o.get('route_goal')!=b['route_goal']):binding_errors.append({'case':case['case_id'],'turn':item['turn'],'expected':b,'observed_route':o.get('route_id')})
        contracts=[]
        for p in (run).glob('*/'+arm+'/chain.sqlite'):
            import sqlite3
            db=sqlite3.connect(p)
            for tid,payload in db.execute("SELECT turn_id,payload FROM receipt WHERE kind='ANSWER_CONTRACT'"):
                c=json.loads(payload);contracts.append({'case':p.parent.parent.name,'turn':tid,**c})
            db.close()
        summary[arm]={'turns':total,'unexpected_status_count':len(unexpected),'text_audit_failures':len(bad_text),'response_binding_failures':len(binding_errors),'unnecessary_reassessment_count':len(extra),'blocked_draft_count':sum(not c['accepted'] for c in contracts),'repair_attempts':sum(c['attempt']>0 for c in contracts)}
        issues.append({'arm':arm,'unexpected_status':unexpected,'text_failures':bad_text,'binding_failures':binding_errors,'unnecessary_reassessment':extra,'blocked_drafts':[c for c in contracts if not c['accepted']]})
    receipt={'review_kind':'Read-only diagnostic; frozen score and products unchanged','result_sha256':hashlib.sha256((run/'result.json').read_bytes()).hexdigest(),'summary':summary,'issues':issues,'generalization':'Same-model product verifier and offline evaluator are not independent legal correctness certification.'}
    (run/'diagnostic-audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
