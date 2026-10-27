"""Carry forward the sealed notebook failure checks to the new delivery."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
source=(HERE.parent/'pipeline_diagnostics_20261023_r2/test_notebook.py').read_text()
source=source.replace("BASE = HERE.parent / 'pipeline_mapped_20261023_r1'",'BASE = HERE')
source=source.replace('DATAIKU_PIPELINE_CLIENT_20261023_R1','DATAIKU_PIPELINE_CLIENT_20261027_R1')
source=source.replace('DATAIKU_PIPELINE_RUN_20261023_R2','DATAIKU_PIPELINE_RUN_20261027_R1')
source=source.replace("self.ns['run'](action, work_dir=", "self.ns['run'](action, folder_name='fixture-folder', work_dir=")
source=source.replace('test_complete_cell_inherits_actual_names_without_auto_run','test_new_target_cell_does_not_inherit_old_names_or_auto_run')
source=source.replace("('prepare','LEGAL_PIPELINE_WORKSPACE','actual-work','long-real-name')",
                      "('prepare','SET_S3_MANAGED_FOLDER_ID','./legal_pipeline_layers_20261027_r1','layers_20261027_r1')")
source=source.replace('SIDDA.LGL_DOC_VER.DOC_ID','SIDDS.LGL_DOC_VER_S.DOC_ID')
source=source.replace("HERE/'DATAIKU_PIPELINE_RUN_20261027_R1.zip'","HERE/'DATAIKU_PIPELINE_LAYERS_20261027_R1.zip'")
source=source.replace('z.read(RUNNER.name)',"z.read('DATAIKU_PIPELINE_LAYERS_20261027_R1/'+RUNNER.name)")
(HERE/'test_notebook.py').write_text(source)
