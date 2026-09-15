"""Ordinary mechanical-contract checks; synthetic rows only, no model calls."""
import copy

import pytest

from lawrag.pipeline.genos_admission import POLICY, validate_structure


@pytest.fixture
def payload():
    return {
        "nodes": [{"id": 0, "parent": None, "block": 0, "span": [0, 2],
                   "family": "kr_article", "surface": "제1조", "page": 1}],
        "blocks": [{"idx": 0, "node": 0, "text": "제1조(가상 규정)", "page": 1},
                   {"idx": 1, "node": 0, "text": "가상 본문", "page": 1}],
        "fitness": {"passed": False, "score": 0.0},
    }


def admit(payload, **meta):
    return validate_structure("abc", {"doc_id": "abc", "passed": False, "score": 0.0, **meta}, payload)


@pytest.mark.parametrize("score", [0.0, 0.1, 0.69, 0.99, 1.0])
def test_fitness_is_advisory_and_inputs_are_unchanged(payload, score):
    before = copy.deepcopy(payload)
    meta = {"doc_id": "abc", "passed": False, "score": score}
    receipt = validate_structure("abc", meta, payload)
    assert receipt["policy"] == POLICY == "score-advisory-v1"
    assert receipt["accepted"] is True
    assert receipt["heuristic_passed"] is False
    assert receipt["heuristic_score"] == score
    assert receipt["warnings"]
    assert all(receipt["checks"].values())
    assert payload == before and meta == {"doc_id": "abc", "passed": False, "score": score}
    # A stored admission receipt is not evidence fed back into its own result.
    meta["structure_admission"] = receipt
    assert validate_structure("abc", meta, payload) == receipt


def test_missing_heuristic_does_not_fabricate_pass_or_score(payload):
    payload.pop("fitness")
    receipt = validate_structure("abc", {"doc_id": "abc"}, payload)
    assert receipt["heuristic_passed"] is None
    assert receipt["heuristic_score"] is None


@pytest.mark.parametrize("field", ["nodes", "blocks"])
@pytest.mark.parametrize("value", [None, [], {}, "malformed"])
def test_missing_structure_fails_even_with_perfect_score(payload, field, value):
    payload[field] = value
    with pytest.raises(ValueError, match=field):
        admit(payload, passed=True, score=1.0)


@pytest.mark.parametrize("value", ["", " \n\t", None, 123])
def test_empty_or_malformed_text_fails(payload, value):
    for block in payload["blocks"]:
        block["text"] = value
    with pytest.raises(ValueError, match="본문"):
        admit(payload)


@pytest.mark.parametrize("source", ["meta", "result"])
def test_document_id_mismatch_fails(payload, source):
    meta = {"doc_id": "abc", "passed": True}
    (meta if source == "meta" else payload)["doc_id"] = "other"
    with pytest.raises(ValueError, match="문서 ID"):
        validate_structure("abc", meta, payload)


@pytest.mark.parametrize("kind", ["nodes", "blocks"])
def test_duplicate_ids_fail(payload, kind):
    payload[kind].append(copy.deepcopy(payload[kind][0]))
    with pytest.raises(ValueError, match="중복"):
        admit(payload)


@pytest.mark.parametrize("value", [True, "0", -1, 0.1, None, 10**100])
def test_bad_block_index_fails_without_span_sized_allocation(payload, value):
    payload["blocks"][0]["idx"] = value
    with pytest.raises(ValueError, match="idx"):
        admit(payload)


@pytest.mark.parametrize("span", [None, [], [0], [0, 1, 2], [True, 2], ["0", 2],
                                  [-1, 2], [0, 0], [2, 1], [0, 10**100]])
def test_bad_span_fails(payload, span):
    payload["nodes"][0]["span"] = span
    with pytest.raises(ValueError, match="span"):
        admit(payload)


@pytest.mark.parametrize("kind", ["parent", "node"])
@pytest.mark.parametrize("value", [99, True, "0"])
def test_bad_unit_references_fail(payload, kind, value):
    row = payload["nodes"][0] if kind == "parent" else payload["blocks"][0]
    row[kind] = value
    with pytest.raises(ValueError, match=kind):
        admit(payload)


def test_parent_cycle_fails(payload):
    payload["nodes"][0]["parent"] = 1
    payload["nodes"].append({"id": 1, "parent": 0, "block": 1, "span": [1, 2]})
    with pytest.raises(ValueError, match="순환"):
        admit(payload)


def test_deep_tree_does_not_recurse():
    size = 1800
    data = {"nodes": [{"id": i, "parent": i - 1 if i else None,
                       "block": 0, "span": [0, 1]} for i in range(size)],
            "blocks": [{"idx": 0, "node": size - 1, "text": "synthetic"}]}
    assert admit(data)["counts"] == {"nodes": size, "blocks": 1}


