import sys,json,importlib.util
from pathlib import Path
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
from common import *
from matrix import classify,eligible

def test_source_only_and_http_are_not_pass():
 assert classify({'turns':[{'http_status':200,'claims':0}]})=='SOURCE_ONLY_OR_INCOMPLETE'
 assert classify({'turns':[{'http_status':504,'claims':3}]})=='API_FAILED'
 assert classify({'unknown':1,'turns':[{'http_status':200,'claims':3}]})=='UNKNOWN'

def test_integrity_and_manual_semantics_are_required():
 r={'turns':[{'http_status':200,'claims':2}]}
 assert classify(r)=='AUDIT_REQUIRED'
 assert classify(r,{'budget_matches':False})=='INTEGRITY_FAILED'
 assert classify(r,{'budget_matches':True,'source_mismatches':[1]})=='INTEGRITY_FAILED'
 assert classify(r,{'budget_matches':True})=='EXPLANATION_REVIEW_REQUIRED'
 assert not eligible([{'verdict':'EXPLANATION_REVIEW_REQUIRED'}])
 assert eligible([{'verdict':'EXPLANATION_REVIEW_REQUIRED'}]*2)

def test_exact_sixty_no_grading_input():
 cases=read(DES/'live-cases.json')
 assert len(cases)==len({c['id'] for c in cases})==60
 assert sum(c['execution']=='PUBLIC_API' for c in cases)==31
 assert sum(c['execution']=='MANUAL_UI' for c in cases)==10
 assert all('anchors' not in c and 'expected' not in c for c in cases)

def test_frozen_routing_only_and_identity():
 C=ROOT/read(DES/'candidate-matrix.json')['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
 from semantic_runtime.legal_agent.provider_routing import validate_policy,route,validate_response
 for name in read(DES/'providers.json'):
  cfg=validate_policy(read(DES/('provider-'+name+'.json')));r=route(cfg['providers'][0])
  assert r['only']==r['order']==[cfg['providers'][0]['tag']]
  assert r['allow_fallbacks'] is False and r['require_parameters'] is True
  if name=='deepinfra':assert r['quantizations']==['bf16']
  if name=='cloudflare':assert 'quantizations' not in r
  try:validate_response({'provider':'Unexpected','model':cfg['model']},cfg['providers'][0],cfg['model'])
  except ValueError:pass
  else:raise AssertionError('provider mismatch accepted')

def test_unknown_provider_has_no_same_request_retry():
 s=(HERE/'matrix.py').read_text();assert 'if d.exists():return' in s
 assert "ART/('STOP_'+provider+'.json')" in s
 assert 'start_new_session=True' in s and 'proc.wait()' in s

if __name__=='__main__':
 for name,fn in list(globals().items()):
  if name.startswith('test_'):fn();print(name,'PASS')
