# Cost of a false link (wrong patient merged in) — high clinical harm
COST_FALSE_LINK = 100

# Cost of a false quarantine (legitimate record held for review)
COST_FALSE_QUARANTINE = 5


def optimal_thresholds():
    """
    Bayes-risk thresholds. Returns (low_risk, medium_risk) cutoffs
    derived from the cost matrix instead of hard-coded values.

    Auto-link only when trust >= P(positive) threshold where the
    expected cost of linking equals the expected cost of quarantining.
    """
    low = COST_FALSE_LINK / (COST_FALSE_LINK + COST_FALSE_QUARANTINE)
    medium = low * 0.6
    return round(low, 3), round(medium, 3)


if __name__ == "__main__":
    low, med = optimal_thresholds()
    print(f"Low-risk threshold:    {low}")
    print(f"Medium-risk threshold: {med}")