"""Install ZIP upload -> GENOS -> ORDS Agent -> Gold as the default path."""
from pathlib import Path


def install_pipeline(params, bootstrap):
    import dataiku
    from flow_install import validate, install
    from sample_setup import setup_table
    variables = dataiku.get_custom_variables()
    cfg = dict(params)
    cfg.setdefault('WORK_DIR', variables.get('AGENT_FLOW_WORK_DIR') or str(Path.home() / '.dataiku-agent-work'))
    cfg['INPUT_FOLDER_ID'] = cfg.get('INPUT_FOLDER_ID') or cfg['CODE_FOLDER_ID']
    cfg['SUPPORT_FOLDER_ID'] = cfg.get('SUPPORT_FOLDER_ID') or cfg['CODE_FOLDER_ID']
    cfg.setdefault('DATA_ZIP_NAME', 'LAW_SAMPLE_R2.zip')
    cfg.setdefault('SUPPORT_ZIP_NAME', 'SAMPLE_SUPPORT_R2.zip')
    cfg.update(ENVIRONMENT='PROD', INPUT_MODE='ZIP')
    validate(cfg)
    if not cfg['SUPPORT_FOLDER_ID']:
        raise ValueError('REAL_PIPELINE_SUPPORT_FOLDER_REQUIRED')
    setup_table(cfg)
    return install(cfg, bootstrap)
