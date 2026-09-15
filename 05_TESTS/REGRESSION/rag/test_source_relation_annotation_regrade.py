from scripts.rag_source_relation_annotation_regrade import summarize


def test_regrade_summary_is_paired_against_full():
    rows = [
        {"grades": {"full_context": {"correct": True},
                    "structural_annotations": {"correct": False},
                    "all_relation_annotations": {"correct": True}}},
        {"grades": {"full_context": {"correct": False},
                    "structural_annotations": {"correct": True},
                    "all_relation_annotations": {"correct": False}}},
    ]
    result = summarize(rows)
    assert result["structural_annotations"]["versus_full"]["full_only_correct"] == 1
    assert result["structural_annotations"]["versus_full"]["annotation_only_correct"] == 1
    assert result["all_relation_annotations"]["versus_full"]["delta"] == 0
