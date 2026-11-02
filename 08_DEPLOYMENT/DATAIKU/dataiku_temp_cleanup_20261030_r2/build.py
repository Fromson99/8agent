import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
source = (root / 'cleanup_large_archives.py').read_bytes()
compile(source, 'cleanup_large_archives.py', 'exec')
(root / 'CLEAN_DATAIKU_LARGE_ZIPS_R2.txt').write_bytes(source)
package = root / 'DATAIKU_LARGE_ZIP_CLEANUP_20261030_R2.zip'
members = {'cleanup_large_archives.py': {'bytes': len(source), 'sha256': hashlib.sha256(source).hexdigest()}}
with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('cleanup_large_archives.py', source)
    z.writestr('PACKAGE_FILES.json', json.dumps(members, indent=2))
with zipfile.ZipFile(package) as z:
    assert z.read('cleanup_large_archives.py') == (root / 'CLEAN_DATAIKU_LARGE_ZIPS_R2.txt').read_bytes()
    assert z.testzip() is None
    assert not any(Path(n).suffix.lower() in ('.zip', '.js', '.jsx', '.mjs', '.cjs') for n in z.namelist())
files = {}
for name in (package.name, 'CLEAN_DATAIKU_LARGE_ZIPS_R2.txt', 'GUIDE.txt'):
    raw = (root / name).read_bytes()
    files[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
(root / 'HANDOFF_FILES.json').write_text(json.dumps(files, indent=2) + '\n')
validation = {'python': '3.11', 'contracts_passed': 13, 'zip_txt_identical': True,
              'mutation_test_scope': 'synthetic files and mock managed folder; complete process visibility simulated',
              'actual_open_fd_guard': 'PASS', 'field_execution': False, 'field_deleted_bytes': None,
              'field_backup_existence': 'UNVERIFIED', 'capacity_sufficient_for_sort': 'UNVERIFIED'}
(root / 'VALIDATION.json').write_text(json.dumps(validation, indent=2) + '\n')
print(json.dumps(files, indent=2))
