
from __future__ import annotations
from typing import Callable, Sequence
import numpy as np


def analyse_min_dimension_distribution(min_scores, band=(0.2, 0.5)):
    arr = np.asarray(min_scores, dtype=float)
    lo, hi = band
    in_band = (arr >= lo) & (arr <= hi)
    frac_in_band = float(in_band.mean())
    hist, edges = np.histogram(arr, bins=10, range=(0.0, 1.0))
    return {
        "n": len(arr),
        "fraction_in_band": frac_in_band,
        "n_in_band": int(in_band.sum()),
        "histogram_counts": hist.tolist(),
        "histogram_edges": edges.tolist(),
        "verdict": (
            "Floor flatness CONSISTENT with data: only "
            + str(round(frac_in_band*100, 2)) + "% of records have min-dim score in ["
            + str(lo) + ", " + str(hi) + "]. Report this distribution alongside the flat result."
            if frac_in_band < 0.02 else
            "Floor flatness SUSPICIOUS: " + str(round(frac_in_band*100, 2))
            + "% fall in the floor-sensitive band. Check that floor is wired into the scoring call."
        ),
    }


def probe_floor_wiring(soft_min_score_fn, dimension_scores, floors_to_test=(0.2, 0.3, 0.4, 0.5)):
    outputs = {}
    for f in floors_to_test:
        outputs[f] = soft_min_score_fn(dimension_scores, floor=f)
    distinct = len(set(np.round(list(outputs.values()), 6)))
    return {
        "dimension_scores_used": list(dimension_scores),
        "outputs_by_floor": outputs,
        "distinct_output_count": distinct,
        "verdict": (
            "Floor correctly wired: output changes with floor on a sensitive-band record."
            if distinct > 1 else
            "Floor NOT wired: output unchanged even on a sensitive-band record. Fix plumbing before reporting flat."
        ),
    }
