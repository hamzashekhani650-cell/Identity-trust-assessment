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

assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.001
assert max(DEFAULT_WEIGHTS.values()) <= 0.40


def compute_trust_score(completeness, temporal, identity, provenance, cross_record):
    score = (
        DEFAULT_WEIGHTS["completeness"] * completeness +
        DEFAULT_WEIGHTS["temporal"]     * temporal +
        DEFAULT_WEIGHTS["identity"]     * identity +
        DEFAULT_WEIGHTS["provenance"]   * provenance +
        DEFAULT_WEIGHTS["cross_record"] * cross_record
    )
    return round(score, 4)