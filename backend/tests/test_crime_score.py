from app.crime import score


def test_compute_score_weights_residential_and_footfall():
    counts = {"burglary": 10, "shoplifting": 20}
    # burglary is residential (weight 0.7), shoplifting is footfall (weight 0.3)
    assert score.compute_score(counts) == 0.7 * 10 + 0.3 * 20


def test_compute_score_empty_counts_is_zero():
    assert score.compute_score({}) == 0


def test_compare_ratio_for_normal_counts():
    result = score.compare({"burglary": 6}, {"burglary": 3})
    row = result["categories"][0]
    assert row == {
        "category": "burglary",
        "residential": True,
        "candidate_count": 6,
        "baseline_count": 3,
        "ratio": 2.0,
    }
    assert result["score_ratio"] == 2.0


def test_compare_ratio_is_none_when_baseline_zero_and_candidate_zero():
    result = score.compare({}, {})
    assert result["total_ratio"] is None
    assert result["score_ratio"] is None


def test_compare_ratio_is_none_when_baseline_zero_and_candidate_nonzero():
    result = score.compare({"burglary": 5}, {})
    row = result["categories"][0]
    assert row["ratio"] is None
    assert result["candidate_residential"] == 5
    assert result["baseline_residential"] == 0
    assert result["residential_ratio"] is None


def test_compare_includes_categories_missing_from_either_side():
    result = score.compare({"burglary": 4}, {"drugs": 2})
    cats = {c["category"]: c for c in result["categories"]}
    assert cats["burglary"]["baseline_count"] == 0
    assert cats["drugs"]["candidate_count"] == 0
