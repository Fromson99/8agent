"""Build the field TXT (bash + embedded python3) from diagnose.py."""
import ast
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
TXT = 'ORA22806_CHECK_R1.txt'


def build():
    source = (HERE / 'diagnose.py').read_bytes()
    for version in ((3, 8), (3, 9), (3, 11)):
        ast.parse(source, feature_version=version)
    text = (b"set -eu\nPYTHONIOENCODING=utf-8 python3 - \"$@\" <<'PY_ORA22806_DIAGNOSTIC'\n" + source +
            b"\nPY_ORA22806_DIAGNOSTIC\n")
    (HERE / TXT).write_bytes(text)
    files = [TXT, 'GUIDE.txt']
    (HERE / 'SHA256SUMS.txt').write_text(''.join(
        '%s  %s\n' % (hashlib.sha256((HERE / f).read_bytes()).hexdigest(), f) for f in files))


if __name__ == '__main__':
    build()
