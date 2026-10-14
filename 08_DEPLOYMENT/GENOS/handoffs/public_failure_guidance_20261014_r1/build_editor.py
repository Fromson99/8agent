from pathlib import Path
import ast,base64,hashlib,zlib
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_PUBLIC_FAILURE_GUIDANCE_20261014_R1'
diag=(R/'genos_diagnostics.py').read_bytes();packed=base64.b64encode(zlib.compress(diag,9)).decode()
editor='import base64 as _b64, hashlib as _hash, sys as _sys, types as _types, zlib as _zlib\n'+f'_raw=_zlib.decompress(_b64.b64decode({packed!r}))\nassert _hash.sha256(_raw).hexdigest()=={hashlib.sha256(diag).hexdigest()!r}\n'
editor+="_module=_types.ModuleType('genos_diagnostics');_module.__file__='<embedded genos_diagnostics>'\n_sys.modules['genos_diagnostics']=_module\nexec(compile(_raw,_module.__file__,'exec'),_module.__dict__)\n"
editor+='\n'+(R/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_text();ast.parse(editor,feature_version=(3,10));(O/(N+'_PASTE_ALL.txt')).write_text(editor)
print('EDITOR_BUILT '+str(len(editor.encode())))
