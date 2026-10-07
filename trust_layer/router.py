"""
Routing decisions for the trust layer.

Two variants:
  route_decision       — Trust-Soft (the paper's validated model)
  route_decision_hard  — Trust-Hard (demo variant with collision override)

Both return a tuple: (decision, reason).
The reason is a short human-readable string that explains why the
decision fired. It gets displayed in the UI and logged for audits.
"""

LOW_RISK_THRESHOLD = 0.85
MEDIUM_RISK_THRESHOLD = 0.50


def route_decision(trust_score, auto_thresh=LOW_RISK_THRESHOLD, quar_thresh=MEDIUM_RISK_THRESHOLD):
    """
    Trust-Soft routing. The paper's validated model.
    No collision override. Pure threshold-based routing on the composite score.

    Returns: (decision, reason)
    """
    if trust_score >= auto_thresh:
        return "AUTO_LINK", f"Composite {trust_score:.3f} ≥ auto-link threshold {auto_thresh}"
    elif trust_score >= quar_thresh:
        return "LINK_WITH_FLAG", f"Composite {trust_score:.3f} between flag thresholds ({quar_thresh} – {auto_thresh})"
    else:
        return "QUARANTINE", f"Composite {trust_score:.3f} below quarantine threshold {quar_thresh}"


def route_decision_hard(trust_score, cross_record_score, auto_thresh=0.75, quar_thresh=0.45):
    """
    Trust-Hard routing. Demo variant.
    Any cross-record score of 0.0 forces immediate quarantine,
    regardless of the composite score.

    Returns: (decision, reason)
    """
    if cross_record_score == 0.0:
        return (
            "QUARANTINE",
            "Identifier collision — cross-record score 0.0 (hard override)",
        )
    if trust_score < quar_thresh:
        return "QUARANTINE", f"Composite {trust_score:.3f} below quarantine threshold {quar_thresh}"
    if trust_score < auto_thresh:
        return "LINK_WITH_FLAG", f"Composite {trust_score:.3f} below auto-link threshold {auto_thresh}"
    return "AUTO_LINK", f"Composite {trust_score:.3f} ≥ auto-link threshold {auto_thresh}"
