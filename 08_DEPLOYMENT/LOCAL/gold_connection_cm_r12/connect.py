"""Independent R12 CM experiment entry; explicit GOLD config and grants."""
from pathlib import Path
import hashlib,json,os,runpy,sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
def main():
    runtime=json.loads((HERE/'runtime.json').read_text())
    for path,expected in runtime['runtime_files'].items():
        if sha(ROOT/path)!=expected:raise RuntimeError('GOLD_RUNTIME_CHANGED: '+path)
    entry=ROOT/runtime['entry']
    sys.dont_write_bytecode=True;os.environ['GOLD_WORKSPACE']=str(ROOT)
    sys.path.insert(0,str(entry.parent))
    sys.argv=[str(entry),'--config',str(HERE/'config_b03.json'),'--connection',str(Path.home()/'.local/state/8-agent/gold-r12-1208/readonly-connection.json'),'--scope',str(HERE/'documents.json'),'--channel','cm-r12',*sys.argv[1:]]
    runpy.run_path(str(entry),run_name='__main__')
if __name__=='__main__':main()
