"""Give synthetic apps their explicit disposable runtime instead of MAIN layout.

The unchanged local WORKSPACE activation receipt binds an older workspace hash.
No production receipt/path or runtime behavior is patched by this test harness.
"""
from functools import wraps
from pathlib import Path


def pytest_configure(config):
    import semantic_runtime.app as app
    original=app.create_app
    @wraps(original)
    def create_app(root,generation,**kwargs):
        kwargs.setdefault('runtime_root', Path(root)/'90_RUNTIME/semantic')
        return original(root,generation,**kwargs)
    app.create_app=create_app
