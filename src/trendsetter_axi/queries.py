"""Experimental stdlib-only chart queries. CLI: python -m trendsetter_axi.queries."""
import ast
import bisect
import json
import math
import operator


CONVENTIONS = {
    "linear": "straight segments in axis scale space",
    "step-post": "source knot value until the next knot",
    "step-pre": "next source knot value after the preceding knot",
    "step-mid": "source knot value within arithmetic x-midpoint boundaries; ties take the next source knot",
}
OPS = {"==": operator.eq, "!=": operator.ne, "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


def _ok(answer, evidence, convention):
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value): _need('finite result unavailable; numeric overflow is not a chart value')
        if isinstance(value, dict):
            for v in value.values(): finite(v)
        if isinstance(value, (list, tuple)):
            for v in value: finite(v)
    finite(answer)
    finite(evidence)
    return dict(answer=answer, evidence=evidence, convention=convention)


def _need(message):
    raise ValueError(message)


def _mark(rec, key):
    matches = [m for m in rec["marks"] if m["id"] == key]
    if not matches: matches = [m for m in rec["marks"] if m.get("name") == key]
    if len(matches) != 1: _need(f"mark {key!r} missing or ambiguous; supply a unique mark id")
    return matches[0]


def _finite(values):
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        _need("finite numeric source values required; missing values are not zero")


def _scale(rec, m, axis):
    return rec["axes"][m["axes"]][axis]["scale"]


def _transform(kind, value, inverse=False):
    if kind in ("linear", "date"): return value
    if kind == "log": return math.exp(value) if inverse else math.log(value)
    _need(f"interpolation for {kind!r} scale unavailable; use exact source knots")


def _at(rec, m, x, field="y", probe=None, prepared=None):
    xs, ys = m["x"], m[field]
    target = x if probe is None else probe
    if prepared is None:
        if len(xs) != len(ys) or not xs: _need("nonempty aligned source arrays required")
        _finite([x, *xs, *ys])
        if probe is None and target in xs:
            hits = [ys[i] for i, t in enumerate(xs) if t == target]
            if len(set(hits)) != 1: _need(f"multiple values at x={x}; supply an unambiguous series")
            return hits[0]
        if m["kind"] == "points": _need(f"no point at x={x}; points are not interpolated")
        if not min(xs) <= target <= max(xs): _need(f"x={x} outside the knots {min(xs)}..{max(xs)}; no extrapolation")
        direction = 1 if xs[-1] > xs[0] else -1
        if any(direction * (b - a) <= 0 for a, b in zip(xs, xs[1:])):
            _need("interpolation needs strictly monotone x; duplicate or unordered knots retained, not sorted")
        ordered = [direction * v for v in xs]
    else:
        direction, ordered = prepared
        hit = bisect.bisect_left(ordered, direction * target)
        if probe is None and hit < len(xs) and xs[hit] == target: return ys[hit]
    interp = m.get("interp")
    if interp not in CONVENTIONS: _need("interpolation convention missing or unsupported")
    i = max(0, min(len(xs) - 2, bisect.bisect_right(ordered, direction * target) - 1))
    if i + 1 in m.get("breaks", []): _need(f"missing source interval at x={x}; gap is not interpolated")
    sx, sy = _scale(rec, m, "x"), _scale(rec, m, "y")
    _transform(sx, xs[i])
    _transform(sy, ys[i])
    if interp == "step-post": return ys[i]
    if interp == "step-pre": return ys[i + 1]
    if interp == "step-mid": return ys[i + (direction * target >= direction * ((xs[i] + xs[i + 1]) / 2))]
    tx = lambda v: _transform(sx, v)
    ty = lambda v: _transform(sy, v)
    t = (tx(x) - tx(xs[i])) / (tx(xs[i + 1]) - tx(xs[i]))
    return _transform(sy, ty(ys[i]) + t * (ty(ys[i + 1]) - ty(ys[i])), True)


