"""Execute the literal delivered notebook installation cell with the public SDK."""
from pathlib import Path
import io
import json
import sys
import types

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE/'payload/02_BACKEND'),str(HERE/'payload'),str(HERE/'tests'),'/tmp/a8-vector-sdk/dataiku_api_client-15.2.0']
from test_contracts import Backend,DSSProject
backend=Backend()
project=DSSProject(backend,'LEGAL_RAG')
fake=types.ModuleType('dataiku')
fake.Folder=lambda id:types.SimpleNamespace(get_download_stream=lambda p:io.BytesIO((HERE/p).read_bytes()))
fake.get_custom_variables=lambda:{}
fake.api_client=lambda:types.SimpleNamespace(get_default_project=lambda:project)
sys.modules['dataiku']=fake
# A fresh notebook kernel has no prior product modules loaded.
for name in list(sys.modules):
    if name.split('.')[0] in ('semantic_runtime','lawrag','vector_silver'):del sys.modules[name]
scope={}
exec(compile((HERE/'DATAIKU_INSTALL.txt').read_text(),'delivered-install-cell','exec'),scope)
cfg=scope['VECTOR_CFG']
assert cfg['load']=='load'
saved=backend.items['recipes']['LEGAL_04_VECTOR_SILVER_R3']['payload']
compile(saved,'installed-recipe','exec')
assert 'action="build"' in saved and "'load': 'load'" in saved
assert 'VECTOR_SILVER_CODE_20261029_R2.zip' in saved
compile((HERE/'DATAIKU_RUN.txt').read_text(),'delivered-run-cell','exec')
count=0
for p in (HERE/'payload').rglob('*.py'):
    compile(p.read_bytes(),str(p),'exec');count+=1
result={'strict_success':True,'literal_install_cell':True,'real_public_sdk':True,
        'recipe_compiled':True,'run_cell_compiled':True,'python_files_compiled':count,
        'field_dataiku':False,'model_calls':0}
(HERE/'DELIVERY_VALIDATION.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
