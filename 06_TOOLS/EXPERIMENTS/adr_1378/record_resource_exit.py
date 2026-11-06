"""Close the local process record without manufacturing a provider response."""
from common import *
cell=ART/'public-live/B03-17-reka'
stop=read(cell/'resource-stop.json');calls=read(cell/'calls.json')
assert stop['provider_outcome_unknown'] and calls[-1]['status']=='started'
assert not (cell/'raw/call-002/response.json.gz').exists()
assert not (cell/'turn-1/response.json.gz').exists()
receipt={'case_id':'B03-17','provider':'reka','collector':'post-worker-exit','exit_code':125,
    'cause':stop['reason'],'turns':[],'physical_calls':len(calls),'unknown':1,
    'no_local_api_response':True,'provider_cancel_confirmed':False,'call_log_sha256':sha(cell/'calls.json'),
    'automatic_retry':False,'unreported_cost_unknown':True}
put(cell/'result.json',receipt)
put(ART/'STOP_reka.json',receipt)