def _value_at(rec, key, x):
    m = _mark(rec, key)
    if m["kind"] not in ("line", "points", "band"): _need(f"value_at unavailable for {m['kind']}; line, points or band required")
    fields = ("lo", "hi") if m["kind"] == "band" else ("y",)
    values = [_at(rec, m, x, k) for k in fields]
    exact = x in m["x"]
    convention = "exact source knot; no interpolation" if exact else CONVENTIONS.get(m.get("interp"), "points: exact matches only")
    indices = [i for i, t in enumerate(m['x']) if t == x] if exact else next(
        [i, i + 1] for i, (a, b) in enumerate(zip(m['x'], m['x'][1:])) if min(a, b) <= x <= max(a, b))
    support = [dict(row=i, x=m['x'][i], **{k: m[k][i] for k in fields}) for i in indices]
    return _ok(values if len(values) > 1 else values[0],
               dict(mark=m["id"], axes=m["axes"], x=x, fields=dict(zip(fields, values)), support=support), convention)


def _band_width_at(rec, key, x):
    m = _mark(rec, key)
    if m["kind"] != "band": _need("paired band bounds required")
    result = _value_at(rec, key, x)
    lo, hi = result["answer"]
    return _ok(hi - lo, result["evidence"], result["convention"] + "; width = hi - lo in data units")


