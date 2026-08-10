"""
curve_extract.py — reading the PLOTTED curves off a datasheet (M7).
===================================================================
Phases 1 and 2 of the datasheet-first plan read TABLES. Everything a table cannot carry has been
standing in as a fitted shape ever since: the MOSFET's E_oss(V) is a V^1.5 extrapolation through one
published point, C_rss is left unmapped because a single value cannot describe a shape, and a diode
that publishes V_F at one current per temperature gets a CONSTANT forward drop (C210), which
understates conduction at the current peak. The numbers those shapes stand for are printed on the
page, in the figures.

WHY THIS IS NOT PIXEL DIGITISING. The plan assumed a raster tracer — threshold the image, follow the
ink, guess the axes. These datasheets are VECTOR: the curve is a stroked path whose control points
are already in page coordinates, exact to the point where the only real error is reading the axes.
So the curve is not traced, it is READ; a raster fallback is still needed for scanned datasheets and
is not built here.

THE CALIBRATION IS THE WHOLE PROBLEM, AND IT IS CHECKABLE. Tick labels are text with positions, so
the pixel-to-value map is a fit through them — and the RESIDUAL of that fit is the evidence it was
read correctly. A plot whose ticks do not fit a consistent linear or logarithmic scale is not
proposed at all. Better still, most curves can be checked against the part's OWN table: the VS-3C40
tabulates V_F = 1.35 V at 20 A, 25 degC, and the digitised 25 degC curve gives 19.5 A at 1.35 V.
That agreement is what says the axes were read right, and it is the same species of check as the
Q_c power-law fit reproducing the published charge at C211.

NOTHING HERE IS TRUSTED. Every function returns a PROPOSAL carrying its own evidence — the fit
residual, the cross-check against the table, the axis titles it believes it read. The designer
confirms against a rendered image of the figure before any of it reaches the engine, exactly as the
extracted table values are confirmed. A curve is a shape somebody has to recognise.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

# Ticks closer to the frame than this (points) are treated as belonging to that axis.
_TICK_BAND = 26.0
# A tick label must sit within this much of the frame's span to count as one of its ticks.
_TICK_SPAN_SLACK = 12.0
# A calibration fit worse than this (relative) is not proposed.
_MAX_FIT_RESIDUAL = 0.02
# Bezier flattening: segments per curve item. 12 puts the chord error far below the stroke width.
_BEZIER_STEPS = 12

_NUM = re.compile(r"^[+-]?\d{1,3}(?:[  ,]\d{3})*(?:\.\d+)?$|^[+-]?\d*\.?\d+$")


def _as_number(text: str) -> Optional[float]:
    """A tick label, or None. Vendors write thousands as '10 000' and '10,000'."""
    t = (text or "").strip().replace(" ", " ")
    if not _NUM.match(t):
        return None
    try:
        return float(t.replace(" ", "").replace(",", ""))
    except ValueError:
        return None


# ── geometry ──────────────────────────────────────────────────────────────────────────────────
def _bezier(p0, p1, p2, p3, n: int = _BEZIER_STEPS):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1.0 - t
        out.append((u**3 * p0.x + 3*u*u*t * p1.x + 3*u*t*t * p2.x + t**3 * p3.x,
                    u**3 * p0.y + 3*u*u*t * p1.y + 3*u*t*t * p2.y + t**3 * p3.y))
    return out


def path_points(path: dict) -> list[tuple[float, float]]:
    """Flatten one drawing path to a polyline in PAGE coordinates."""
    pts: list[tuple[float, float]] = []
    for it in path.get("items", []):
        kind = it[0]
        if kind == "l":
            pts.append((it[1].x, it[1].y))
            pts.append((it[2].x, it[2].y))
        elif kind == "c":
            pts.append((it[1].x, it[1].y))
            pts.extend(_bezier(it[1], it[2], it[3], it[4]))
        elif kind == "qu":                        # quad — its corners, enough to bound it
            for q in it[1]:
                pts.append((q.x, q.y))
    return pts


def _axis_parallel(items, tol: float = 0.6) -> bool:
    """Every segment runs along one axis — the signature of a frame or a gridline group."""
    n = 0
    for it in items:
        if it[0] != "l":
            return False
        if abs(it[1].x - it[2].x) > tol and abs(it[1].y - it[2].y) > tol:
            return False
        n += 1
    return n > 0


def find_plots(page, min_w: float = 80.0, min_h: float = 60.0) -> list[dict]:
    """Axes frames on a page, big enough to be a plot.

    Most vendors draw the axes box as a single `re`. Some draw it as four lines, and some draw no
    box at all — but every plot has a GRIDLINE GROUP, a path of axis-parallel segments whose
    bounding box is the plot area. Both are accepted, because Figs 8 and 9 of the reference diode
    datasheet (capacitive charge and energy versus reverse voltage — the two the C211 grading fit
    wants) are drawn the second way and were invisible to a rectangle-only search.

    A page of a datasheet is otherwise full of rectangles and rules, so the size floor does the
    separating, and near-duplicate boxes are merged: the frame, the gridlines and the clip path all
    describe the same plot.
    """
    cands = []
    for a in page.get_drawings():
        r = a["rect"]
        if r.width < min_w or r.height < min_h:
            continue
        items = a.get("items", [])
        if any(it[0] == "re" for it in items):
            cands.append((r, 0))                       # an explicit frame outranks a gridline group
        elif len(items) >= 6 and _axis_parallel(items):
            cands.append((r, 1))
    out: list[dict] = []
    for r, rank in sorted(cands, key=lambda c: (c[1], -c[0].width * c[0].height)):
        if any(abs(r.x0 - o["rect"][0]) < 8 and abs(r.y0 - o["rect"][1]) < 8 and
               abs(r.x1 - o["rect"][2]) < 8 and abs(r.y1 - o["rect"][3]) < 8 for o in out):
            continue                                   # same plot, described twice
        out.append({"rect": (r.x0, r.y0, r.x1, r.y1), "width": r.width, "height": r.height})
    # Only when no frame was drawn at all. Additive: a vendor that draws frames is untouched.
    if not out:
        out.extend(find_plots_by_ticks(page, min_w, min_h))
    out.sort(key=lambda f: (round(f["rect"][1], 1), f["rect"][0]))
    return out


# A superscript is smaller than its base, starts at its right edge, and its centre sits higher.
_SUP_SIZE_RATIO = 0.85
_SUP_RISE = 0.8
_SUP_GAP = 7.0


def reassembled_labels(page, clip=None) -> list[tuple[float, float, float]]:
    """Numeric axis labels as (x_centre, y_centre, value), rebuilt from FRAGMENTED text runs.

    Some vendors position their axis labels rather than typesetting them, so one label arrives as
    several runs: a decade as a base "10" and a raised "3", a decimal as "0" and ".05". Read run by
    run, an axis labelled 1 / 10 / 100 / 1000 yields the numbers 10, 1, 10, 2, 10, 3 and fits
    nothing.

    THIS IS A FALLBACK, NOT A REPLACEMENT. It runs only where the plain reading has already failed
    to fit — an earlier attempt made it the primary reader and broke 16 of 23 tests on the two
    vendors that were working, because reassembly changes what a correctly-read label means.
    """
    spans = []
    for b in page.get_text("dict", clip=clip)["blocks"]:
        for l in b.get("lines", []):
            for sp in l.get("spans", []):
                t = sp["text"].strip()
                if t:
                    spans.append({"t": t, "bb": sp["bbox"], "size": sp["size"]})
    spans.sort(key=lambda sp: (round(sp["bb"][1], 1), sp["bb"][0]))

    out: list[tuple[float, float, float]] = []
    used = set()
    for i, sp in enumerate(spans):
        if i in used:
            continue
        base = _as_number(sp["t"])
        bb = sp["bb"]
        cy = (bb[1] + bb[3]) / 2.0
        # "0" + ".05" -> 0.05 : a decimal split at the point, same size, same line, touching
        joined = None
        for j, nx in enumerate(spans):
            if j == i or j in used:
                continue
            nb = nx["bb"]
            if (abs(nx["size"] - sp["size"]) < 0.3 and abs(nb[1] - bb[1]) < 1.0
                    and -1.0 <= nb[0] - bb[2] <= 2.0 and nx["t"].startswith(".")):
                joined = _as_number(sp["t"] + nx["t"])
                if joined is not None:
                    used.add(j)
                    out.append(((bb[0] + nb[2]) / 2.0, cy, joined))
                break
        if joined is not None:
            continue
        if base is None:
            continue
        # "10" + raised "3" -> 1000
        for j, ex in enumerate(spans):
            if j == i or j in used:
                continue
            eb, esz = ex["bb"], ex["size"]
            ev = _as_number(ex["t"])
            if ev is None or ev != int(ev) or abs(ev) > 12:
                continue
            if (esz <= sp["size"] * _SUP_SIZE_RATIO
                    and -1.5 <= eb[0] - bb[2] <= _SUP_GAP
                    and cy - (eb[1] + eb[3]) / 2.0 >= _SUP_RISE
                    and eb[1] < bb[3]):
                used.add(j)
                out.append(((bb[0] + eb[2]) / 2.0, cy, base ** ev if base else 0.0))
                break
        else:
            out.append(((bb[0] + bb[2]) / 2.0, cy, base))
    return out


def _tick_clusters(labels, along: int, tol: float, min_n: int, min_span: float):
    """Group labels that line up along one axis — a tick row or a tick column."""
    other = 1 - along
    buckets: dict[int, list] = {}
    for lab in labels:
        buckets.setdefault(int(round(lab[other] / tol)), []).append(lab)
    out = []
    for group in buckets.values():
        if len(group) < min_n:
            continue
        vals = [g[along] for g in group]
        if max(vals) - min(vals) < min_span:
            continue
        out.append(sorted(group, key=lambda g: g[along]))
    return out


def find_plots_by_ticks(page, min_w: float = 80.0, min_h: float = 60.0) -> list[dict]:
    """Plot areas inferred from the TICK LABELS, for datasheets that draw no axes box.

    Some vendors draw no frame and no gridline group — just the curves, two axis lines and the
    labels — so a frame-shaped search finds nothing on them at all. What every plot does have is a
    ROW of numeric labels beneath it and a COLUMN beside it; the plot is what they bracket. Each row
    takes the ONE nearest column that belongs to it: pairing every row with every column to its left
    builds nested frames spanning whole page columns, whose mixed tick sets then fit nothing.
    """
    labels = reassembled_labels(page)
    rows = _tick_clusters(labels, along=0, tol=3.0, min_n=3, min_span=60.0)
    cols = _tick_clusters(labels, along=1, tol=6.0, min_n=3, min_span=50.0)
    out = []
    for r in rows:
        rx0, rx1 = r[0][0], r[-1][0]
        ry = sum(l[1] for l in r) / len(r)
        best, best_d = None, 1e9
        for c in cols:
            cx = sum(l[0] for l in c) / len(c)
            cy0, cy1 = c[0][1], c[-1][1]
            if not (rx0 - 70.0 <= cx <= rx0 + 12.0):
                continue
            if not (0.0 <= ry - cy1 <= 34.0):
                continue
            d = (rx0 - cx) + (ry - cy1)
            if d < best_d:
                best, best_d = (cx, cy0, cy1), d
        if best is None:
            continue
        cx, cy0, cy1 = best
        x0, y0, x1, y1 = cx + 6.0, cy0 - 6.0, rx1 + 6.0, ry - 6.0
        if x1 - x0 < min_w or y1 - y0 < min_h:
            continue
        out.append({"rect": (x0, y0, x1, y1), "width": x1 - x0, "height": y1 - y0, "from": "ticks"})
    return out


def _text_items(page, clip=None):
    import fitz
    blocks = page.get_text("dict", clip=clip)["blocks"]
    for b in blocks:
        for l in b.get("lines", []):
            txt = "".join(s["text"] for s in l["spans"]).strip()
            if txt:
                yield txt, l["bbox"]


# ── calibration ───────────────────────────────────────────────────────────────────────────────
def _fit_axis(ticks: list[tuple[float, float]]) -> Optional[dict]:
    """Fit position -> value over the tick labels, linear or logarithmic, and report the residual.

    The residual is the point: it is the only evidence available that the labels were associated
    with the right axis and read in the right order. A plot with a second axis on the far side, or
    a legend full of numbers, produces a bad fit rather than a confident wrong answer.
    """
    ticks = sorted(set(ticks))
    # THREE, NOT TWO. Any two points fit a straight line with residual exactly zero, so a 2-tick
    # axis passes the residual gate no matter which labels were picked up — the check cannot fail,
    # which means it is not a check. Found on the LVE5060E: Fig. 3's x axis came back [0, 4], which
    # is its Y axis (0, 4, 8 ... W) read as X, and it was reported as calibrated with residual 0.
    # A third tick is what makes the residual able to reject anything.
    if len(ticks) < 3:
        return None

    def _lsq(pairs):
        n = len(pairs)
        sx = sum(p for p, _ in pairs); sy = sum(v for _, v in pairs)
        sxx = sum(p * p for p, _ in pairs); sxy = sum(p * v for p, v in pairs)
        den = n * sxx - sx * sx
        if abs(den) < 1e-12:
            return None
        m = (n * sxy - sx * sy) / den
        c = (sy - m * sx) / n
        if m == 0:
            return None
        span = max(v for _, v in pairs) - min(v for _, v in pairs)
        if span == 0:
            return None
        resid = max(abs((m * p + c) - v) for p, v in pairs) / span
        return {"m": m, "c": c, "residual": resid}

    def _consensus(pairs):
        """Fit the largest set of ticks that agree, and ignore the rest.

        A tick row is not clean. The y axis's bottom label sits at the corner and reads as an x
        tick; the neighbouring plot's first label sits just past the right edge and reads as one
        too. Least squares has no defence against either — ONE outlier drags the line and inflates
        the residual until a perfectly readable axis is refused. That is what hid the LVE5060E's
        Fig. 4, the forward characteristic: twelve ticks spaced exactly 13.4 pt apart, plus two
        strays, fitting nothing.

        So the line is chosen by CONSENSUS: every pair of ticks proposes one, and the proposal
        that the most ticks agree with wins. The agreeing set must still be a clear majority and
        must still span most of the axis, because a handful of strays that happen to line up is
        exactly what this must not accept.
        """
        n = len(pairs)
        span = max(v for _, v in pairs) - min(v for _, v in pairs)
        if span <= 0:
            return None
        tol = 0.02 * span
        best_in = None
        for i in range(n):
            for j in range(i + 1, n):
                (p1, v1), (p2, v2) = pairs[i], pairs[j]
                if p2 == p1:
                    continue
                m = (v2 - v1) / (p2 - p1)
                c = v1 - m * p1
                inl = [(p, v) for p, v in pairs if abs(m * p + c - v) <= tol]
                if best_in is None or len(inl) > len(best_in):
                    best_in = inl
        if best_in is None or len(best_in) < 3 or len(best_in) < 0.6 * n:
            return None
        pos = [p for p, _ in best_in]
        allpos = [p for p, _ in pairs]
        if (max(pos) - min(pos)) < 0.5 * (max(allpos) - min(allpos)):
            return None
        out = _lsq(best_in)
        if out is not None:
            # the range is what the AGREEING ticks cover — reporting it over all of them would
            # advertise an axis reaching values the fit deliberately ignored
            out["inliers"] = len(best_in)
            out["_range"] = [min(v for _, v in best_in), max(v for _, v in best_in)]
        return out

    lin = _consensus(ticks)
    log = None
    if all(v > 0 for _, v in ticks):
        log = _consensus([(p, math.log10(v)) for p, v in ticks])

    best, scale = lin, "linear"
    if log and (best is None or log["residual"] < best["residual"]):
        best, scale = log, "log"
    if best is None or best["residual"] > _MAX_FIT_RESIDUAL:
        return None
    rng = best.get("_range") or [min(v for _, v in ticks), max(v for _, v in ticks)]
    if scale == "log":
        rng = [10.0 ** rng[0], 10.0 ** rng[1]]
    return {"scale": scale, "m": best["m"], "c": best["c"],
            "residual": round(best["residual"], 5), "n_ticks": len(ticks),
            "inliers": best.get("inliers", len(ticks)),
            "range": [round(rng[0], 6), round(rng[1], 6)]}


def _apply(cal: dict, pos: float) -> float:
    v = cal["m"] * pos + cal["c"]
    return 10.0 ** v if cal["scale"] == "log" else v


def calibrate(page, frame: tuple) -> dict:
    """Propose the pixel-to-data mapping for one plot, from the tick labels around it."""
    import fitz
    x0, y0, x1, y1 = frame

    bottom, left = [], []
    clip = fitz.Rect(x0 - 60, y0 - 20, x1 + 60, y1 + _TICK_BAND + 14)
    for txt, bb in _text_items(page, clip):
        val = _as_number(txt)
        if val is None:
            continue
        cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
        # below the frame, horizontally inside it -> an x tick
        if y1 <= bb[1] <= y1 + _TICK_BAND and x0 - _TICK_SPAN_SLACK <= cx <= x1 + _TICK_SPAN_SLACK:
            bottom.append((cx, val))
        # left of the frame, vertically inside it -> a y tick
        elif bb[2] <= x0 + 2 and x0 - _TICK_BAND - 20 <= bb[2] and y0 - 6 <= cy <= y1 + 6:
            left.append((cy, val))

    cal_x, cal_y = _fit_axis(bottom), _fit_axis(left)
    # FALLBACK, in that order. A label the plain reading got right must keep its meaning; only an
    # axis that fitted nothing is re-read with fragments reassembled.
    if not (cal_x and cal_y):
        b2, l2 = [], []
        for cx, cy, val in reassembled_labels(page, clip):
            if y1 - 2 <= cy <= y1 + _TICK_BAND and x0 - _TICK_SPAN_SLACK <= cx <= x1 + _TICK_SPAN_SLACK:
                b2.append((cx, val))
            elif cx <= x0 + 4 and x0 - _TICK_BAND - 24 <= cx and y0 - 8 <= cy <= y1 + 8:
                l2.append((cy, val))
        cal_x = cal_x or _fit_axis(b2)
        cal_y = cal_y or _fit_axis(l2)
        if b2 or l2:
            bottom, left = bottom or b2, left or l2
    titles = _axis_titles(page, frame)
    return {
        "frame": list(frame),
        "x": cal_x, "y": cal_y,
        "x_ticks": len(bottom), "y_ticks": len(left),
        "titles": titles,
        "ok": bool(cal_x and cal_y),
        "reason": ("" if (cal_x and cal_y) else
                   "the tick labels around this frame do not fit a consistent linear or "
                   "logarithmic scale, so no mapping is proposed"),
    }


def _axis_titles(page, frame: tuple) -> dict:
    """The axis captions, which say WHAT was plotted — the designer's main confirmation cue."""
    import fitz
    x0, y0, x1, y1 = frame
    # The nearest non-numeric line, not the longest: the FIGURE CAPTION also sits under the plot
    # and is longer, so "longest" reliably returned the caption instead of the axis title.
    def _nearest(clip, key):
        best, best_d = "", 1e9
        for txt, bb in _text_items(page, clip):
            # A rotated y-axis title arrives as one line, but so do the stacked tick labels of a
            # log axis ("0 5", "0 01"), which are digits with spaces and parse as neither number
            # nor title. Require some letters.
            letters = sum(ch.isalpha() for ch in txt)
            if (_as_number(txt) is not None or re.match(r"^Fig\.?\s*\d", txt)
                    or len(txt) < 3 or letters < 3):
                continue
            d = key(bb)
            if d < best_d:
                best, best_d = txt, d
        return best

    xt = _nearest(fitz.Rect(x0 - 12, y1 + 8, x1 + 12, y1 + 46), lambda bb: bb[1] - y1)
    yt = _nearest(fitz.Rect(x0 - 62, y0 - 8, x0 + 4, y1 + 8), lambda bb: x0 - bb[2])
    return {"x": xt, "y": yt}


