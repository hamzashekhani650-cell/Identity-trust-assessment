
from __future__ import annotations
from typing import Sequence

DEFAULT_WEIGHTS_4D = {
    "completeness": 0.20,
    "temporal": 0.15,
    "identity": 0.20,
    "provenance": 0.15,
}


def analyse_floor_sensitivity(
    dimension_scores_per_record: Sequence[dict],
    floors=(0.2, 0.3, 0.4, 0.5),
    threshold: float = 0.571,
) -> dict:
    """
    Correct floor-sensitivity check.

    For each record, compute the composite score across floor values, and check
    whether its quarantine status (score < threshold) changes. This is the right
    question — max(min_score, floor) affects every record below the floor, not
    just records whose min_score sits inside the swept band.

    dimension_scores_per_record: one dict per record, keyed by the four validators
      used for this population (completeness, temporal, identity, provenance).
      Cross_record is intentionally excluded because it is handled by the router's
      hard override and set to 1.0 for clean-population testing.
    """
    results_per_floor = {f: [] for f in floors}
    per_record_traces = []

    for i, dims in enumerate(dimension_scores_per_record):
        weighted_sum = sum(DEFAULT_WEIGHTS_4D[k] * dims[k] for k in DEFAULT_WEIGHTS_4D)
        min_score = min(dims[k] for k in DEFAULT_WEIGHTS_4D)

        trace = {}
        for f in floors:
            composite = weighted_sum * max(min_score, f)
            trace[f] = composite
        per_record_traces.append((i, min_score, weighted_sum, trace))
        for f in floors:
            results_per_floor[f].append(trace[f] < threshold)

    quarantine_by_floor = {f: sum(results_per_floor[f]) for f in floors}

    # Identify records whose status flips across the sweep
    flippers = []
    for i, min_score, weighted_sum, trace in per_record_traces:
        statuses = [trace[f] < threshold for f in floors]
        if len(set(statuses)) > 1:
            flippers.append({
                "record_index": i,
                "min_score": min_score,
                "weighted_sum": weighted_sum,
                "scores_by_floor": {f: round(trace[f], 4) for f in floors},
                "status_by_floor": {f: statuses[j] for j, f in enumerate(floors)},
            })

    net_delta = quarantine_by_floor[floors[-1]] - quarantine_by_floor[floors[0]]

    if len(flippers) == 0:
        verdict = (
            "No record changes quarantine status across the floor sweep. "
            "For every affected record, weighted_sum is low enough that even "
            "max(min_score, floor)=0.5 keeps the composite below "
            + str(threshold) + ". The floor is applied but never crosses the "
            "routing boundary on this population."
        )
    elif net_delta == 0:
        verdict = (
            str(len(flippers)) + " records change status, but net quarantine "
            "count is flat (delta=0). Crossings cancel in aggregate — some "
            "records exit quarantine, others enter, at the same rate. This is "
            "not 'unaffected by floor'; it is 'floor-invariant in aggregate via "
            "cancellation'."
        )
    else:
        verdict = (
            str(len(flippers)) + " records change status; net quarantine delta "
            "across the sweep is " + str(net_delta) + ". The aggregate "
            "quarantine rate is NOT floor-invariant on this population."
        )

    return {
        "n_records": len(dimension_scores_per_record),
        "floors": list(floors),
        "threshold": threshold,
        "quarantine_by_floor": quarantine_by_floor,
        "n_flippers": len(flippers),
        "net_quarantine_delta": net_delta,
        "flippers": flippers[:20],  # cap for printout
        "verdict": verdict,
    }
