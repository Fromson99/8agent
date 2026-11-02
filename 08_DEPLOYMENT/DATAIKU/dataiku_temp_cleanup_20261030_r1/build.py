import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
source = (root / 'cleanup_temp.py').read_bytes()
compile(source, 'cleanup_temp.py', 'exec')
(root / 'CLEAN_DATAIKU_TEMP.txt').write_bytes(source)
package = root / 'DATAIKU_TEMP_CLEANUP_20261030_R1.zip'
with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('cleanup_temp.py', source)
    z.writestr('PACKAGE_FILES.json', json.dumps({
        'cleanup_temp.py': {'bytes': len(source), 'sha256': hashlib.sha256(source).hexdigest()}
    }, indent=2))
with zipfile.ZipFile(package) as z:
    assert z.read('cleanup_temp.py') == (root / 'CLEAN_DATAIKU_TEMP.txt').read_bytes()
    assert z.testzip() is None
files = {}
for name in ('DATAIKU_TEMP_CLEANUP_20261030_R1.zip', 'CLEAN_DATAIKU_TEMP.txt', 'GUIDE.txt'):
    raw = (root / name).read_bytes()
    files[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
(root / 'HANDOFF_FILES.json').write_text(json.dumps(files, indent=2) + '\n')
print(json.dumps(files, indent=2))