def test_nested_spans_and_late_parent_are_valid(payload):
    payload["nodes"].insert(0, {"id": 1, "parent": 0, "block": 1, "span": [1, 2]})
    payload["blocks"][1]["node"] = 1
    assert admit(payload)["accepted"]


def test_uncovered_prefix_fails_without_creating_a_node(payload):
    payload["nodes"][0].update(block=1, span=[1, 2])
    with pytest.raises(ValueError, match="어느 구조 마디"):
        admit(payload)
    assert len(payload["nodes"]) == 1


def test_uncovered_tail_fails(payload):
    payload["nodes"][0]["span"] = [0, 1]
    with pytest.raises(ValueError, match="어느 구조 마디"):
        admit(payload)


def test_explicit_leaf_attachment_can_cover_outside_text_span(payload):
    payload["nodes"][0].update(span=[0, 1], attachments=[{"block": 1, "kind": "table"}])
    payload["blocks"][1]["kind"] = "table"
    assert admit(payload)["accepted"]


def test_missing_attachment_block_fails(payload):
    payload["nodes"][0]["attachments"] = [{"block": 99}]
    with pytest.raises(ValueError, match="첨부 블록"):
        admit(payload)


def test_falsy_malformed_attachments_are_not_treated_as_absent(payload):
    payload["nodes"][0]["attachments"] = {}
    with pytest.raises(ValueError, match="attachments"):
        admit(payload)


def test_block_owner_must_actually_cover_it(payload):
    payload["nodes"].append({"id": 1, "parent": 0, "block": 1, "span": [1, 2]})
    payload["blocks"][0]["node"] = 1
    with pytest.raises(ValueError, match="span/첨부"):
        admit(payload)


def test_optional_overlay_owner_is_not_fabricated(payload):
    payload["blocks"][1]["node"] = None
    assert admit(payload)["accepted"]
    assert payload["blocks"][1]["node"] is None


@pytest.mark.parametrize("value", ["x" * 64, "a" * 64, "abc", 10])
def test_present_bad_source_coordinate_fails(payload, value):
    payload["blocks"][0]["source_artifact_sha256"] = value
    with pytest.raises(ValueError, match="SHA-256"):
        admit(payload)


def test_valid_source_coordinate_is_preserved(payload):
    payload["blocks"][0]["source_artifact_sha256"] = "abc" + "d" * 61
    before = copy.deepcopy(payload)
    assert admit(payload)["accepted"]
    assert payload == before


def test_synthetic_real_viewer_payload_shape():
    from lawrag.core.structure.model import Block, Fingerprint, Ladder, Node, StructureResult
    from lawrag.core.structure.viewer import payload as render

    node = Node(level=0, ordinal=(1,), family="kr_article", surface="제1조", block_idx=0,
                page=1, element_index=0, candidate_id="synthetic", span=(0, 2))
    structure = StructureResult(doc="synthetic", tree=[node], ladder=Ladder(), candidates=[],
                                fitness_score=0.0, fitness_passed=False,
                                fingerprint=Fingerprint())
    rendered = render(structure, [Block(0, "제1조"), Block(1, "가상 본문")])
    assert admit(rendered)["accepted"]


def test_source_field_adapter_does_not_require_viewer_heading_coordinate(payload):
    for node in payload["nodes"]:
        node.pop("block")
        node["family"] = "source_field"
    assert admit(payload)["accepted"]
    assert all("block" not in node for node in payload["nodes"])


def test_registered_format_payload_keeps_false_fitness():
    from lawrag.core.fitness_gate import Fitness
    from lawrag.core.parse_adapter import Element, ParseResult
    from lawrag.core.structurize import Document, Section
    from lawrag.core.structure.from_format import result_from_document
    from lawrag.core.structure.viewer import payload as render

    parsed = ParseResult(path="synthetic.hwp", doc_id="abc", parser="synthetic-hwp", born_digital=True,
                         elements=[Element(0, "text", "제1조"), Element(1, "text", "가상 본문")])
    document = Document(doc_type="synthetic", format_version=1, source_file="synthetic.hwp",
                        sections=[Section(section_id="제1조", marker={"kind": "regex", "id": "조", "no": "1"},
                                          path=["제1조"], level=0, elements=[0, 1], pages=[1])])
    result, blocks = result_from_document(parsed, document, Fitness(score=0.0, passed=False), doc_type="synthetic")
    rendered = render(result, blocks, elements=parsed.elements)
    assert admit(rendered)["accepted"]
    assert rendered["fitness"]["passed"] is False
