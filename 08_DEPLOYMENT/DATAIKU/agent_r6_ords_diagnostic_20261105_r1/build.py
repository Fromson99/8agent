import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent


def build():
    source=(HERE/'diagnose.py').read_bytes()
    ast.parse(source,feature_version=(3,11))
    text=b"set -eu\npython3 - \"$@\" <<'PY_R6_ORDS_DIAGNOSTIC'\n"+source+b"\nPY_R6_ORDS_DIAGNOSTIC\n"
    (HERE/'GENOS_R6_ORDS_CHECK_R1.txt').write_bytes(text)
    with zipfile.ZipFile(HERE/'GENOS_R6_ORDS_DIAGNOSTIC_20261105_R1.zip','w') as z:
        z.writestr('diagnose.py',source,compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('MANIFEST.json',json.dumps({'files':{'diagnose.py':hashlib.sha256(source).hexdigest()},'purpose':'Read-only R6 ORDS diagnosis; no runtime replacement'}),compress_type=zipfile.ZIP_DEFLATED)


if __name__=='__main__':build()
