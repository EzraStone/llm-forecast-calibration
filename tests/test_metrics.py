"""Tests for metrics (spec section 8). Must pass before analysis code is used."""
import numpy as np
import pytest

from src.metrics import (
    auc,
    brier,
    ece,
    log_loss,
    mean_abs_from_half,
    murphy_decomposition,
)


def test_brier_perfect():
    y = np.array([0, 1, 0, 1])
    p = np.array([0.0, 1.0, 0.0, 1.0])
    assert brier(p, y) == 0.0


def test_brier_always_half_balanced():
    y = np.array([0, 1, 0, 1])
    p = np.full(4, 0.5)
    assert brier(p, y) == pytest.approx(0.25)


def test_brier_known_value():
    # p=0.8 on y=1 (err 0.04), p=0.3 on y=0 (err 0.09): mean = 0.065
    y = np.array([1, 0])
    p = np.array([0.8, 0.3])
    assert brier(p, y) == pytest.approx(0.065)


def test_murphy_components_sum_to_brier():
    rng = np.random.default_rng(7)
    for trial in range(20):
        y = rng.integers(0, 2, 60)
        # discrete forecasts (realistic: model outputs 0.01-granular probabilities)
        p = np.round(np.clip(rng.beta(2, 2, 60), 0.01, 0.99), 2)
        rel, res, unc = murphy_decomposition(p, y)
        assert rel - res + unc == pytest.approx(brier(p, y), abs=1e-9)


def test_ece_zero_for_perfectly_calibrated():
    # construct a set where each bin's mean prediction equals its empirical frequency
    # use integer-compatible frequencies (avoid banker's rounding): k/n = p_bin
    ps, ys = [], []
    for i in range(10):
        p_bin = (i + 0.5) / 10
        n = 20  # k = p_bin * 20 is an integer for 0.05..0.95
        k = int(p_bin * n)
        ps.extend([p_bin] * n)
        ys.extend([1] * k + [0] * (n - k))
    assert ece(np.array(ps), np.array(ys), n_bins=10) == pytest.approx(0.0, abs=1e-12)


def test_ece_positive_for_miscalibrated():
    # confident wrong predictions
    y = np.zeros(20)
    p = np.full(20, 0.9)
    assert ece(p, y, n_bins=10) == pytest.approx(0.9, abs=1e-9)


def test_log_loss_clips_extremes():
    y = np.array([0, 1])
    p = np.array([0.0, 1.0])  # would be infinite without clipping
    ll = log_loss(p, y, clip=1e-3)
    assert np.isfinite(ll)
    assert ll == pytest.approx(-np.log(1 - 1e-3), abs=1e-6)


def test_auc_perfect_discrimination():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.3, 0.7, 0.9])
    assert auc(p, y) == 1.0


def test_auc_chance():
    rng = np.random.default_rng(3)
    y = rng.integers(0, 2, 100)
    p = np.full(100, 0.5)
    assert auc(p, y) == pytest.approx(0.5)


def test_mean_abs_from_half():
    p = np.array([0.5, 0.0, 1.0])
    assert mean_abs_from_half(p) == pytest.approx(1.0 / 3.0)
