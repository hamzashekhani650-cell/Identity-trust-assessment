from trust_layer.validators import (
    validate_completeness,
    validate_temporal,
    validate_identity_consistency,
    validate_provenance,
)

DEFAULT_WEIGHTS = {
    "completeness": 0.20,
    "temporal":     0.15,
    "identity":     0.20,
    "provenance":   0.15,
    "cross_record": 0.30,
}

# Floor: the minimum dimension score is lifted to at least this value
# before the penalty is applied. Prevents legitimate 0.0 dimensions
# (missing facility, no identifier) from vetoing the whole record.
MIN_FLOOR = 0.4


def robust_trust_score(scores: dict):
    """
    Soft conjunctive aggregation: weighted sum multiplied by a penalty
    derived from the weakest dimension score.

    penalty = MIN_FLOOR + (1 - MIN_FLOOR) * min_score

    A single adversarial dimension (min = 0.0) still drags the composite
    down by a factor of MIN_FLOOR, but a legitimate dimension returning
    0.0 (e.g., no source facility) does not zero the entire record.
    """
    weighted_sum = sum(DEFAULT_WEIGHTS[k] * v for k, v in scores.items())
    min_score = min(scores.values())
    penalty = MIN_FLOOR + (1 - MIN_FLOOR) * min_score
    return round(weighted_sum * penalty, 4)
