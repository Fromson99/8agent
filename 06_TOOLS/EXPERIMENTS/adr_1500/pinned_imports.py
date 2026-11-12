"""Exact-module import routing to immutable experiment source, never mutable ROOT."""
import importlib.abc,importlib.util,sys,json,hashlib
from pathlib import Path
_PINS=None;_ROOT=None
class Finder(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname not in _PINS['modules']:return None
  item=_PINS['modules'][fullname];p=_ROOT/item
  return importlib.util.spec_from_file_location(fullname,p,submodule_search_locations=[str(p.parent)] if p.name=='__init__.py' else None)
def install(root):
 global _PINS,_ROOT
 _ROOT=Path(root).resolve();_PINS=json.loads((_ROOT/'transport-pins.json').read_text())
 for n in _PINS['modules']:
  if n in sys.modules:raise RuntimeError('UNPINNED_MODULE_ALREADY_LOADED:'+n)
 sys.meta_path.insert(0,Finder());verify_files()
def verify_files():
 for relative,expected in _PINS['files'].items():
  p=_ROOT/relative
  if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise RuntimeError('FROZEN_TRANSPORT_CHANGED:'+relative)
def verify_loaded(root):
 assert Path(root).resolve()==_ROOT;verify_files();loaded={}
 for name,relative in _PINS['modules'].items():
  module=sys.modules.get(name)
  if module is None:raise RuntimeError('PINNED_TRANSPORT_NOT_IMPORTED:'+name)
  if Path(module.__file__).resolve()!=(_ROOT/relative).resolve():raise RuntimeError('UNPINNED_MODULE_ORIGIN:'+name)
  loaded[name]={'path':str(module.__file__),'sha256':_PINS['files'][relative]}
 return {'loaded':loaded,'files':dict(_PINS['files']),'verified':True}
