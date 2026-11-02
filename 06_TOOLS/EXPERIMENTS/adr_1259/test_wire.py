from copy import deepcopy
import gzip,json
from pathlib import Path
import pytest
from semantic_runtime.ontology_work import wiki_model as model,wiki_contracts as wc
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.ontology_compiler import content_hash


def fixture():
 raw='raw-'+'a'*64
 source={'id':'external-name','anchor':{'document_id':'doc','version':'b'*64,'unit_id':'1','content_sha256':content_hash('①같은 말😀. 같은 말😀.'),'label':'가상 원문'},'text':'①같은 말😀. 같은 말😀.'}
 schema,bank=model.prepare({raw:{}},[],[source],lambda a:source['text'])
 sid=next(iter(bank))
 value={'operations':[{'op':'ADD_STATEMENT','target':'@s','value':{'text':'같은 말😀.','origin_refs':[raw],'source_basis':[{'source':sid,'quote':'같은 말😀.','occurrence':1}],'open_items':[]}}]}
 return schema,bank,value


def test_exact_second_unicode_quote_and_original_value_preserved():
 schema,bank,value=fixture();before=deepcopy(value);restored=model.restore(value,schema,bank)
 assert value==before
 basis=restored['operations'][0]['value']['source_basis'][0]
 assert basis['start_cp']==8 and basis['end_cp']==14
 wc.validate_basis(basis,lambda a:'①같은 말😀. 같은 말😀.',{'doc'})
 assert model.restore(value,schema,bank)==restored


@pytest.mark.parametrize('change',['fake_raw','source_as_raw','invalid_handle','wrong_kind','bad_quote','wrong_occurrence'])
def test_real_failure_classes_never_get_guessed_into_valid_changes(change):
 schema,bank,value=fixture();op=value['operations'][0]
 if change=='fake_raw':op['value']['origin_refs']=['invented']
 if change=='source_as_raw':op['value']['origin_refs']=[next(iter(bank))]
 if change=='invalid_handle':op['target']='@한글 제목'
 if change=='wrong_kind':op['op']='CREATE_ENTRY'
 if change=='bad_quote':op['value']['source_basis'][0]['quote']='없는 인용'
 if change=='wrong_occurrence':op['value']['source_basis'][0]['occurrence']=2
 with pytest.raises(ContractError):model.restore(value,schema,bank)


def test_actual_failed_response_is_rejected_without_repairs():
 schema,bank,_=fixture()
 p=Path('/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1255-wiki-workspace-oracle-live/artifacts/run-001/live/authoring/001-output.json.gz')
 value=json.loads(gzip.decompress(p.read_bytes()));before=deepcopy(value)
 with pytest.raises(ContractError):model.restore(value,schema,bank)
 assert value==before


@pytest.mark.parametrize('runner',['live.py','native.py'])
def test_usage_archival_keeps_both_completed_provider_responses(tmp_path,runner):
 # Execute only the archive function, never the live runner's top level.
 import ast,types
 script=Path(__file__).with_name(runner)
 tree=ast.parse(script.read_text())
 node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='compressed')
 def raw(path,value):
  with gzip.open(path,'wt') as f:json.dump(value,f)
 namespace={'json':json,'Path':Path,'raw':raw}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(script),'exec'),namespace)
 client=types.SimpleNamespace(_key='private-test-key',calls=1)
 path=tmp_path/'usage.json';fn=namespace['compressed']
 fn(client,path,{'physical_calls':1,'completed':True})
 client.calls=2;fn(client,path,{'physical_calls':2,'completed':True})
 saved=sorted(json.loads(gzip.decompress(p.read_bytes()))['physical_calls'] for p in tmp_path.glob('*.gz'))
 assert saved==[1,2]
 with pytest.raises(RuntimeError):fn(client,path,{'physical_calls':2})
