import gzip
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import relay_check as m

LAW = '''<법령><기본정보><법령ID>010513</법령ID><법령명_한글>자본시장과 금융투자업에 관한 법률</법령명_한글><시행일자>20261002</시행일자></기본정보><조문><조문단위><조문내용>제1조 목적</조문내용></조문단위></조문></법령>'''.encode()
ADM = '''<AdmRulService><행정규칙기본정보><행정규칙일련번호>2100000285020</행정규칙일련번호><행정규칙명>금융투자업규정</행정규칙명></행정규칙기본정보><조문내용>제1조 목적</조문내용></AdmRulService>'''.encode()
LIST = '''<AdmRulSearch><totalCnt>1</totalCnt><admrul><행정규칙명>금융투자업규정</행정규칙명><행정규칙일련번호>2100000285020</행정규칙일련번호><현행연혁구분>현행</현행연혁구분></admrul></AdmRulSearch>'''.encode()


class Response:
    def __init__(self, raw=LAW, status=200):
        self.raw = raw
        self.status_code = status
        self.headers = {"Content-Type": "application/xml"}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def iter_content(self, size): yield self.raw


class Session:
    def __init__(self, values): self.values, self.calls = iter(values), []
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        value = next(self.values)
        if isinstance(value, Exception): raise value
        return value


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pause = patch.object(m.time, "sleep")
        self.pause.start()
        self.addCleanup(self.pause.stop)
    def check(self, values, **overrides):
        cfg = {"relay_origin":"https://relay.example:8443", "output_root":self.tmp.name,
               "law_name":"자본시장과 금융투자업에 관한 법률", "law_id":"010513",
               "admrul_name":"금융투자업규정"}
        cfg.update(overrides)
        return m.RelayCheck(cfg, "SYNTHETIC_SECRET_123", session=Session(values))
    def call(self, c, name="body"):
        return c.request(name, "lawService.do", "law", {"ID":"010513","type":"XML"}, "law_body",
                         "자본시장과 금융투자업에 관한 법률", "010513")
    def test_header_query_contract(self):
        c=self.check([Response()]); self.assertEqual(self.call(c)["status"],"BODY_OK")
        args, kw=c.session.calls[0]
        self.assertEqual(args,("GET","https://relay.example:8443/law/DRF"))
        self.assertEqual(kw["headers"]["target_url"],"http://www.law.go.kr/DRF/lawService.do?target=law")
        self.assertNotIn("target",kw["params"])
        self.assertTrue(kw["verify"]); self.assertFalse(kw["allow_redirects"])
    def test_target_query_mode(self):
        c=self.check([Response()],target_in_header=False); self.call(c)
        kw=c.session.calls[0][1]
        self.assertEqual(kw["params"]["target"],"law")
        self.assertNotIn("?",kw["headers"]["target_url"])
    def test_no_duplicate_success_or_failure(self):
        for response in (Response(),Response(b"<html>login</html>")):
            c=self.check([response]); self.assertEqual(self.call(c),self.call(c));self.assertEqual(c.calls,1)
    def test_reject_same_name_changed_input(self):
        c=self.check([Response()]);self.call(c)
        with self.assertRaises(ValueError): c.request("body","lawService.do","eflaw",{},"law_body")
    def test_html_200_not_success(self):
        c=self.check([Response(b"<html>login</html>")]);self.assertEqual(self.call(c)["status"],"REJECTED")
    def test_malformed_json_or_xml(self):
        for raw in (b"<broken",b'{"data":"XML"}'):
            c=self.check([Response(raw)]);self.assertEqual(self.call(c)["status"],"PARSE_ERROR")
    def test_redirect_not_followed(self):
        c=self.check([Response(b"redirect",302)]);self.assertEqual(self.call(c)["reason"],"REDIRECT_BLOCKED")
    def test_auth_blocks_next_call(self):
        c=self.check([Response(b"denied",403)]);self.call(c)
        self.assertEqual(self.call(c,"next")["status"],"BLOCKED_OR_BUDGET_EXHAUSTED");self.assertEqual(c.calls,1)
    def test_tls_timeout_no_retry(self):
        for exc,status in [(m.requests.exceptions.SSLError("secret URL"),"TLS_ERROR"),
                           (m.requests.exceptions.Timeout("secret URL"),"TIMEOUT")]:
            c=self.check([exc]);self.assertEqual(self.call(c)["status"],status);self.assertEqual(c.calls,1)
            self.assertNotIn("secret URL",(c.out/"summary.json").read_text())
    def test_wrong_body_identity(self):
        c=self.check([Response(LAW.replace(b"010513",b"999999"))]);self.assertEqual(self.call(c)["reason"],"BODY_ID_MISMATCH")
    def test_missing_article_and_dtd(self):
        for raw in ('<법령/>'.encode(), b'<!DOCTYPE x><x/>'):
            with self.assertRaises(ValueError):m.inspect_xml(raw,"law_body")
    def test_empty_list_distinct(self):
        r=m.inspect_xml(b"<LawSearch><totalCnt>0</totalCnt></LawSearch>","law_list")
        self.assertEqual(r["status"],"EMPTY_LIST")
    def test_partial_success_and_unsupported_eflaw(self):
        lawlist=b"<LawSearch><totalCnt>0</totalCnt></LawSearch>"
        c=self.check([Response(),Response(lawlist),Response(LIST),Response(ADM),Response(b"unsupported",404)])
        c.check_laws(); self.assertEqual(c.records["admrul_body"]["status"],"BODY_OK")
        self.assertEqual(c.records["law_effective_body"]["reason"],"HTTP_404")
        c.check_laws();self.assertEqual(c.calls,5)
    def test_no_arbitrary_adm_choice(self):
        c=self.check([Response(),Response(b"<LawSearch><totalCnt>0</totalCnt></LawSearch>"),
                      Response(b"<AdmRulSearch><totalCnt>0</totalCnt></AdmRulSearch>"),Response()])
        c.check_laws();self.assertEqual(c.records["admrul_body"]["status"],"SKIPPED_NO_UNIQUE_CURRENT_ID")
    def test_budget(self):
        c=self.check([]);c.calls=m.MAX_CALLS
        self.assertEqual(self.call(c)["status"],"BLOCKED_OR_BUDGET_EXHAUSTED")
        c=self.check([]);c.started-=901
        self.assertEqual(self.call(c)["status"],"BLOCKED_OR_BUDGET_EXHAUSTED")
    def test_redacted_response_hashes(self):
        c=self.check([Response(LAW+b"<!--OC=SYNTHETIC_SECRET_123-->")]);r=self.call(c)
        raw=gzip.decompress((c.out/r["response_file"]).read_bytes())
        self.assertNotIn(b"SYNTHETIC_SECRET_123",raw)
        self.assertTrue(r["credential_redacted"]);self.assertEqual(m.digest(raw),r["saved_sha256"])
        self.assertNotEqual(r["wire_sha256"],r["saved_sha256"])
    def test_size_and_inflight_preserved(self):
        with patch.object(m,"MAX_BYTES",4):
            c=self.check([Response()]);self.assertEqual(self.call(c)["reason"],"RESPONSE_SIZE_LIMIT")
    def test_export_saved_bytes_and_failure(self):
        class Folder:
            def __init__(self):self.data={}
            def upload_data(self,n,b):self.data[n]=b
            def get_download_stream(self,n):return io.BytesIO(self.data[n])
        folder=Folder();c=self.check([Response()]);self.call(c);c.table()
        with patch.dict(sys.modules,{"dataiku":types.SimpleNamespace(Folder=lambda id:folder)}):
            c.export_to_dataiku("fake")
            self.assertTrue(any(x.endswith("summary.json") for x in folder.data))
            folder.get_download_stream=lambda n:io.BytesIO(b"tampered")
            with self.assertRaises(RuntimeError):c.export_to_dataiku("fake")
    def test_real_public_body_fixtures(self):
        for name,kind,id in [("law_body","law_body","010513"),("admrul_body","admrul_body","2100000285020")]:
            raw=gzip.decompress((Path(__file__).parent/(name+".xml.gz")).read_bytes())
            r=m.inspect_xml(raw,kind,expected_id=id)
            self.assertEqual(r["status"],"BODY_OK");self.assertGreater(r["article_characters"],1000)
    def test_missing_notice_key_and_no_false_success(self):
        c=self.check([]);r=c.request("notice","ptcpAdmPp.xml","",{},"notice")
        self.assertEqual(r["status"],"MISSING_MAKING_OC");self.assertEqual(c.calls,0)
        self.assertEqual(m.inspect_xml(b"<response><count>0</count></response>","notice")["status"],"NOTICE_XML_REVIEW_REQUIRED")
    def test_ip_json_contract_no_guess(self):
        c=self.check([Response(b'{"result":{"ip":"192.0.2.1"}}')])
        r=c.request("ip_lookup","ip","",{"EXTR_INSN_SECT_CODE":"0"},"ip")
        self.assertEqual(r["status"],"IP_RESPONSE_REVIEW_REQUIRED")
        self.assertEqual(c.session.calls[0][1]["json"],{"EXTR_INSN_SECT_CODE":"0"})
    def test_reject_unsafe_config(self):
        for config in ({"ca_bundle":False},{"relay_origin":"http://relay.example"},{"law_origin":"https://bad.example"}):
            with self.assertRaises(ValueError):self.check([],**config)


if __name__ == "__main__":
    unittest.main()
