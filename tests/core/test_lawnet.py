"""법령 관계망 전사 — 조인·해소 규약 (lawrag/core/lawnet.py).

여기서 지키는 것 다섯:
  (1) 대상 법령은 명칭 완전일치로 잇는다 — 위임 데이터의 대상 MST 는 구판이라
      번호 조인이 성립하지 않는다 (실측: 현행 283193 vs 데이터 238305).
  (2) 스토어 조인은 본문 sha256[:16] == doc_id (lineage 와 같은 규약).
  (3) 조 좌표는 surface 완전일치 — "제34조의2" 가지조문 포함.
  (4) 대상 미보유 간선도 버리지 않는다 — dst.doc_id 가 null 로 남는다.
  (5) 제1조(목적)는 전사다 — 법령 XML 태그에서, 행정규칙 평문에서, 그대로.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core import lawnet  # noqa: E402


def _sha(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


LAW_XML = """<법령>
<조문단위><조문번호>1</조문번호><조문여부>조문</조문여부>
<조문내용>제1조(목적) 이 법은 갑 업무를 규율함을 목적으로 한다.
후속 줄은 인덱스에 싣지 않는다.</조문내용></조문단위>
</법령>"""

ADMRUL_XML = """<AdmRulService>
<조문내용>
제1편 총칙
제1-1조(목적) 이 규정은 갑법 위임 사항을 정함을 목적으로 한다.
제1-2조(정의) 용어의 뜻은 다음과 같다.
</조문내용></AdmRulService>"""

DELEGATED_XML = """<lsDelegated><법령>
<법령정보><법령일련번호>200</법령일련번호><법령ID>010001</법령ID>
<법령명>갑법 시행령</법령명></법령정보>
<위임조문정보>
  <조정보><조문번호>3</조문번호><조문제목>업무의 범위</조문제목></조정보>
  <위임정보>
    <위임구분>인용법령</위임구분>
    <위임법령일련번호>999</위임법령일련번호>
    <위임법령제목>갑법</위임법령제목>
    <위임법령조문정보><위임법령조문번호>34</위임법령조문번호>
      <위임법령조문가지번호>2</위임법령조문가지번호>
      <위임법령조문제목>준수사항</위임법령조문제목>
      <조항호목>제34조의2제1항</조항호목>
      <링크텍스트>법 제34조의2제1항</링크텍스트></위임법령조문정보>
  </위임정보>
  <위임정보>
    <위임구분>위임행정규칙</위임구분>
    <위임행정규칙조문정보>
      <위임행정규칙일련번호>2100000000001</위임행정규칙일련번호>
      <위임행정규칙제목>갑규정</위임행정규칙제목>
      <조항호목>제2조제3호</조항호목>
      <링크텍스트>금융위원회가 정하여 고시하는</링크텍스트>
    </위임행정규칙조문정보>
  </위임정보>
  <위임정보>
    <위임구분>인용법령</위임구분>
    <위임법령일련번호>777</위임법령일련번호>
    <위임법령제목>을법</위임법령제목>
    <위임법령조문정보><위임법령조문번호>5</위임법령조문번호>
      <조항호목>제5조</조항호목><링크텍스트>「을법」 제5조</링크텍스트>
    </위임법령조문정보>
  </위임정보>
</위임조문정보>
</법령></lsDelegated>"""

STMD_XML = """<법령체계도><상하위법>
<법률><기본정보><법령ID>010000</법령ID><법령일련번호>100</법령일련번호>
  <법종구분>법률</법종구분><법령명>갑법</법령명></기본정보>
  <시행령><기본정보><법령ID>010001</법령ID><법령일련번호>200</법령일련번호>
    <법종구분>대통령령</법종구분><법령명>갑법 시행령</법령명></기본정보>
    <행정규칙><고시><기본정보><행정규칙일련번호>2100000000001</행정규칙일련번호>
      <법종구분>고시</법종구분><행정규칙명>갑규정</행정규칙명></기본정보></고시>
    <고시><기본정보><행정규칙일련번호>2100000000009</행정규칙일련번호>
      <법종구분>고시</법종구분><행정규칙명>병규정</행정규칙명></기본정보></고시>
    </행정규칙>
  </시행령>
