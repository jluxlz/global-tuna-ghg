"""Explicit positive price scenarios, not estimated carbon-to-fuel elasticities."""
import math

def inverse_carbon_multiplier(start,end):
    """Hold zero/missing regimes flat; otherwise use the positive inverse ratio.

    This is a prescribed scenario assumption for fuels lacking future quotes.
    It does not infer that carbon pricing empirically causes fuel costs to fall.
    """
    if start is None or end is None:return 1.
    a,b=float(start),float(end)
    if not math.isfinite(a) or not math.isfinite(b) or a<=0 or b<=0:return 1.
    return a/b
