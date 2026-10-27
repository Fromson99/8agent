"""Feedback binds source generations and runs; corrections remain proposals."""
from datetime import datetime,timezone
import json
import uuid
from .contracts import write,sha

def proposal_for(event):
    return {'schema_version':'term-runtime-v1','id':'proposal:'+event['id'].split(':',1)[1],
            'event_id':event['id'],'generation_id':event['generation_id'],'source_store_sha256':event['source_store_sha256'],
            'target':event['target'],'status':'PROPOSED','reason':event['reason'],'required_next_step':'REVIEW_AND_VALIDATE'}

def record_feedback(contracts,run_path,signal,reason,output_dir):
    run=json.loads(run_path.read_text());answer=run['answer'];ident=uuid.uuid4().hex
    event={'schema_version':'term-runtime-v1','id':'event:'+ident,'occurred_at':datetime.now(timezone.utc).isoformat(),
           'generation_id':answer['generation_id'],'source_store_sha256':answer['source_store_sha256'],
           'target':{'answer_id':answer['id'],'query_id':answer['query_id'],'run_path':str(run_path),'run_sha256':sha(run_path)},
           'signal':signal,'reason':reason}
    contracts.validate(event,'urn:8-agent:term-runtime-v1','Event')
    proposal=proposal_for(event)
    contracts.validate(proposal,'urn:8-agent:term-runtime-v1','Proposal')
    write(output_dir/(ident+'.json'),{'event':event,'proposal':proposal})
    return {'event':event,'proposal':proposal}
