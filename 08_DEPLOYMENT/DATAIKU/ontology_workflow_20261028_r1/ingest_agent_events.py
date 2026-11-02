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

def ingest_journal_page(db,workspace,*,after,metadata,authorize,limit=32):
    """Full immutable event history, including corrections; no implicit publication."""
    from semantic_runtime.ontology_work.observations import export_journal
    page=export_journal(db,after=after,limit=limit,authorize=authorize,metadata=metadata)
    receipts=[workspace.ingest(raw) for raw in page['events']]
    # A partial failure raises before a new checkpoint is returned. Re-ingest is idempotent.
    result={'version':'workspace-journal-receipts-v1','receipts':receipts,
            'checkpoint':page['checkpoint'],'page_full':page['page_full'],
            'stage':'RAW_STORED_NOT_APPROVED'}
    result_hash=workspace.store.put(result)
    return {**result,'receipt_hash':result_hash}

def ingest_workspace(rows,workspace):
    """Rows are authenticated export envelopes, not model-supplied source receipts."""
    for row in rows:
        raw=row.get('raw_envelope',row)
        if isinstance(raw,str):raw=json.loads(raw)
        yield workspace.ingest(raw)

def main():
    import dataiku
    from semantic_runtime.ontology_work.configuration import workflow,workspace_workflow
    variables=dataiku.get_custom_variables()
    config=variables['ontology_connection_config_path']
    os.environ['GENOS_RAG_ONTOLOGY_CONFIG']=config
    actor=dataiku.api_client().get_auth_info(with_secrets=False)['authIdentifier']
    free=variables.get('ontology_ingest_mode')=='workspace'
    work=workspace_workflow(actor=actor) if free else workflow(actor=actor)
    dataset=dataiku.Dataset(variables['ontology_agent_event_dataset'])
    # The upstream dataset is the existing authorized agent-event export. Rows are
    # iterated, never loading full logs into a dataframe. Repeat runs deduplicate.
    receipts=list(ingest_workspace(dataset.iter_rows(),work)) if free else ingest(dataset.iter_rows(),work)
    result={'version':'ontology-input-receipts-v1','rows':receipts}
    work.store.put(result)
    return {'queued':len(receipts)}

if __name__=='__main__':print(json.dumps(main(),ensure_ascii=False))
