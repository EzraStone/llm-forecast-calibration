"""Pure metric functions for calibration analysis (spec section 7).

All functions take 1-D numpy arrays: p (predicted prob of YES), y (0/1 outcomes).
"""
import numpy as np


def brier(p, y):
    """Mean (p - y)^2."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2))


def murphy_decomposition(p, y, n_bins=None):
    """Brier decomposition into reliability, resolution, uncertainty.

    Classical Murphy (1973) binning: each DISTINCT forecast value is its own bin,
    which makes the identity Brier = rel - res + unc exact (verified in tests).
    Forecasts here are discrete (model probabilities at ~0.01 granularity, or
    medians of K samples), so distinct-value binning is both classical and exact.

    n_bins is accepted for API compatibility and ignored; equal-width binning
    would break the exact identity via within-bin variance.
    """
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(p)
    ybar = y.mean()
    rel = res = 0.0
    for val in np.unique(p):
        m = p == val
        nb = m.sum()
        p_bar = val  # the bin mean IS the value
        y_bar_b = y[m].mean()
        rel += (nb / n) * (p_bar - y_bar_b) ** 2
        res += (nb / n) * (y_bar_b - ybar) ** 2
    unc = ybar * (1 - ybar)
    return float(rel), float(res), float(unc)


def ece(p, y, n_bins=10, equal_mass=False):
    """Expected calibration error.

    equal_mass=False: 10 equal-width bins.
    equal_mass=True:  10 equal-count bins (quantile bins).
    """
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(p)
    if n == 0:
        return 0.0
    if equal_mass:
        order = np.argsort(p)
        p_sorted, y_sorted = p[order], y[order]
        edges = np.array_split(np.arange(n), n_bins)
        total = 0.0
        for members in edges:
            if len(members) == 0:
                continue
            pb = p_sorted[members].mean()
            yb = y_sorted[members].mean()
            total += (len(members) / n) * abs(pb - yb)
        return float(total)
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, n_bins - 1)
    total = 0.0
    for b in range(n_bins):
        m = idx == b
        if not m.any():
            continue
        pb = p[m].mean()
        yb = y[m].mean()
        total += (m.sum() / n) * abs(pb - yb)
    return float(total)


def log_loss(p, y, clip=1e-3):
    """Mean negative log-likelihood on clipped probabilities."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    pc = np.clip(p, clip, 1 - clip)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def auc(p, y):
    """Area under ROC via rank statistic (handles ties)."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    # rank-based (Mann-Whitney U) with average ranks for ties
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    # average tied ranks
    sorted_p = p[order]
    i = 0
    while i < len(p):
        j = i
        while j + 1 < len(p) and sorted_p[j + 1] == sorted_p[i]:
            j += 1
        if j > i:
            avg = (i + j) / 2 + 1
            ranks[order[i:j + 1]] = avg
        i = j + 1
    rank_sum_pos = ranks[y == 1].sum()
    u = rank_sum_pos - n1 * (n1 + 1) / 2
    return float(u / (n1 * n0))


def mean_abs_from_half(p):
    """Mean |p - 0.5| — confidence/sharpness."""
    p = np.asarray(p, dtype=float)
    return float(np.mean(np.abs(p - 0.5)))
