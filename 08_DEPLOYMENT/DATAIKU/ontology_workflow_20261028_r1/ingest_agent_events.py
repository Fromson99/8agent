"""Dataiku Python recipe: existing agent events → S3 work JSON and input queue.
Never approves, publishes, calls GENOS or accesses S3 from GENOS.
"""
import json,os

def ingest(rows,workflow):
    receipts=[]
    for row in rows:
        if row.get('kind')!='ONTOLOGY_WORK_INPUT':continue
        payload=row.get('payload_json',row.get('payload'))
        if isinstance(payload,str):payload=json.loads(payload)
        from semantic_runtime.contracts import digest
        if payload['input_hash']!=digest(payload['input']):raise ValueError('agent work input hash mismatch')
        receipts.append(workflow.enqueue(payload['input']))
    return receipts

def main():
    import dataiku
    from semantic_runtime.ontology_work.configuration import workflow
    variables=dataiku.get_custom_variables()
    config=variables['ontology_connection_config_path']
    os.environ['GENOS_RAG_ONTOLOGY_CONFIG']=config
    actor=dataiku.api_client().get_auth_info(with_secrets=False)['authIdentifier']
    work=workflow(actor=actor)
    dataset=dataiku.Dataset(variables['ontology_agent_event_dataset'])
    # The upstream dataset is the existing authorized agent-event export. Rows are
    # iterated, never loading full logs into a dataframe. Repeat runs deduplicate.
    receipts=ingest(dataset.iter_rows(),work)
    result={'version':'ontology-input-receipts-v1','rows':receipts}
    work.store.put(result)
    return {'queued':len(receipts)}

if __name__=='__main__':print(json.dumps(main(),ensure_ascii=False))
