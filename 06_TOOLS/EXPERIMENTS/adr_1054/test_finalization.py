from copy import deepcopy
from finalize_records import observations_complete

def test_complete_requires_all_product_evaluation_and_integrity_receipts():
 s={'status':'COMPLETE_OBSERVATIONS','complete_observations':True,'completed_product_cells':111,'finished_evaluation_cases':37,'metrics_cells':111,'ledger_cells':111,'source_integrity_failure_cells':0,'stop':None,'fatal_cells':[]}
 assert observations_complete(s,{'status':'COMPLETE'})
 for k,v in {'status':'STOPPED','complete_observations':False,'completed_product_cells':110,'finished_evaluation_cases':36,'metrics_cells':110,'ledger_cells':110,'source_integrity_failure_cells':1,'stop':{'reason':'failure'},'fatal_cells':['failure']}.items():
  assert not observations_complete({**s,k:v},{'status':'COMPLETE'})
 assert not observations_complete(s,{'status':'STOPPED'})
