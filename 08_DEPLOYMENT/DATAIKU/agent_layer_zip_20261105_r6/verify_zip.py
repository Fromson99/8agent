"""ZIP input contracts using the exact delivered modules, without network calls."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

HERE=Path(__file__).resolve().parent


def check():
    cases=[]
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        for name,slot in [('GENOS_AGENT_ZIP_R6.zip','server'),('DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip','flow')]:
            with zipfile.ZipFile(HERE/name) as z:z.extractall(root/slot)
        sys.path[:0]=[str(root/'server'),str(root/'flow')]
        import archive_input as source
        import raw_zip_input as receiver
        import transport as t
        work=root/'work';work.mkdir()
        data=os.urandom(2*t.CHUNK+17)
        class Folder:
            def list_paths_in_partition(self):return ['/incoming/data.zip']
            def get_download_stream(self,name):
                assert name=='incoming/data.zip'
                return io.BytesIO(data)
        cfg={'DATA_ZIP_NAME':'incoming/data.zip','DATA_ZIP_SHA256':hashlib.sha256(data).hexdigest()}
        receipt=source.snapshot(Folder(),work,cfg)
        assert (work/'RAW_INPUT.zip').read_bytes()==data and receipt['bytes']==len(data)
        assert source.snapshot(Folder(),work,cfg)==receipt
        cases+=['multi_megabyte_existing_ZIP_exact_byte_copy','same_trial_same_ZIP_reused']
        data=b'x'+data[1:]
        try:source.snapshot(Folder(),work,dict(cfg,DATA_ZIP_SHA256=''))
        except ValueError as exc:assert str(exc)=='ZIP_INPUT_CHANGED_USE_NEW_TRIAL'
        else:raise AssertionError('changed source ZIP accepted')
        assert (work/'RAW_INPUT.zip').read_bytes()!=data
        cases.append('changed_ZIP_does_not_replace_saved_original')
        for name in ('../data.zip','/data.zip','data.txt','a\\data.zip'):
            try:source.archive_name(name)
            except ValueError:pass
            else:raise AssertionError('invalid ZIP path accepted')
        cases.append('invalid_or_non_ZIP_source_name_rejected')
        workspace=root/'plain';workspace.mkdir()
        archive=root/'plain.zip';raw='<법령>원문 바이트</법령>'.encode()
        with zipfile.ZipFile(archive,'w') as z:z.writestr('internal/test_team/법령.xml',raw)
        manifest=receiver.unpack(archive,workspace)
        assert (workspace/'01_DATA/RAW/internal/test_team/법령.xml').read_bytes()==raw
        assert manifest['metadata']['document_count']==1
        assert manifest['metadata']['source_zip_sha256']==t.sha(archive)
        assert receiver.unpack(archive,workspace)==manifest
        cases+=['ordinary_RAW_ZIP_unpacked_only_in_GENOS_with_exact_document_bytes','ordinary_ZIP_input_audit_and_repeat_identity']
        packaged=HERE.parent/'agent_layer_return_20261105_r4'/'LAW_SAMPLE_R2.zip'
        destination=root/'packaged';destination.mkdir()
        result=receiver.unpack(packaged,destination)
        assert result['metadata']['document_count']==1
        cases.append('existing_R4_data_transport_ZIP_supported_unchanged')
        for i,members in enumerate(({'../escaped.xml':raw},{'internal/test_team/link.xml':raw},
                                   {'internal/test_team/a.xml':raw,'01_DATA/RAW/internal/test_team/a.xml':raw},
                                   {'internal/test_team/a.xml.genos.json':b'{}'})):
            path=root/f'bad-{i}.zip'
            with zipfile.ZipFile(path,'w') as z:
                for name,value in members.items():
                    info=zipfile.ZipInfo(name)
                    if i==1:info.external_attr=0o120777<<16
                    z.writestr(info,value)
            target=root/f'bad-{i}';target.mkdir()
            try:receiver.unpack(path,target)
            except ValueError:pass
            else:raise AssertionError('unsafe or inconsistent RAW ZIP accepted')
        cases+=['traversal_blocked_before_extraction','ZIP_symlink_blocked','duplicate_canonical_RAW_path_blocked','orphan_sidecar_blocked']
    return {'status':'PASS','cases':cases}


if __name__=='__main__':print(json.dumps(check(),ensure_ascii=False,indent=2))
