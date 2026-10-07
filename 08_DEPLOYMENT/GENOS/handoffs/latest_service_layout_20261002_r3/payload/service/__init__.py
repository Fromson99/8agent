"""GENOS service package and local import share the root runtime module.

The root implementation remains the local/frozen release compatibility source.
Both service and service.service resolve to one module with one warmup/cache.
"""
import importlib.util
from pathlib import Path
import sys

_entry_directory = Path(__file__).resolve().parent
_backend_path = _entry_directory.parent / "service.py"
_spec = importlib.util.spec_from_file_location(__name__, _backend_path,
    submodule_search_locations=[str(_entry_directory)])
_runtime = importlib.util.module_from_spec(_spec)
sys.modules[__name__] = _runtime
sys.modules[__name__ + ".service"] = _runtime
try:
    _spec.loader.exec_module(_runtime)
except BaseException:
    sys.modules.pop(__name__ + ".service", None)
    raise
_runtime.obs.event(_runtime.log, "deployment.entry.loaded",
    entry_path=str(_entry_directory / "service.py"), backend_path=str(_backend_path),
    backend_sha256=_runtime.hashlib.sha256(_backend_path.read_bytes()).hexdigest(),
    implementation_requested=_runtime.os.environ.get("GENOS_RAG_IMPLEMENTATION", ""))
