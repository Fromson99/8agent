from scripts import data_tiers


def test_data_tier_inventory_separates_vectors_and_evaluation_data() -> None:
    inventory = data_tiers.build_inventory()
    assert inventory["classification"]["production_lawxml_raw"]["file_count"] > 1
    assert inventory["classification"]["production_lawxml_structure"]["file_count"] > 1
    assert inventory["classification"]["evaluation_mock_or_fixture"]["file_count"] > 1
    assert inventory["classification"]["excluded_vectors"]["file_count"] > 0
    assert inventory["coverage"]["data_files_total"] == inventory["coverage"][
        "data_files_classified"
    ]
    assert inventory["coverage"]["unclassified_data_files"] == []
    assert inventory["coverage"]["multiply_classified_data_files"] == []
    assert inventory["two_bucket_complete"] is False
    assert data_tiers.validate(inventory) == []
