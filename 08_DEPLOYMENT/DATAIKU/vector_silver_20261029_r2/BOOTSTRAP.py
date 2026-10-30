import dataiku,hashlib,io,json,pathlib,sys,tempfile,zipfile,atexit,shutil
_folder=dataiku.Folder("ehA8dpVm")
with _folder.get_download_stream("VECTOR_SILVER_CODE_20261029_R2.zip") as _stream:_raw=_stream.read(32*1024*1024+1)
if len(_raw)>32*1024*1024 or hashlib.sha256(_raw).hexdigest()!="5a3c0abed0e0a7cdf0dfc8ef595bbd6744107bff83c4d578d61142f2f45989b3":raise ValueError("VECTOR_CODE_HASH")
_root=pathlib.Path(tempfile.mkdtemp(prefix="legal-vector-code-"));atexit.register(shutil.rmtree,_root,ignore_errors=True)
with zipfile.ZipFile(io.BytesIO(_raw)) as _z:
 _names=_z.namelist()
 if len(_names)!=len(set(_names)) or sum(i.file_size for i in _z.infolist())>64*1024*1024:raise ValueError("VECTOR_ARCHIVE_SIZE_OR_DUPLICATE")
 _manifest=json.loads(_z.read("CODE_MANIFEST.json"))
 if set(_names)!=set(_manifest["files"])|{"CODE_MANIFEST.json"}:raise ValueError("VECTOR_ARCHIVE_NAMES")
 for _entry in _z.infolist():
  _p=pathlib.PurePosixPath(_entry.filename)
  if _p.is_absolute() or ".." in _p.parts or (_entry.external_attr>>16)&0o170000==0o120000:raise ValueError("VECTOR_ARCHIVE_PATH")
  if _entry.filename=="CODE_MANIFEST.json":continue
  _body=_z.read(_entry.filename)
  if hashlib.sha256(_body).hexdigest()!=_manifest["files"][_entry.filename]:raise ValueError("VECTOR_FILE_HASH")
  _dest=_root/_entry.filename;_dest.parent.mkdir(parents=True,exist_ok=True);_dest.write_bytes(_body)
# Refuse an already imported different package instead of mixing revisions in a notebook.
for _name in ("semantic_runtime","lawrag","vector_silver"):
 if _name in sys.modules:
  _loaded=pathlib.Path(sys.modules[_name].__file__).resolve()
  _relative=("02_BACKEND/" if _name!="vector_silver" else "")+_name+"/__init__.py"
  if not _loaded.is_relative_to(_root):raise ValueError("RESTART_NOTEBOOK_KERNEL_BEFORE_INSTALL: "+_name)
sys.path[:0]=[str(_root/"02_BACKEND"),str(_root)]
