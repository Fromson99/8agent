"""Apply the established checkout/rollback contracts to the delivered R5 installer."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def check():
    parent = HERE.parent / 'agent_layer_return_20261105_r4' / 'verify_overwrite.py'
    source = parent.read_text().replace('GENOS_AGENT_RETURN_R4.zip', 'GENOS_AGENT_ORDS_R5.zip').replace('GENOS_DEPLOY_R4.txt', 'GENOS_DEPLOY_R5.txt').replace('genos-agent-return-r4', 'genos-agent-ords-r5')
    namespace = {'__file__': str(HERE / 'verify_overwrite.py'), '__name__': '_r5_installer_contract'}
    exec(compile(source, str(parent), 'exec'), namespace)
    return namespace['check']()


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False, indent=2))
