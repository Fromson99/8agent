"""Verified standalone package entry; configure the existing authenticated host."""
import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
binding=json.loads((ROOT/'package-binding.json').read_text())
for name,expected in binding['files'].items():
    path=ROOT/name
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('Ontology UI package changed: '+name)
configured=os.environ.get('GENOS_ONTOLOGY_CODE_ROOT')
if configured and Path(configured).resolve()!=(ROOT/'code').resolve():
    raise RuntimeError('Package backend root mismatch; use this package code or rebuild the binding')
os.environ['GENOS_ONTOLOGY_CODE_ROOT']=str(ROOT/'code')
sys.path.insert(0,str(ROOT))
from ontology_console import main
main()
