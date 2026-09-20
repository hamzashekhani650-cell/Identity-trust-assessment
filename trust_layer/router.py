LOW_RISK_THRESHOLD = 0.85
MEDIUM_RISK_THRESHOLD = 0.50


def route_decision(trust_score):
    if trust_score >= LOW_RISK_THRESHOLD:
        return "AUTO_LINK"
    elif trust_score >= MEDIUM_RISK_THRESHOLD:
        return "LINK_WITH_FLAG"
    else:
        return "QUARANTINE"


def route_decision_hard(trust_score, cross_record_score):
    if cross_record_score == 0.0:
        return "QUARANTINE"
    return route_decision(trust_score)