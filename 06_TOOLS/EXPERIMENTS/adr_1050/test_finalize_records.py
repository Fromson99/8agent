from copy import deepcopy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from finalize_records import complete_observations,flat_retrieval
import pytest
GOOD={'status':'COMPLETE_OBSERVATIONS','complete_observations':True,'completed_product_cells':111,'metrics_cells':111,'ledger_cells':111,'finished_evaluation_cases':37,'source_integrity_failure_cells':0,'stop':None,'fatal_cells':[]}
def test_complete_gate():assert complete_observations(GOOD,{'status':'COMPLETE'})
@pytest.mark.parametrize('field,value',[('complete_observations',False),('completed_product_cells',110),('metrics_cells',110),('ledger_cells',110),('finished_evaluation_cases',36),('source_integrity_failure_cells',1),('stop',{'reason':'provider'}),('fatal_cells',[1])])
def test_incomplete_never_finalized(field,value):
 s=deepcopy(GOOD);s[field]=value;assert not complete_observations(s,{'status':'COMPLETE'})
def test_stopped_service_never_finalized():assert not complete_observations(GOOD,{'status':'STOPPED'})
def test_ledger_flat_counts_use_final_stage():
 cases=[{'stages':[{'after_count':99},{'after_count':x,'before_count':x+1,'gold_after':1,'gold_total':2}]} for x in [1,3,5]]
 r=flat_retrieval({'runs':[{'arms':[{'arm_id':'baseline','cases':cases}]}]},100)
 assert r['presented_total']['baseline']==9 and r['presented_mean']['baseline']==3
 assert r['before_filter']['baseline']==12 and r['golden_recall']['baseline']==.5
 assert r['selectivity']['baseline']==.03
