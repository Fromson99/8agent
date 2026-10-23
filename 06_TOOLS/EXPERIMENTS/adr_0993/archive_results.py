"""Archive the stopped run using the frozen member-by-member verification logic."""
from pathlib import Path
path=Path(__file__).with_name('archive_runtime.py')
source=path.read_text().replace("ART/'resource-run-001.json'", "ART/'run-001-resource.json'")
exec(compile(source,str(path),'exec'))
