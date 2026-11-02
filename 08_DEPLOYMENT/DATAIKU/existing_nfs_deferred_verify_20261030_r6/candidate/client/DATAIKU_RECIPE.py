"""Edit the four environment-specific values, then run in Dataiku Python."""
from pathlib import Path
import sys
import dataiku

PACKAGE_DIR = Path('/실제/경로/DATAIKU_PIPELINE_CLIENT_20261022_R1')
UPLOAD_FOLDER_ID = 'LEGAL_DATA_ZIP_IMPORT'
INPUT_DIR = Path('/실제/경로/legal_pipeline_inputs')
JOB_DIR = Path('/실제/경로/legal_pipeline_jobs/run_20261022_01')

sys.path.insert(0, str(PACKAGE_DIR))
from restore_inputs import restore
from dataiku_run import run_dataiku

upload = Path(dataiku.Folder(UPLOAD_FOLDER_ID).get_path())
if not (INPUT_DIR / 'restored-inputs.json').exists():
    print(restore(upload, INPUT_DIR))
# Add internal files to INPUT_DIR/01_DATA/RAW/internal/<name_team>/ before this call.
result = run_dataiku(INPUT_DIR, upload / 'PIPELINE_SUPPORT.zip', JOB_DIR)
print({key: value for key, value in result.items() if key != 'identity'})
