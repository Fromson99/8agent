"""Reproduce a preexisting display-policy mismatch without tool recovery files."""
from pathlib import Path
import hashlib,json,os,sys,subprocess,tempfile,zipfile,xml.etree.ElementTree as E
O=Path(__file__).resolve().parent;R=O.parents[3]
kind=sys.argv[1]
fixture=next(x for x in json.loads((O/'FIXTURES.json').read_text()) if x['kind']==kind);archive=O/fixture['path']
assert hashlib.sha256(archive.read_bytes()).hexdigest()==fixture['sha256']
with tempfile.TemporaryDirectory(prefix='tool-recovery-legacy-display-') as td:
 code=Path(td)
 with zipfile.ZipFile(archive) as z:z.extractall(code)
 script='''from pathlib import Path
import sys,importlib,json
R=Path(sys.argv[1]);code=Path(sys.argv[2]);sys.dont_write_bytecode=True
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')]
for n in ('lawrag','lawrag.pipeline'):
 m=importlib.import_module(n);m.__path__.append(str(R/'02_BACKEND'/n.replace('.','/')))
plugin=importlib.import_module('conftest')
for n in ('test_investigation_diagnostics','test_genos_chat_flow','test_legal_agent_double_harness'):
 m=importlib.import_module(n)
 if getattr(m,'ROOT',None)==R:m.ROOT=code
import pytest
rc=pytest.main(['-q','--tb=short','--show-capture=no','-o','pythonpath=','--noconftest',str(R/'05_TESTS/CONTRACTS/test_investigation_diagnostics.py')+'::test_complete_scoped_diagnostics_remain_internal','--junitxml='+sys.argv[3]],plugins=[plugin])
for n,m in list(sys.modules.items()):
 if n.startswith('semantic_runtime') and getattr(m,'__file__',None):assert Path(m.__file__).resolve().is_relative_to(code),m.__file__
raise SystemExit(rc)
'''
 out=O/('failures/legacy-display-baseline-'+kind+'.xml')
 with (O/('failures/legacy-display-baseline-'+kind+'.log')).open('w') as log:
  p=subprocess.run([str(R/'.venv/bin/python'),'-c',script,str(R),str(code),str(out)],cwd=R,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'LAWRAG_WORKSPACE_ROOT':str(R),'LAWRAG_TOOL_WORKSPACE_ROOT':str(R)})
 cases=list(E.parse(out).iter('testcase'));assert p.returncode==1 and len(cases)==1 and cases[0].find('failure') is not None
 failure=cases[0].find('failure');assert "assert 'REFERENCE_TARGET_UNRESOLVED' not in rendered" in failure.text
 (O/('LEGACY_DISPLAY_BASELINE_'+kind+'.json')).write_text(json.dumps({'preexisting':True,'fixture':fixture,'test':cases[0].attrib,'message':failure.get('message'),'evidence':str(out.relative_to(O)),'cause':'Legacy full progress UI deliberately emits in-scope diagnostics. New compact-public default expectation does not match this unchanged older policy. Private cross-document records remain filtered.','code_changed':False},ensure_ascii=False,indent=2)+'\n')
print('Legacy display assertion reproduced before patch; runtime remained inside original inventory')
