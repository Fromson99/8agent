"""Offline only; the product does not import this module or see expectations."""
import re

def grade(products,gold):
    result=[]
    for case in products:
        spec=gold[case['case_id']];checks=[];rows=case['turns']
        def check(i,kind,expected,observed,ok):checks.append({'turn':i,'kind':kind,'expected':expected,'observed':observed,'pass':bool(ok)})
        for row in rows:
            i=row['turn'];o=row['output'];text=(o.get('answer') or {}).get('text','');expected=spec['statuses'][i-1];allow=expected if isinstance(expected,list) else [expected]
            check(i,'status',allow,o.get('status'),o.get('status') in allow)
            proc=spec['procedure'][i-1]
            if proc:check(i,'procedure_token',proc,text,bool(re.search(r'(?<![A-Z])'+proc+r'(?![A-Z])',text)))
            if str(i) in spec.get('executed',{}):
                expected=spec['executed'][str(i)];check(i,'executed_stages',expected,o.get('executed'),expected==o.get('executed'))
            if str(i) in spec.get('targets',{}):
                session,ordinal=spec['targets'][str(i)];g=next((g for g in row['db']['goal'] if g['session']==session and g['ordinal']==ordinal),None)
                check(i,'target',[session,ordinal],o.get('goal_id'),g is not None and o.get('goal_id')==g['id'])
            if i in spec.get('inspect_turns',[]):check(i,'requested_natural_explanation','nonempty answer.text',text,bool(text.strip()))
            if i in spec.get('table_turns',[]):check(i,'markdown_table','pipe rows and separator',text,bool(re.search(r'\|[^\n]+\n\|?\s*:?-{3}',text)))
            if i in spec.get('unconfirmed_turns',[]):
                active=[k['id'] for k in row['db']['knowledge'] if k['status']=='ACTIVE'];check(i,'unconfirmed_not_published',[],active,not active)
            if i in spec.get('isolation_turns',[]):
                prev={g['id']:g for g in rows[i-2]['db']['goal']};cur={g['id']:g for g in row['db']['goal']};other=[gid for gid in prev if gid!=o.get('goal_id')]
                check(i,'unrelated_goals_unchanged',other,{gid:cur.get(gid,{}).get('revision') for gid in other},all(cur.get(gid)==prev[gid] for gid in other))
            if str(i) in spec.get('restore_turns',{}):
                origin=rows[spec['restore_turns'][str(i)]-1];expected=(origin['output'].get('state') or {}).get('facts');observed=(o.get('state') or {}).get('facts')
                check(i,'restored_fact_state',expected,observed,expected is not None and observed==expected)
            # Every published route must be complete and tied to current goal revision.
            goals={g['id']:g for g in row['db']['goal']};active=[r for r in row['db']['route'] if r['status']=='ACTIVE']
            check(i,'active_route_current',True,[{'goal':r['goal'],'revision':r['revision']} for r in active],all(r['goal'] in goals and r['revision']==goals[r['goal']]['revision'] and goals[r['goal']]['status']=='READY' and len(r['payload']['nodes'])==7 for r in active))
        result.append({'case_id':case['case_id'],'checks':checks,'passed':sum(c['pass'] for c in checks),'total':len(checks)})
    return result
