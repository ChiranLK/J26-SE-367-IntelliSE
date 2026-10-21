"""Pytest suite for statistics module."""
from analytics.statistics import compute_mean, compute_median, compute_variance

def test_mean_calculation():
    assert compute_mean([10.0, 20.0, 30.0]) == 20.0
    assert compute_mean([]) is None

def test_median_odd_and_even():
    assert compute_median([3.0, 1.0, 2.0]) == 2.0
    assert compute_median([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert compute_median([]) is None

def test_variance_calculation():
    assert compute_variance([2.0, 4.0, 6.0]) == 4.0
    assert compute_variance([5.0]) == 0.0
