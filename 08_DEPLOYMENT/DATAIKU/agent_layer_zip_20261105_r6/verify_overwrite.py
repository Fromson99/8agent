"""Exercise exact R6 installer commits, byte identity, preservation and rollback."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def check():
    parent=HERE.parent/'agent_layer_return_20261105_r4'/'verify_overwrite.py'
    source=parent.read_text().replace('GENOS_AGENT_RETURN_R4.zip','GENOS_AGENT_ZIP_R6.zip').replace('GENOS_DEPLOY_R4.txt','GENOS_DEPLOY_R6.txt').replace('genos-agent-return-r4','genos-agent-zip-r6')
    ns={'__file__':str(HERE/'verify_overwrite.py'),'__name__':'_r6_installer_contract'}
    exec(compile(source,str(parent),'exec'),ns)
    return ns['check']()


if __name__=='__main__':print(json.dumps(check(),ensure_ascii=False,indent=2))
