"""Package the new entry script; never rebuild or modify the pinned R1 ZIPs."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
NAME = "DATAIKU_PIPELINE_RUN_20261022_R2"
script = (HERE / "DATAIKU_PIPELINE_RUN.py").read_bytes()
compile(script, NAME + ".txt", "exec")
(HERE / (NAME + ".txt")).write_bytes(script)
names = [NAME + ".txt", "DATAIKU_PIPELINE_RUN.py", "GUIDE.txt", "WORK_CONTRACT.txt"]
if (HERE / "VALIDATION.json").exists():
    names.append("VALIDATION.json")
pins = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in names}
(HERE / "SHA256.json").write_text(json.dumps(pins, indent=2) + "\n")
with zipfile.ZipFile(HERE / (NAME + ".zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for name in [*names, "SHA256.json"]:
        z.write(HERE / name, NAME + "/" + name)
print(json.dumps({"zip": NAME + ".zip", "bytes": (HERE / (NAME + ".zip")).stat().st_size,
                  "sha256": hashlib.sha256((HERE / (NAME + ".zip")).read_bytes()).hexdigest()}))
