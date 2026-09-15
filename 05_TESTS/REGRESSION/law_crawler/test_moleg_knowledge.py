import json
from pathlib import Path

import pytest

from lawrag.datasets.catalog import load_package
import lawrag.pipeline.collect_moleg_knowledge as collector
from lawrag.pipeline.collect_moleg_knowledge import _publish, parse_params
from lawrag.sources.moleg_knowledge import (
    ENDPOINTS,
    MolegKnowledgeClient,
    parse_xml_page,
    public_request_plan,
)


LIST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LawSearch>
  <totalCnt>2</totalCnt><page>1</page><display>1</display>
  <lstrm>
    <법령용어ID>1001</법령용어ID><법령용어명>금융투자업자</법령용어명>
    <법령용어한자>金融投資業者</법령용어한자>
    <법령용어정의>금융투자업을 영위하는 자</법령용어정의>
    <법령용어사전구분>법령정의</법령용어사전구분>
    <신규필드>보존됨</신규필드>
  </lstrm>
</LawSearch>"""


def test_parse_list_preserves_original_fields_and_pagination():
    parsed = parse_xml_page(LIST_XML, ENDPOINTS["legal_terms"])
    assert parsed.total_count == 2
    assert parsed.page_count == 2
    assert parsed.records[0]["source_id"] == "1001"
    assert parsed.records[0]["label"] == "금융투자업자"
    assert parsed.records[0]["definition"] == "금융투자업을 영위하는 자"
    assert parsed.records[0]["fields"]["신규필드"] == "보존됨"


def test_parse_relation_emits_one_record_per_edge_with_parent():
    xml = """<lstrmRltService><검색결과개수>1</검색결과개수><법령용어>
      <법령용어명>하도급계약</법령용어명>
      <연계용어><일상용어명>도급계약</일상용어명><용어관계>상위어</용어관계></연계용어>
      <연계용어><일상용어명>하도급</일상용어명><용어관계>연관어</용어관계></연계용어>
    </법령용어></lstrmRltService>"""
    parsed = parse_xml_page(xml, ENDPOINTS["legal_term_relations"])
    assert [row["label"] for row in parsed.records] == ["도급계약", "하도급"]
    assert all(row["fields"]["_기준용어명"] == "하도급계약" for row in parsed.records)


def test_article_terms_keep_article_coordinate_on_each_term():
    xml = """<joRltLstrmService><검색결과개수>1</검색결과개수><법령조문>
      <법령명>전기공사업법</법령명><조번호>0015</조번호><조가지번호>00</조가지번호>
      <연계용어><법령용어명>도급계약</법령용어명></연계용어>
    </법령조문></joRltLstrmService>"""
    parsed = parse_xml_page(xml, ENDPOINTS["article_terms"])
    assert parsed.records[0]["fields"]["_기준법령명"] == "전기공사업법"
    assert parsed.records[0]["fields"]["_기준조번호"] == "0015"
    assert parsed.records[0]["fields"]["_기준조가지번호"] == "00"


def test_knowledge_term_recovers_mst_from_relation_link():
    xml = """<lstrmAISearch><검색결과개수>1</검색결과개수><법령용어>
      <법령용어명>하도급계약</법령용어명>
      <용어간관계링크>/DRF/lawService.do?OC=REDACTED&amp;target=lstrmRlt&amp;MST=48269</용어간관계링크>
    </법령용어></lstrmAISearch>"""
    parsed = parse_xml_page(xml, ENDPOINTS["knowledge_terms"])
    assert parsed.records[0]["source_id"] == "48269"


def test_client_enforces_endpoint_contract_and_keeps_oc_out_of_plan():
    class Client:
        def get(self, *_args, **_kwargs):  # pragma: no cover - params test only
            raise AssertionError("network must not be called")

    api = MolegKnowledgeClient(Client(), "secret@example.com")
    params = api.params("legal_term_relations", {"query": "신탁", "relation": "synonym"})
    assert params["OC"] == "secret@example.com"
    assert params["target"] == "lstrmRlt"
    assert params["relation"] == "140301"
    plan = public_request_plan("legal_term_relations", {"query": "신탁"})
    assert "secret@example.com" not in json.dumps(plan, ensure_ascii=False)
    with pytest.raises(ValueError, match="다음 중 하나"):
        api.params("term_articles")
    assert api.params("legal_term_relations", {"MST": "1001"})["MST"] == "1001"
    with pytest.raises(ValueError, match="6자리"):
        api.params("article_terms", {"ID": "001234", "JO": "1"})


def test_fetch_redacts_oc_echoed_inside_response_links():
    class Response:
        status_code = 200
        text = LIST_XML.replace(
            "</lstrm>",
            "<법령용어상세링크>/DRF/lawService.do?OC=secret@example.com&amp;target=lstrm</법령용어상세링크></lstrm>",
        )

        def raise_for_status(self):
            return None

    class Client:
        def get(self, *_args, **_kwargs):
            return Response()

    xml, parsed = MolegKnowledgeClient(Client(), "secret@example.com").fetch("legal_terms")
    assert "secret@example.com" not in xml
    assert "OC=REDACTED" in xml
    assert "secret@example.com" not in json.dumps(parsed.records, ensure_ascii=False)


def test_cli_param_rejects_secret_and_duplicates():
    assert parse_params(["query=신탁"]) == {"query": "신탁"}
    with pytest.raises(ValueError, match="환경변수"):
        parse_params(["OC=secret"])
    with pytest.raises(ValueError, match="중복"):
        parse_params(["query=신탁", "query=회사"])


def test_publish_creates_non_exportable_verified_dataset_package(tmp_path: Path):
    work = tmp_path / "work"
    raw = work / "raw"
    raw.mkdir(parents=True)
    (raw / "page-000001.xml").write_text(LIST_XML, encoding="utf-8")
    plan = work / "request-plan.json"
    plan.write_text('{"authentication":"OC from environment"}\n', encoding="utf-8")
    normalized = work / "records.jsonl"
    normalized.write_text('{"label":"금융투자업자"}\n', encoding="utf-8")

    manifest_path = _publish(tmp_path, "legal_terms", work, plan, normalized)
    package = load_package(manifest_path, verify_files=True)
    assert package.dataset_id == "moleg-knowledge-legal-terms"
    assert package.export_allowed is False
    assert {artifact.role for artifact in package.artifacts} == {"raw", "lexical_index"}


def test_completed_collection_reuses_checkpoint_without_network(tmp_path: Path, monkeypatch):
    class Client:
        calls = 0

        def fetch(self, endpoint, values, *, page, display):
            self.calls += 1
            xml = LIST_XML.replace("<totalCnt>2</totalCnt>", "<totalCnt>1</totalCnt>")
            return xml, parse_xml_page(
                xml,
                ENDPOINTS[endpoint], requested_page=page, requested_display=display,
            )

    monkeypatch.setattr(
        collector, "runtime_path", lambda *parts: tmp_path / "runtime" / Path(*parts)
    )
    client = Client()
    first, checkpoint = collector._collect_endpoint(
        client, "legal_terms", {}, 100, 0, tmp_path,
    )
    second, repeated = collector._collect_endpoint(
        client, "legal_terms", {}, 100, 0, tmp_path,
    )
    assert first == second
    assert checkpoint["completed"] is True
    assert repeated["record_count"] == 1
    assert client.calls == 1


def test_collection_rejects_missing_rows_and_does_not_publish(tmp_path, monkeypatch):
    class Client:
        def fetch(self, endpoint, values, *, page, display):
            return LIST_XML, parse_xml_page(LIST_XML, ENDPOINTS[endpoint])
    monkeypatch.setattr(collector, 'runtime_path', lambda *parts: tmp_path / 'runtime' / Path(*parts))
    with pytest.raises(RuntimeError, match='레코드 수'):
        collector._collect_endpoint(Client(), 'legal_terms', {}, 100, 0, tmp_path)
    assert not (tmp_path / '01_DATA' / 'PACKAGES').exists()


def test_resume_uses_saved_page_after_checkpoint_interruption(tmp_path, monkeypatch):
    class Client:
        calls = 0
        def fetch(self, endpoint, values, *, page, display):
            self.calls += 1
            xml = LIST_XML.replace('<totalCnt>2</totalCnt>', '<totalCnt>1</totalCnt>')
            return xml, parse_xml_page(xml, ENDPOINTS[endpoint])
    monkeypatch.setattr(collector, 'runtime_path', lambda *parts: tmp_path / 'runtime' / Path(*parts))
    original = collector._atomic_json
    def interrupt(path, value):
        if path.name == 'checkpoint.json':
            raise OSError('simulated interruption')
        original(path, value)
    monkeypatch.setattr(collector, '_atomic_json', interrupt)
    client = Client()
    with pytest.raises(OSError):
        collector._collect_endpoint(client, 'legal_terms', {}, 100, 0, tmp_path)
    monkeypatch.setattr(collector, '_atomic_json', original)
    package, checkpoint = collector._collect_endpoint(client, 'legal_terms', {}, 100, 0, tmp_path)
    assert client.calls == 1
    assert checkpoint['record_count'] == 1
    assert package.is_file()


def test_catalog_variants_and_same_page_duplicates_survive_import(tmp_path, monkeypatch):
    from lawrag.pipeline.glossary_alignment import import_catalog
    def item(label):
        return f'<lstrm><법령용어ID>1,2</법령용어ID><법령용어명>{label}</법령용어명></lstrm>'
    xml = '<LawSearch><totalCnt>3</totalCnt>' + item('투자 신탁') + item('투자신탁') * 2 + '</LawSearch>'
    class Client:
        def fetch(self, endpoint, values, *, page, display):
            return xml, parse_xml_page(xml, ENDPOINTS[endpoint])
    monkeypatch.setattr(collector, 'runtime_path', lambda *parts: tmp_path / 'runtime' / Path(*parts))
    manifest, checkpoint = collector._collect_endpoint(Client(), 'legal_terms', {}, 100, 0, tmp_path)
    result = import_catalog(tmp_path / 'state', [manifest])
    terms = json.loads(Path(result['glossary']).read_text())['terms']
    assert checkpoint['record_count'] == 3
    assert len(terms) == 2
    assert {t['source']['source_id'] for t in terms} == {'1,2'}
    assert {t['term'] for t in terms} == {'투자 신탁', '투자신탁'}


def test_duplicate_across_pages_still_rejected(tmp_path, monkeypatch):
    class Client:
        def fetch(self, endpoint, values, *, page, display):
            xml = LIST_XML.replace('<page>1</page>', f'<page>{page}</page>')
            return xml, parse_xml_page(xml, ENDPOINTS[endpoint])
    monkeypatch.setattr(collector, 'runtime_path', lambda *parts: tmp_path / 'runtime' / Path(*parts))
    with pytest.raises(RuntimeError, match='중복'):
        collector._collect_endpoint(Client(), 'legal_terms', {}, 1, 0, tmp_path)
