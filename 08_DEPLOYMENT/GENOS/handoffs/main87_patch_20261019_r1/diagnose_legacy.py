"""Observe failing historical fixture response, without editing product behavior."""
import json,runpy,sys
from pathlib import Path
import pytest
H=Path(__file__).resolve().parent
observed=[]
class Diagnostics:
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self,item,call):
        result=yield
        report=result.get_result()
        if report.when!='call':return
        row={'nodeid':item.nodeid,'outcome':report.outcome,'error':str(call.excinfo.value) if call.excinfo else None}
        if call.excinfo:
            for entry in call.excinfo.traceback:
                values=entry.frame.f_locals
                response=values.get('result')
                if hasattr(response,'status_code') and hasattr(response,'json'):
                    row.update(http_status=response.status_code,response=response.json())
                transport=values.get('transport')
                if hasattr(transport,'phases'):row['phases']=transport.phases
        observed.append(row)
        (H/'WORKING_FAILURE_REPRO.json').write_text(json.dumps(observed,ensure_ascii=False,indent=2)+'\n')
original=pytest.main
def main(args,plugins=()):return original(args,plugins=[*plugins,Diagnostics()])
pytest.main=main
sys.argv[0]=str(H/'installed_contract_runner.py')
runpy.run_path(sys.argv[0],run_name='__main__')
