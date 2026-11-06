"""Install the existing three-stage flow with the explicit production Gold target."""
from pathlib import Path


def install_pipeline(params, bootstrap):
    import dataiku
    from flow_install import validate, install
    from sample_setup import setup_table
    variables = dataiku.get_custom_variables()
    cfg = dict(params)
    cfg.setdefault('WORK_DIR', variables.get('AGENT_FLOW_WORK_DIR') or str(Path.home() / '.dataiku-agent-work'))
    cfg.setdefault('SUPPORT_FOLDER_ID', cfg['CODE_FOLDER_ID'])
    cfg.update(ENVIRONMENT='PROD', INPUT_MODE='LOOSE')
    validate(cfg)
    if not cfg['SUPPORT_FOLDER_ID']:
        raise ValueError('REAL_PIPELINE_SUPPORT_FOLDER_REQUIRED')
    setup_table(cfg)
    return install(cfg, bootstrap)
