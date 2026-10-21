"""Execute exact delivered notebook/TXT with public fixtures and a fake relay."""
import ast
import contextlib
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import relay_check as m
import test_relay_check as fixtures


def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(fixtures.Tests)
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/"TEST_TRANSCRIPT.txt").write_text(stream.getvalue())
    assert result.wasSuccessful()
    core=(OUT/"relay_check.py").read_bytes()
    notebook=json.loads((OUT/"DATAIKU_LAW_API_20261015_R1.ipynb").read_bytes())
    codes=["".join(c["source"]) for c in notebook["cells"] if c["cell_type"]=="code"]
    assert len(codes)==8 and codes[1].endswith(core.decode())
    assert all(c["outputs"]==[] and c["execution_count"] is None for c in notebook["cells"] if c["cell_type"]=="code")
    runner=(OUT/"DATAIKU_LAW_API_20261015_R1_RUN.txt").read_text()
    curl=(OUT/"CURL_EQUIVALENT.txt").read_text()
    for name, code in [("Notebook"+str(i),code) for i,code in enumerate(codes)]+[("RUN",runner),("curl",curl)]:
        ast.parse(code,filename=name,feature_version=(3,9))
    class Session(fixtures.Session):
        def mount(self,*a,**kw): pass
    class Folder:
        def __init__(self):self.data={}
        def upload_data(self,n,b):self.data[n]=b
        def get_download_stream(self,n):return io.BytesIO(self.data[n])
    outcomes=[]
    for form in ("notebook", "standalone_txt"):
        law=gzip.decompress((OUT/"law_body.xml.gz").read_bytes())
        adm=gzip.decompress((OUT/"admrul_body.xml.gz").read_bytes())
        session=Session([fixtures.Response(law),fixtures.Response(b"<LawSearch><totalCnt>0</totalCnt></LawSearch>"),
                         fixtures.Response(fixtures.LIST),fixtures.Response(adm),fixtures.Response(law)])
        folder=Folder(); ns={"__name__":"__main__"}
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.requests,"Session",return_value=session), \
             patch("getpass.getpass",return_value="MOCK_CREDENTIAL_987"), \
             patch.dict(os.environ,{"LAW_OC":"MOCK_CREDENTIAL_987"}), \
             patch.object(m.time,"sleep"), patch.dict(sys.modules,{"dataiku":types.SimpleNamespace(Folder=lambda id:folder)}), \
             contextlib.redirect_stdout(io.StringIO()):
            old=os.getcwd()
            try:
                os.chdir(tmp)
                if form=="notebook":
                    for i,code in enumerate(codes):
                        exec(compile(code,form+str(i),"exec"),ns)
                        if i==0:ns["MANAGED_FOLDER_ID"]="MOCK_FOLDER"
                    exec(codes[4],ns) # second button press: no duplicate calls
                else:
                    exec(compile(runner,form,"exec"),ns)
                    exec(compile(runner,form,"exec"),ns)
                    ns["check"].export_to_dataiku("MOCK_FOLDER")
                check=ns["check"]
                assert len(session.calls)==5
                assert check.records["law_effective_body"]["status"]=="BODY_OK"
                assert check.records["admrul_body"]["status"]=="BODY_OK"
                assert all(args[1].startswith("https://45.101.64.86:8443/") for args,kw in session.calls)
                assert len(folder.data)==12
                assert all(b"MOCK_CREDENTIAL_987" not in val for val in folder.data.values())
                outcomes.append({"form":form,"calls":5,"second_execution_extra_calls":0,
                                 "managed_folder_files_roundtrip":12,"passed":True})
            finally:os.chdir(old)
    # Execute curl example without network; inspect stdin-only credential + request.
    with tempfile.TemporaryDirectory() as tmp, patch("getpass.getpass",return_value="MOCK_CREDENTIAL_987"), \
         patch("shutil.which",return_value="/usr/bin/curl"), \
         patch("subprocess.run",return_value=types.SimpleNamespace(returncode=0,stdout=fixtures.LAW+b"\n200")) as call, \
         contextlib.redirect_stdout(io.StringIO()):
        old=os.getcwd()
        try:
            os.chdir(tmp);ns={};exec(compile(curl,"CURL_EQUIVALENT.txt","exec"),ns)
            assert ns["_report"]["status"]=="BODY_OK"
            args,kw=call.call_args
            assert "MOCK_CREDENTIAL_987" not in " ".join(args[0])
            assert b"OC=MOCK_CREDENTIAL_987" in kw["input"]
            assert "--location" not in args[0] and "-k" not in args[0]
        finally:os.chdir(old)
    live=json.loads((OUT/"SAME_CODE_EXTERNAL_CHECK.json").read_bytes())
    assert live["physical_calls"]==5
    assert all(x["status"] in ("BODY_OK","LIST_OK") for x in live["records"])
    output={"status":"PASS","contract_tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
            "exact_deliverable_execution":outcomes,"curl_example_mock_execution":True,
            "python_3_9_syntax":True,"notebook_code_cells":8,"no_notebook_outputs_or_secrets":True,
            "same_code_public_api_calls":5,"same_code_public_api_all_passed":True,
            "relay_helper_sha256":hashlib.sha256(core).hexdigest(),
            "actual_samsung_relay":"NOT_ACCESSED","actual_dataiku":"NOT_ACCESSED","GENOS":"NOT_ACCESSED"}
    (OUT/"VALIDATION.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
