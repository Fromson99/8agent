"""GENOS latest-image file entry: project_root/service/service.py.

Load the maintained v6 root runtime by exact path. Never resolve an unrelated
service module from the container's sys.path. The runtime keeps its own root.
"""
import hashlib
import importlib.util
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_PATH = _ROOT / "service.py"
_runtime = sys.modules.get("service")
if not (_runtime is not None and
        Path(getattr(_runtime, "__file__", "")).resolve() == _BACKEND_PATH and
        callable(getattr(_runtime, "service", None))):
    _name = "_genos_root_service"
    _runtime = sys.modules.get(_name)
    if _runtime is None:
        _spec = importlib.util.spec_from_file_location(_name, _BACKEND_PATH)
        _runtime = importlib.util.module_from_spec(_spec)
        sys.modules[_name] = _runtime
        try:
            _spec.loader.exec_module(_runtime)
        except BaseException:
            sys.modules.pop(_name, None)
            raise
    elif Path(_runtime.__file__).resolve() != _BACKEND_PATH:
        raise RuntimeError("GENOS service backend path differs")
service = _runtime.service
application = _runtime.application
_runtime.obs.event(_runtime.log, "deployment.entry.loaded",
    entry_path=str(Path(__file__).resolve()), backend_path=str(_BACKEND_PATH),
    backend_sha256=hashlib.sha256(_BACKEND_PATH.read_bytes()).hexdigest(),
    implementation_requested=_runtime.os.environ.get("GENOS_RAG_IMPLEMENTATION", ""))