# ── the curves ────────────────────────────────────────────────────────────────────────────────
def _centreline(pts: list[tuple[float, float]], x0: float, x1: float,
                bins: int = 120) -> list[tuple[float, float]]:
    """Reduce a filled RIBBON to the line it draws.

    Some vendors do not stroke their curves: the renderer converts the stroke to a filled outline,
    so the path runs out along one edge of the line and back along the other. Its two edges are half
    a stroke-width either side of the real curve, so the midpoint of the ribbon at each x IS the
    curve. Binning in x and averaging the extremes recovers it without needing to know which
    direction the outline was walked.
    """
    if x1 <= x0:
        return pts
    w = (x1 - x0) / bins
    buckets: dict[int, list[float]] = {}
    for px, py in pts:
        buckets.setdefault(int((px - x0) / w), []).append(py)
    out = []
    for b in sorted(buckets):
        ys = buckets[b]
        out.append((x0 + (b + 0.5) * w, (min(ys) + max(ys)) / 2.0))
    return out


def curves_in(page, frame: tuple, cal: dict, min_points: int = 4) -> list[dict]:
    """Every stroked curve inside a plot frame, in DATA coordinates.

    A path is a curve if it is stroked, has enough points inside the frame, and is not the frame
    itself or a gridline. Points outside the frame are dropped rather than clamped: a PDF clips the
    plot to its axes, and a Bezier control point can legitimately sit outside the visible area.
    """
    import fitz
    x0, y0, x1, y1 = frame
    rect = fitz.Rect(x0, y0, x1, y1)
    out = []
    for a in page.get_drawings():
        if not a["rect"].intersects(rect):
            continue
        # A curve is either STROKED, or written as a filled outline of a stroke. The second is how
        # Figs 8 and 9 of the reference diode datasheet are drawn, and skipping unstroked paths
        # made those two figures — the capacitive charge and energy curves — come back empty.
        filled = (a.get("type") or "").startswith("f") and a.get("width") in (None, 0)
        if not filled and a.get("width") in (None, 0):
            continue
        if filled:
            col = tuple(a.get("fill") or ())
            # black and white fills are the grid, the ticks and the plot background
            if not col or all(c < 0.15 for c in col) or all(c > 0.85 for c in col):
                continue
        if any(it[0] == "re" for it in a.get("items", [])):
            continue                              # the frame, legend swatches, table rules
        pts = [(px, py) for px, py in path_points(a)
               if x0 - 0.5 <= px <= x1 + 0.5 and y0 - 0.5 <= py <= y1 + 0.5]
        if len(pts) < 2:
            continue
        xs = {round(p[0], 1) for p in pts}; ys = {round(p[1], 1) for p in pts}
        # A gridline is AXIS-PARALLEL — constant in one coordinate. A straight but SLOPED line is
        # data: Fig. 7's forward-power-loss lines are single straight segments, and testing
        # "straight means gridline" threw them away along with the grid.
        if len(xs) < 2 or len(ys) < 2:
            continue
        # ...and a legend swatch is a short sloped line, so require a real span across the plot
        span = max((max(p[0] for p in pts) - min(p[0] for p in pts)) / max(x1 - x0, 1e-9),
                   (max(p[1] for p in pts) - min(p[1] for p in pts)) / max(y1 - y0, 1e-9))
        if span < 0.15:
            continue
        if len(pts) < min_points and len(a.get("items", [])) > 1:
            continue
        if filled:
            pts = _centreline(pts, x0, x1)
        data = [(_apply(cal["x"], px), _apply(cal["y"], py)) for px, py in pts]
        data.sort()
        out.append({
            "color": [round(c, 4) for c in (a.get("color") or a.get("fill") or [])],
            "drawn_as": "fill" if filled else "stroke",
            "width": a.get("width"),
            "n_points": len(data),
            "x": [round(v, 6) for v, _ in data],
            "y": [round(v, 6) for _, v in data],
            "x_span": [round(min(v for v, _ in data), 6), round(max(v for v, _ in data), 6)],
            "y_span": [round(min(v for _, v in data), 6), round(max(v for _, v in data), 6)],
        })
    out.sort(key=lambda c: -c["n_points"])
    return out


