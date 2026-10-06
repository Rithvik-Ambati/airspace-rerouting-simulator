"""Summary statistics shared by the dashboard, CLI and benchmark."""
import math
from statistics import mean, stdev


def summarize(result):
    return result.get("metrics", {})


def mean_ci(values, z=1.96):
    """Mean and a normal-approximation 95% half-width (0 for fewer than 2 samples)."""
    values = [float(v) for v in values]
    if not values:
        return 0.0, 0.0
    if len(values) < 2:
        return values[0], 0.0
    return mean(values), z * stdev(values) / math.sqrt(len(values))
