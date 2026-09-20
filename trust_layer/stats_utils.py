
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy import stats as scipy_stats


def _wilson_interval(successes, n, alpha):
    z = scipy_stats.norm.ppf(1 - alpha / 2)
    p_hat = successes / n
    denom = 1 + z**2 / n
    centre = p_hat + z**2 / (2 * n)
    half_width = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n)
    lower = (centre - half_width) / denom
    upper = (centre + half_width) / denom
    return max(0.0, lower), min(1.0, upper)


def _clopper_pearson_interval(successes, n, alpha):
    if successes == 0:
        lower = 0.0
    else:
        lower = scipy_stats.beta.ppf(alpha / 2, successes, n - successes + 1)
    if successes == n:
        upper = 1.0
    else:
        upper = scipy_stats.beta.ppf(1 - alpha / 2, successes + 1, n - successes)
    return float(lower), float(upper)


@dataclass
class ProportionResult:
    successes: int
    n: int
    point_estimate: float
    ci_lower: float
    ci_upper: float
    method: str
    confidence: float

    def __str__(self):
        return (str(self.successes) + "/" + str(self.n) + " = " +
                str(round(self.point_estimate, 4)) + " " +
                "(" + str(int(self.confidence*100)) + "% " + self.method +
                " CI: [" + str(round(self.ci_lower, 4)) + ", " +
                str(round(self.ci_upper, 4)) + "])")


def proportion_ci(successes, n, confidence=0.95, method="wilson"):
    alpha = 1 - confidence
    if method == "wilson":
        lower, upper = _wilson_interval(successes, n, alpha)
    elif method == "beta":
        lower, upper = _clopper_pearson_interval(successes, n, alpha)
    else:
        raise ValueError("method must be wilson or beta")
    return ProportionResult(
        successes=successes, n=n,
        point_estimate=successes / n,
        ci_lower=lower, ci_upper=upper,
        method=method, confidence=confidence,
    )


@dataclass
class PairedTestResult:
    test_name: str
    statistic: float
    p_value: float
    n_pairs: int
    mean_diff: float
    interpretation: str


def paired_seed_comparison(scores_a, scores_b, alpha=0.05,
                            label_a="A", label_b="B"):
    a = np.asarray(scores_a, dtype=float)
    b = np.asarray(scores_b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired arrays must match in length")
    n_pairs = len(a)
    diffs = a - b
    mean_diff = float(np.mean(diffs))

    if np.all(diffs == 0):
        return PairedTestResult(
            test_name="none (identical)", statistic=0.0, p_value=1.0,
            n_pairs=n_pairs, mean_diff=0.0,
            interpretation=(label_a + " and " + label_b +
                            " are identical across all " + str(n_pairs) + " seeds."))

    try:
        stat, p = scipy_stats.wilcoxon(a, b)
        test_name = "Wilcoxon signed-rank"
    except ValueError:
        stat, p = scipy_stats.ttest_rel(a, b)
        test_name = "paired t-test"

    if p < alpha:
        interp = ("Significant difference between " + label_a + " and " + label_b +
                  " (p=" + str(round(p, 4)) + "), mean diff = " + str(round(mean_diff, 4)))
    else:
        interp = ("No significant difference between " + label_a + " and " + label_b +
                  " (p=" + str(round(p, 4)) + "), mean diff = " + str(round(mean_diff, 4)) +
                  ". With n=" + str(n_pairs) + " seeds, limited power.")

    return PairedTestResult(test_name, float(stat), float(p), n_pairs,
                            mean_diff, interp)
