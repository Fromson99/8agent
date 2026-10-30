"""The full Flow skips PDF parsing/conversion; no preprocessor configuration."""
import hashlib,json
from pathlib import Path

POLICY={'pipeline_parser_mode':'skip','preprocessor_enabled':False,'pdf_conversion':False,
        'pdf_policy':'SKIP_BEFORE_PARSING','document_failure_policy':'verified-native-successes-only',
        'required_environment':[]}


def environment():
    # Fixed policy: stale R3-R6 environment values must not enable the parser.
    return 'skip',{'GENOS_PDF_PARSER':'skip','GENOS_PDF_CONVERSION':'off',
                  'GENOS_PREPROCESSOR_TRANSPORT':'disabled','STRUCTURE_RECIPE_VLM':'off'}


def inspect(root):
    code=hashlib.sha256((Path(root)/'CODE_PINS.json').read_bytes()).hexdigest()
    digest=hashlib.sha256(json.dumps({'code_sha256':code,**POLICY},sort_keys=True).encode()).hexdigest()
    return {'ready':True,'errors':[],'config_sha256':digest,**POLICY}


def require(root,expected=None):
    value=inspect(root)
    if expected is not None and value['config_sha256']!=expected:raise ValueError('PREPROCESSOR_CONFIG_CHANGED')
    return value
