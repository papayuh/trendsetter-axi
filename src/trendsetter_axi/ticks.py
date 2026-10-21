"""Tick label formatting: one decimal count per axis, negative zero suppressed."""
import math, re
import numpy as np


def number_formatter(values, n=3, *, exact=False, min_decimals=0, distinct=True, persig=None, decimals=None, max_decimals=None):
    """One numeric scope, one decimal count; no per-value k/M units.

    Compact scopes retain at least n significant digits at the smallest
    magnitude, increasing precision for close values. Exact scopes retain
    supplied decimal precision. Very wide domains use one
    scientific notation policy, not clipped digits or tiny values rounded to 0.
    Missing values do not affect precision; negative zero is suppressed.
    """
    from decimal import Decimal
    finite = [float(v) for v in np.asarray(values, float).reshape(-1) if math.isfinite(v)]
    nonzero = [v for v in finite if v]
    fixed = decimals is not None
    if fixed: decimals = max(0, int(decimals))
    elif exact:
        decimals = max([min_decimals] + [max(0, -Decimal(str(v)).normalize().as_tuple().exponent) for v in finite])
    else:
        decimals = max([min_decimals] + [max(0, n - 1 - math.floor(math.log10(abs(v)))) for v in nonzero])
        if finite and all(v.is_integer() for v in finite): decimals = min_decimals
        elif distinct:
            # A common decimal count must not invent ties in close values.
            initial = decimals
            while decimals < initial + 4 and len({round(v, decimals) for v in finite}) < len(set(finite)):
                decimals += 1
            n += decimals - initial
    if max_decimals is not None: decimals = min(decimals,max_decimals)
    widest = max([1] + [len(f"{v:.{decimals}f}") for v in finite])
    scientific = widest > 24
    # True significant digits (tables/footers/bars; axes keep one decimal count): when one common decimal count would pad
    # a value with 2+ trailing zeros (0.0642 beside 2.0300), each value gets its own digits and no trailing zeros.
    if not fixed and (exact if persig is None else persig) and nonzero and not scientific:
        clean = lambda v: float(f"{v:.12g}") if re.search(r"(9{6,}|0{6,})\d{0,3}$", repr(float(v)).split("e")[0]) else v   # binary-float tails (0.2399999999999998)
        own = lambda v: min(max_decimals if max_decimals is not None else 10000,
                           max(0, -Decimal(repr(float(clean(v)))).normalize().as_tuple().exponent)
                           if exact else max(0, n - 1 - math.floor(math.log10(abs(v)))))
        if not all(v.is_integer() for v in finite) and max(own(v) for v in nonzero) - min(own(v) for v in nonzero) >= 2:
            def fmt(v):
                if not math.isfinite(v): return "n/a"
                if v == 0: return "0"
                d = own(v); t = f"{round(float(clean(v)), d):.{d}f}"
                return t.rstrip("0").rstrip(".") if "." in t else t
            return fmt
    if scientific:
        digits = max([n] + [len(Decimal(str(v)).normalize().as_tuple().digits) for v in nonzero]) if exact else n
        decimals = max(0, digits - 1)
    def fmt(v):
        if not math.isfinite(v): return "n/a"
        if scientific: return f"{v:.{decimals}e}"
        v = round(float(v), decimals)
        return f"{0.0 if v == 0 else v:.{decimals}f}"
    return fmt


def tick_formatter(ticks, n=3, *, strict=False, min_decimals=0):
    """One decimal count per axis/scope, with negative zero suppressed.

    strict=True caps displayed precision at n significant digits; close values
    may share a rounded label, never an assignment bin. Legacy axes retain
    distinct ticks by raising precision. Both policies share this formatter.
    """
    ticks = [float(t) for t in ticks]
    fin = sorted({t for t in ticks if math.isfinite(t)})
    if strict:
        # Display only: never feed rounded labels back into bin assignment.
        # A scope has ONE decimal count, capped by its largest magnitude.
        # Wide domains use a common scientific mantissa rather than erasing
        # small values. Carries are included when selecting that precision.
        nonzero = [abs(t) for t in fin if t]
        largest = float(f'{max(nonzero, default=1):.{n}g}')
        scientific = bool(nonzero and (largest >= 1e4 or largest < 1e-3 or
                                      largest / min(nonzero) >= 1e3))
        decimals = n - 1 if scientific else max(0,n-1-math.floor(math.log10(largest)))
        if not scientific:
            while decimals > min_decimals and all(round(t, decimals) == round(t, decimals-1) for t in fin):
                decimals -= 1
        def fmt(v):
            if not math.isfinite(v): return 'n/a'
            if scientific:
                # Formatting can carry; .g first prevents a four-digit mantissa.
                value = float(f'{float(v):.{n}g}')
                return f'{0.0 if value == 0 else value:.{decimals}e}'
            value = round(float(f'{float(v):.{n}g}'), decimals)
            return f'{0.0 if value == 0 else value:.{decimals}f}'
        fmt.scope = lambda values, **kw: tick_formatter(values, n, strict=True, **kw)
        return fmt
    if any(t and (abs(t) < 1e-4 or abs(t) >= 1e12) for t in fin) or len(fin) < 2: return number_formatter(ticks)
    step = (fin[-1] - fin[0]) / (len(fin) - 1)
    d = max(0, n - 1 - math.floor(math.log10(step)))
    while d < 12 and len({round(t, d) for t in fin}) < len(fin): d += 1
    while d > 0 and all(f"{t:.{d}f}".endswith("0") for t in fin): d -= 1
    return lambda v: "n/a" if not math.isfinite(v) else f"{(0.0 if round(v, d) == 0 else v):.{d}f}"