</법률>
</상하위법></법령체계도>"""


@pytest.fixture()
def world(tmp_path):
    """법률 갑법(스토어에 있음) · 시행령(있음) · 갑규정(스토어엔 없음) 소우주."""
    corpus = tmp_path / "corpus"
    store = tmp_path / "store"
    sha = {"갑법": _sha("갑법"), "영": _sha("갑법 시행령"), "규정": _sha("갑규정")}

    law_dir = corpus / "law"
    (law_dir / "갑법").mkdir(parents=True)
    (law_dir / "갑법" / "본문.xml").write_text(LAW_XML, encoding="utf-8")
    (law_dir / "규정").mkdir(parents=True)
    (law_dir / "규정" / "본문.xml").write_text(ADMRUL_XML, encoding="utf-8")
    (law_dir / "manifest.json").write_text(json.dumps({"items": [
        {"name": "갑법", "kind": "law", "doc_no": "100", "enforce": "20260101",
         "body_sha256": sha["갑법"],
         "body_file": str((law_dir / "갑법" / "본문.xml").relative_to(tmp_path)),
         "body_format": "xml"},
        {"name": "갑법 시행령", "kind": "law", "doc_no": "200", "enforce": "20260101",
         "body_sha256": sha["영"], "body_file": "본문없음.xml", "body_format": "xml"},
        {"name": "갑규정", "kind": "admrul", "doc_no": "2100000000001",
         "enforce": "20260101", "body_sha256": sha["규정"],
         "body_file": str((law_dir / "규정" / "본문.xml").relative_to(tmp_path)),
         "body_format": "xml"},
    ]}, ensure_ascii=False), encoding="utf-8")

    rel = law_dir / "relations"
    rel.mkdir()
    (rel / "lsDelegated_200.xml").write_text(DELEGATED_XML, encoding="utf-8")
    (rel / "lsStmd_100.xml").write_text(STMD_XML, encoding="utf-8")

    for name, nodes in [
        ("갑법", [{"id": 4, "surface": "제34조의2", "parent": None},
                  {"id": 5, "surface": "①", "parent": 4}]),
        ("영", [{"id": 7, "surface": "제3조", "parent": None}]),
    ]:
        d = store / sha[name][:16]
        d.mkdir(parents=True)
        (d / "result.json").write_text(
            json.dumps({"nodes": nodes}, ensure_ascii=False), encoding="utf-8")

    return {"corpus": corpus, "store": store, "root": tmp_path, "sha": sha}


def test_대상은_명칭으로_잇고_구판_MST는_무시된다(world):
    items = lawnet.load_manifest(world["corpus"])
    out = lawnet.transcribe_delegations(world["corpus"] / "law" / "relations", items)
    edges = out["edges"]
    assert len(edges) == 3
    up = next(e for e in edges if e["dst"]["name"] == "갑법")
    # 데이터의 999(구판)가 아니라 명칭 완전일치로 sha16 이 잇는다
    assert up["dst"]["doc_id"] == world["sha"]["갑법"][:16]
    assert up["dst"]["jo"] == "제34조의2" and up["kind"] == "인용법령"
    assert up["src"]["doc_id"] == world["sha"]["영"][:16]
    assert up["src"]["jo"] == "제3조"


def test_행정규칙은_일련번호로_잇고_미보유는_null_보존(world):
    items = lawnet.load_manifest(world["corpus"])
    edges = lawnet.transcribe_delegations(
        world["corpus"] / "law" / "relations", items)["edges"]
    down = next(e for e in edges if e["dst"]["name"] == "갑규정")
    assert down["dst"]["doc_id"] == world["sha"]["규정"][:16]
    # 조항호목은 대상 좌표가 아니라 출발 쪽 위치다(실측 99.9%) — src.anchor 로
    # 남고, 행정규칙 대상의 조 좌표는 데이터에 없다(문서 수준 포인터)
    assert down["dst"]["jo"] is None
    assert down["src"]["anchor"] == "제2조제3호"
    orphan = next(e for e in edges if e["dst"]["name"] == "을법")
    assert orphan["dst"]["doc_id"] is None       # 버리지 않는다


def test_조_좌표가_surface_완전일치로_해소된다(world):
    items = lawnet.load_manifest(world["corpus"])
    edges = lawnet.transcribe_delegations(
        world["corpus"] / "law" / "relations", items)["edges"]
    hits = lawnet.resolve_nodes(edges, world["store"])
    up = next(e for e in edges if e["dst"]["name"] == "갑법")
    assert up["src"]["node"] == 7 and up["dst"]["node"] == 4     # 가지조문 포함
    down = next(e for e in edges if e["dst"]["name"] == "갑규정")
    assert "node" not in down["dst"]             # 대상 조 좌표가 없다 — 문서 수준
    assert hits == 4                             # 을법 간선도 src 쪽은 해소된다


def test_문서_인덱스가_제1조와_가족을_전사한다(world):
    idx = lawnet.build_index(world["corpus"], world["corpus"] / "law" / "relations",
                             world["store"], world["root"])
    rows = {d["name"]: d for d in idx["docs"]}
    assert rows["갑법"]["purpose"] == "제1조(목적) 이 법은 갑 업무를 규율함을 목적으로 한다."
    assert rows["갑규정"]["purpose"].startswith("제1-1조(목적) 이 규정은")
    assert rows["갑법"]["kind"] == "법률"
    assert rows["갑법 시행령"]["kind"] == "대통령령"       # 체계도 법종구분이 이긴다
    assert rows["갑법"]["in_store"] and not rows["갑규정"]["in_store"]
    fam = idx["families"][0]
    assert fam["root"] == "갑법"
    held = {m["name"]: m["held"] for m in fam["members"]}
    assert held == {"갑법": True, "갑법 시행령": True, "갑규정": True, "병규정": False}