def value_at(curve: dict, x: float) -> Optional[float]:
    """Interpolate the curve at x, or None outside its span."""
    xs, ys = curve["x"], curve["y"]
    if not xs or x < xs[0] or x > xs[-1]:
        return None
    for (xa, ya), (xb, yb) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if xa <= x <= xb:
            if xb == xa:
                return ya
            return ya + (yb - ya) * (x - xa) / (xb - xa)
    return ys[-1]


def cross_check(curves: list[dict], x: float, y: float, tol_pct: float = 10.0) -> dict:
    """Does any digitised curve pass through a point the datasheet TABLE states?

    This is the acceptance test for a whole figure. The axes can be misread, the wrong label set can
    be picked up, the scale can be taken as linear when it is logarithmic — and every one of those
    shows up here, because the table and the plot are independent renderings of the same
    measurement. A figure that cannot be checked this way is proposed with lower standing.
    """
    best = None
    for i, c in enumerate(curves):
        got = value_at(c, x)
        if got is None or y == 0:
            continue
        err = abs(got - y) / abs(y) * 100.0
        if best is None or err < best["error_pct"]:
            best = {"curve_index": i, "expected": y, "got": round(got, 4),
                    "error_pct": round(err, 2), "color": c["color"]}
    if best is None:
        return {"checked": False, "agrees": False,
                "note": f"no digitised curve covers x = {x:g}, so the figure could not be checked "
                        f"against the datasheet's own tabulated point"}
    best["checked"] = True
    best["agrees"] = best["error_pct"] <= tol_pct
    best["note"] = (
        f"The table states {y:g} at x = {x:g}; the closest digitised curve gives "
        f"{best['got']:g}, {best['error_pct']:.1f} % apart. "
        + ("The plot and the table are independent renderings of the same measurement, so this "
           "agreement is what says the axes were read correctly."
           if best["agrees"] else
           "They disagree, which means the axes or the curve were misread — the calibration is "
           "not usable as it stands."))
    return best


