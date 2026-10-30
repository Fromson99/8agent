from pathlib import Path
import sys,os,json,socket,signal
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1155-investigation-focus-offline';f=json.loads((A/'artifacts/design/freeze.json').read_text());S=R/f['code_root']
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(S),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
original=socket.socket.connect

def connect(sock,address):
 if sock.family in (socket.AF_INET,socket.AF_INET6):raise RuntimeError('Network disabled: offline synthetic test only')
 return original(sock,address)
socket.socket.connect=connect
signal.alarm(180)
sys.path[:0]=[str(S/'02_BACKEND'),str(R/'05_TESTS'),str(R/'05_TESTS/CONTRACTS'),str(R/'06_TOOLS/EXPERIMENTS/adr_1152')]
import pytest
sys.exit(pytest.main(['-o','pythonpath='+str(S/'02_BACKEND')+' '+str(R/'05_TESTS')+' '+str(R/'05_TESTS/CONTRACTS')+' '+str(R/'06_TOOLS/EXPERIMENTS/adr_1152'),'-q',str(R/'06_TOOLS/EXPERIMENTS/adr_1152/test_observed_native.py'),'--junitxml='+str(A/'artifacts/native-offline.xml')]))
