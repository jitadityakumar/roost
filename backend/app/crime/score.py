"""Weighted crime score, ported verbatim from crime-rate-tracker's
crime_compare.py -- see that script's module docstring for the residential
vs. footfall rationale (a high ratio near a busy high street/station
shouldn't be read the same as one on residential streets)."""

RESIDENTIAL_CATEGORIES = {
    "burglary",
    "vehicle-crime",
    "criminal-damage-arson",
    "violent-crime",
    "robbery",
    "possession-of-weapons",
}

RESIDENTIAL_WEIGHT = 0.7
FOOTFALL_WEIGHT = 0.3


def _split(category_counts: dict[str, int]) -> tuple[int, int]:
    residential = sum(n for cat, n in category_counts.items() if cat in RESIDENTIAL_CATEGORIES)
    footfall = sum(category_counts.values()) - residential
    return residential, footfall


def compute_score(category_counts: dict[str, int]) -> float:
    residential, footfall = _split(category_counts)
    return RESIDENTIAL_WEIGHT * residential + FOOTFALL_WEIGHT * footfall


def _ratio(candidate: float, baseline: float) -> float | None:
    """None means the baseline is zero -- caller renders as n/a (candidate
    also zero) or "new" (candidate has crimes the baseline had none of)."""
    if baseline == 0:
        return None
    return candidate / baseline


def compare(candidate_counts: dict[str, int], baseline_counts: dict[str, int]) -> dict:
    """Compares candidate vs. baseline category counts. Shape mirrors what
    crime_compare.py's print_comparison computes, as data rather than
    printed text."""
    all_categories = sorted(set(candidate_counts) | set(baseline_counts))
    categories = []
    for cat in all_categories:
        candidate_n = candidate_counts.get(cat, 0)
        baseline_n = baseline_counts.get(cat, 0)
        categories.append(
            {
                "category": cat,
                "residential": cat in RESIDENTIAL_CATEGORIES,
                "candidate_count": candidate_n,
                "baseline_count": baseline_n,
                "ratio": _ratio(candidate_n, baseline_n),
            }
        )

    candidate_res, candidate_footfall = _split(candidate_counts)
    baseline_res, baseline_footfall = _split(baseline_counts)
    candidate_score = compute_score(candidate_counts)
    baseline_score = compute_score(baseline_counts)

    return {
        "categories": categories,
        "candidate_total": sum(candidate_counts.values()),
        "baseline_total": sum(baseline_counts.values()),
        "total_ratio": _ratio(sum(candidate_counts.values()), sum(baseline_counts.values())),
        "candidate_residential": candidate_res,
        "baseline_residential": baseline_res,
        "residential_ratio": _ratio(candidate_res, baseline_res),
        "candidate_footfall": candidate_footfall,
        "baseline_footfall": baseline_footfall,
        "footfall_ratio": _ratio(candidate_footfall, baseline_footfall),
        "candidate_score": candidate_score,
        "baseline_score": baseline_score,
        "score_ratio": _ratio(candidate_score, baseline_score),
    }