def render(page, frame: tuple, pad: float = 34.0, zoom: float = 3.0) -> bytes:
    """The figure as a PNG, so the designer can confirm the proposal against what is printed."""
    import fitz
    x0, y0, x1, y1 = frame
    clip = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
    return pix.tobytes("png")


def digitise(pdf_bytes: bytes, page_no: Optional[int] = None) -> dict:
    """Every plot in the document, with its calibration, its curves and its own evidence."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    figures = []
    pages = [page_no] if page_no is not None else range(doc.page_count)
    for pi in pages:
        page = doc[pi]
        for f in find_plots(page):
            cal = calibrate(page, tuple(f["rect"]))
            entry = {"page": pi, "frame": list(f["rect"]), "calibration": cal, "curves": []}
            if cal["ok"]:
                entry["curves"] = curves_in(page, tuple(f["rect"]), cal)
            entry["caption"] = _caption_for(page, tuple(f["rect"]))
            figures.append(entry)
    return {"figures": figures, "pages": doc.page_count}


def _caption_for(page, frame: tuple) -> str:
    """'Fig. N - ...' below the frame. Vendors put the caption under the plot."""
    import fitz
    x0, y0, x1, y1 = frame
    for txt, bb in _text_items(page, fitz.Rect(x0 - 90, y1, x1 + 90, y1 + 74)):
        if re.match(r"^Fig\.?\s*\d", txt):
            return txt
    return ""
