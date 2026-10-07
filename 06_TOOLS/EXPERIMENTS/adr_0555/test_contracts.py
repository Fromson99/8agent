"""No-network candidate and scoped-authorization contracts."""
import copy, importlib.util, json, sys
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0555/catalogue-router/revisions/rev-002/snapshot'
spec=importlib.util.spec_from_file_location('catalogue_contract',C/'02_BACKEND/semantic_runtime/legal_agent/source_query_planning.py')
route=importlib.util.module_from_spec(spec);spec.loader.exec_module(route)
def value(mode):
 return {'mode':mode,'reason':'시험','answer':'안녕하세요.' if mode in ('DIRECT','OUT_OF_DOMAIN') else '',
         'law_names':[],'queries':['정관 변경'] if mode=='SEARCH' else [],
         'document_category':'all','browse_view':'documents','title_query':'','inspect_documents':False}
@pytest.mark.parametrize('mode',['DIRECT','OUT_OF_DOMAIN','BROWSE','SEARCH'])
def test_valid_route(mode):assert route.validate_catalogue(value(mode),['상법'])['mode']==mode
@pytest.mark.parametrize('mode,key,replacement',[
 ('DIRECT','queries',['상법']),('DIRECT','answer',''),('BROWSE','queries',['상법']),
 ('SEARCH','queries',[]),('SEARCH','answer','추측 법률 답'),('SEARCH','law_names',['비공개 계약서']),
 ('DIRECT','inspect_documents',True)])
def test_invalid_route(mode,key,replacement):
 v=value(mode);v[key]=replacement
 with pytest.raises(Exception):route.validate_catalogue(v,['상법'])
def test_original_query_contract_unchanged():
 v={'plans':[{'case_id':'one','law_names':['상법'],'queries':['정관 변경']}]}
 assert route.validate(v,[{'case_id':'one'}],['상법'])['one']['queries']==['정관 변경']
def test_product_and_synthetic_grants_are_distinct(tmp_path):
 sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
 import adr_structure as validator
 A=R/'04_EXPERIMENTS/ADR/ADR-0555-pecab-only-catalogue-routing'
 m=json.loads((A/'실험/manifest.json').read_text())
 if 'experiment_override' not in m['llm_policy']:pytest.skip('run after freeze')
 model,errors=validator._openrouter_scoped_benchmark_override(A,m,{'main_wiring':'unchanged'})
 assert (model,errors)==('qwen/qwen3.8-27b',[])
 wrong=copy.deepcopy(m);wrong['llm_policy']['llm_calls'][0]['class']='offline_benchmark_candidate'
 assert validator._openrouter_scoped_benchmark_override(A,wrong,{'main_wiring':'unchanged'})[1]
 wrong=copy.deepcopy(m);wrong['decision_eligible']=True
 assert validator._openrouter_scoped_benchmark_override(A,wrong,{'main_wiring':'unchanged'})[1]