def _predicate(expression, row):
    """Small expression language, never eval: no calls, attributes or subscripts."""
    if not isinstance(expression, str) or len(expression) > 1024: _need("predicate must be an expression of at most 1024 characters")
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 64: _need("predicate exceeds 64 syntax nodes")
    arithmetic = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    comparisons = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
    def visit(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool, type(None))): return node.value
        if isinstance(node, ast.Name):
            if node.id not in row: _need(f"predicate field {node.id!r} missing; supply that column")
            if row[node.id] is None: _need(f"predicate field {node.id!r} is missing, not zero")
            if isinstance(row[node.id], (int, float)): _finite([row[node.id]])
            return row[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in arithmetic:
            a, b = visit(node.left), visit(node.right)
            _finite([a, b])
            value = arithmetic[type(node.op)](a, b)
            _finite([value])
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else +value if isinstance(node.op, ast.UAdd) else not value
        if isinstance(node, ast.BoolOp):
            return all(visit(n) for n in node.values) if isinstance(node.op, ast.And) else any(visit(n) for n in node.values)
        if isinstance(node, ast.Compare):
            values = [visit(n) for n in [node.left, *node.comparators]]
            if not all(type(op) in comparisons for op in node.ops): _need("unsupported predicate comparison")
            return all(comparisons[type(op)](a, b) for op, a, b in zip(node.ops, values, values[1:]))
        _need("unsupported predicate syntax; only columns, constants, arithmetic, comparisons and and/or/not allowed")
    return bool(visit(tree.body))


def _rows(m):
    fields = {"line": ("x", "y"), "points": ("x", "y"), "band": ("x", "lo", "hi"), "bars": ("x", "base", "top")}.get(m["kind"])
    if fields is None: _need(f"row predicates unavailable for {m['kind']}")
    if len({len(m[k]) for k in fields}) != 1: _need("aligned source arrays required")
    for values in zip(*(m[k] for k in fields)):
        _finite(values)
        row = dict(zip(fields, values))
        if "lo" in row: row["width"] = row["hi"] - row["lo"]
        if "base" in row: row["height"] = row["top"] - row["base"]
        yield row


def _first_x_where(rec, key, predicate):
    m = _mark(rec, key)
    for i, row in enumerate(_rows(m)):
        if _predicate(predicate, row):
            return _ok(row["x"], dict(mark=m["id"], row=i, values=row, predicate=predicate), "first eligible source row in data order; knots only")
    return _ok(None, dict(mark=m["id"], predicate=predicate), "no eligible source knot matches; says nothing between knots")


def _count_where(rec, predicate, table=None):
    if table is None: table = rec.get("records", rec.get("declared", {}).get("records"))
    if table is None: _need("records table or risk table required (one row per subject, e.g. time and event); duplicated subjects draw the same curve")
    if not isinstance(table, list) or not all(isinstance(r, dict) for r in table): _need("records must be a list of row objects")
    n = sum(_predicate(predicate, row) for row in table)
    return _ok(n, dict(matched=n, rows=len(table), predicate=predicate), "count attached rows once each; not inferred from curve or censor marks")


def _crossing(rec, key, other):
    a = _mark(rec, key)
    b = _mark(rec, other) if isinstance(other, str) else None
    marks = [a, b] if b else [a]
    if any(m["kind"] != "line" for m in marks): _need("crossing requires line marks")
    if b and any(rec["axes"][a["axes"]][k] != rec["axes"][b["axes"]][k] for k in "xy"):
        _need("crossing requires shared axis scales and units; explicitly align axes first")
    if not b: _finite([other])
    sx, sy = _scale(rec, a, "x"), _scale(rec, a, "y")
    lo, hi = max(min(m["x"]) for m in marks), min(max(m["x"]) for m in marks)
    if lo > hi: _need("line domains do not overlap")
    knots, prepared = {lo, hi}, {}
    for m in marks:
        if m.get("interp") not in CONVENTIONS: _need("line interpolation convention required")
        # Validate ordering even if a crossing happens to lie at an exact knot.
        xs = m["x"]
        if len(xs) != len(m['y']): _need('aligned source arrays required')
        _finite([*xs, *m['y']])
        direction = 1 if xs[-1] > xs[0] else -1
        prepared[id(m)] = (direction, [direction * x for x in xs])
        if len(xs) > 1 and not (all(v > u for u, v in zip(xs, xs[1:])) or all(v < u for u, v in zip(xs, xs[1:]))):
            _need("crossing requires strictly monotone, unique x knots")
        knots.update(x for x in xs if lo <= x <= hi)
        if m["interp"] == "step-mid": knots.update((u + v) / 2 for u, v in zip(xs, xs[1:]) if lo <= (u + v) / 2 <= hi)
    xs = sorted(knots)
    def delta(x, probe=None):
        vals = [_at(rec, m, x, probe=probe, prepared=prepared[id(m)]) for m in marks]
        if not b: vals.append(other)
        return _transform(sy, vals[0]) - _transform(sy, vals[1])
    convention = "first equality or sign change in increasing x; jumps reported at boundary, not as equality; no extrapolation"
    evidence = dict(marks=[m["id"] for m in marks], threshold=None if b else other)
    previous = None
    for i, x in enumerate(xs):
        d = delta(x)
        if d == 0 or previous is not None and previous * d < 0:
            return _ok(x, dict(evidence, boundary=x, difference=d), convention)
        if i + 1 == len(xs): break
        end = xs[i + 1]
        mid = (x + end) / 2
        left, right = delta(x, mid), delta(end, mid)
        if left == 0 or left * d < 0: return _ok(x, dict(evidence, interval=[x, end]), convention)
        if left * right < 0:
            t = left / (left - right)
            tx = _transform(sx, x) + t * (_transform(sx, end) - _transform(sx, x))
            return _ok(_transform(sx, tx, True), dict(evidence, interval=[x, end], differences=[left, right]), convention + "; solved in axis scale space")
        previous = right
    return _ok(None, evidence, convention + "; no crossing on shared domain")


def _check(rec, claim):
    operation, *args, op, wanted = claim
    if operation not in ("value_at", "band_width_at", "first_x_where", "crossing", "count_where"): _need("claim must name a scalar query")
    if op not in OPS: _need("claim comparison unsupported")
    result = query(rec, operation, *args)
    if "unavailable" in result:
        return dict(result, verdict="unavailable", computed=None, claimed=wanted)
    computed = result["answer"]
    verdict = OPS[op](computed, wanted)
    return dict(_ok(verdict, result["evidence"], result["convention"] + "; exact comparison " + op), verdict=verdict, computed=computed, claimed=wanted)


def _diff(a, b):
    # Local ids are not cross-chart identities. Match unique (axes, name, kind).
    def index(rec):
        out = {}
        for m in rec["marks"]:
            key = (m["axes"], m.get("name"), m["kind"])
            if key in out: _need("diff identity ambiguous; unique names per axes/kind required")
            out[key] = m
        return out
    aa, bb = index(a), index(b)
    changes = []
    for key in sorted(aa.keys() | bb.keys(), key=repr):
        before, after = aa.get(key), bb.get(key)
        left = {k: v for k, v in (before or {}).items() if k != "id"}
        right = {k: v for k, v in (after or {}).items() if k != "id"}
        fields = {k: dict(before=left.get(k), after=right.get(k)) for k in sorted(left.keys() | right.keys()) if left.get(k) != right.get(k)}
        if fields: changes.append(dict(identity=list(key), fields=fields))
    axes = None if a["axes"] == b["axes"] else dict(before=a["axes"], after=b["axes"])
    return _ok(dict(marks=changes, axes=axes, declared=None if a.get("declared") == b.get("declared") else dict(before=a.get("declared"), after=b.get("declared"))),
               dict(before=len(aa), after=len(bb)), "exact stored-array/axis/declaration comparison; unique axes/name/kind identities; no tolerance, resampling or inferred pairs")


def _facts(rec):
    facts = []
    for m in rec["marks"]:
        item = dict(mark=m["id"], kind=m["kind"], axes=m["axes"])
        if m["kind"] in ("line", "points", "band", "bars"):
            rows = list(_rows(m))
            item["n"] = len(rows)
            field = "width" if m["kind"] == "band" else "height" if m["kind"] == "bars" else "y"
            if rows and _scale(rec, m, 'x' if m.get('orientation') == 'h' else 'y') != 'category':
                item.update(min=min(r[field] for r in rows), max=max(r[field] for r in rows), field=field)
        elif m["kind"] == "segments": item["n"] = len(m["segments"])
        elif m["kind"] == "heat": item.update(rows=len(m["z"]), missing=sum(v is None for row in m["z"] for v in row))
        elif m["kind"] == "area": item["n"] = len(m["polygons"])
        facts.append(item)
    return _ok(dict(marks=facts, declared=rec.get("declared", {}), unavailable=rec.get("unavailable", []) +
                    ["Totals, pairwise aggregates, correlations and interval meaning are unavailable without explicit author intent; declarations are assertions, not inferred facts."]),
               dict(marks=[m["id"] for m in rec["marks"]]), "eligible stored geometry only; extrema over knots, not a population; no intent-dependent aggregates")


def query(record, operation, *args):
    """Answer with evidence/convention, or unavailable naming the missing input.

    Operations: value_at(mark,x), band_width_at(mark,x), first_x_where(mark,expr),
    crossing(line,line_or_number), count_where(expr,table=None), check(claim),
    diff(other_record), facts(). Predicates use row column names, not Python code.
    """
    functions = dict(value_at=_value_at, band_width_at=_band_width_at, first_x_where=_first_x_where,
                     crossing=_crossing, count_where=_count_where, check=_check, diff=_diff, facts=_facts)
    try:
        if operation not in functions: _need(f"unknown operation {operation!r}; choose from {', '.join(functions)}")
        return functions[operation](record, *args)
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError, OverflowError, SyntaxError, StopIteration) as exc:
        reason = f"record field {exc.args[0]!r} missing; supply a complete record" if isinstance(exc, KeyError) else str(exc)
        return dict(answer=None, unavailable=reason or 'aligned source arrays and axis metadata required', evidence=dict(operation=operation), convention="no inference or extrapolation when required input/convention is unavailable")


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", help="saved record JSON")
    parser.add_argument("operation")
    parser.add_argument("args", nargs="*", help="JSON values, or bare strings; diff takes another record filename")
    args = parser.parse_args()
    def value(s):
        try: return json.loads(s)
        except json.JSONDecodeError: return s
    try:
        with open(args.record) as f: record = json.load(f)
        values = [value(s) for s in args.args]
        if args.operation == "diff" and len(values) == 1 and isinstance(values[0], str):
            with open(values[0]) as f: values[0] = json.load(f)
        print(json.dumps(query(record, args.operation, *values), allow_nan=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"record input unavailable: {exc}\n")


if __name__ == "__main__": main()
