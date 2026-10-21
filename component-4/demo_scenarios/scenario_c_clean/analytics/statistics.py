"""Statistical metrics calculation module."""
from typing import List, Optional

def compute_mean(data: List[float]) -> Optional[float]:
    if not data:
        return None
    return sum(data) / len(data)

def compute_median(data: List[float]) -> Optional[float]:
    if not data:
        return None
    sorted_data = sorted(data)
    n = len(sorted_data)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_data[mid])
    return (sorted_data[mid - 1] + sorted_data[mid]) / 2.0

def compute_variance(data: List[float]) -> Optional[float]:
    if not data or len(data) < 2:
        return 0.0
    mean_val = compute_mean(data)
    return sum((x - mean_val) ** 2 for x in data) / (len(data) - 1)
