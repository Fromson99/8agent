"""Read-only Tier 3 projection from discovered cards and exact READ records."""
import json


def inventory(repo):
    rows={}
    def add(value):
        if isinstance(value,list):
            for child in value:add(child)
        elif isinstance(value,dict):
            target=value.get('target')
            if isinstance(target,str) and value.get('document_name'):
                h=repo.db.execute('SELECT identity_json FROM navigation_handle WHERE handle=?',(target,)).fetchone()
                if h:
                    n=json.loads(h[0])
                    if n.get('document_id') in repo.binding['scope']['document_version_ids']:
                        key=(n['document_id'],str(n.get('unit_id')))
                        rows.setdefault(key,{'document_id':n['document_id'],'unit_id':n.get('unit_id'),
                            'document_name':value['document_name'],'coordinate':value.get('coordinate') or value.get('title') or '',
                            'target':target,'evidence_ids':[],'status':'DISCOVERED_NOT_READ'})
            for k,child in value.items():
                if k in ('items','targets'):add(child)
    for r in repo.db.execute('SELECT result_json FROM observation ORDER BY created_seq'):
        add(json.loads(r[0]))
    for e in repo.evidence():
        key=(e['document_id'],str(e['unit_id']))
        row=rows.setdefault(key,{'document_id':e['document_id'],'unit_id':e['unit_id'],
            'document_name':e['metadata']['document_name'],'coordinate':e['metadata'].get('heading',''),
            'target':None,'evidence_ids':[]})
        row['evidence_ids'].append(e['evidence_id']);row['status']='READ_UNSELECTED'
    selected=set();rejected=set();pending={}
    for h in repo.heads('source_selection',current=True):
        p=h['payload']
        if p['status']=='SELECTED':selected.add(p['evidence_id'])
        elif p['status']=='REJECTED':rejected.add(p['evidence_id'])
        else:pending[p['evidence_id']]=p['reason']
    output=[]
    for row in rows.values():
        ids=set(row['evidence_ids'])
        if ids & selected or ids and ids<=rejected:continue
        reasons=[pending[e] for e in ids if e in pending]
        if reasons:row.update(status='PENDING',reason=' / '.join(reasons))
        output.append(row)
    return sorted(output,key=lambda r:(r['document_name'],str(r['unit_id'])))
