"""
raster_curve.py — reading the PLOTTED curves off a datasheet whose figures are BITMAPS (B19).
=============================================================================================
`curve_extract.py` reads vector figures: the curve is a stroked path already in page coordinates,
so it is READ rather than traced, and the only real error is reading the axes. Its docstring says
a raster fallback "is still needed for scanned datasheets and is not built here". This is it.

The Toshiba TRS12E65H is the file that forced it. Its eight characteristic curves are 1638x1289
images with no vector paths at all, and — the part that decides the whole design — page 4 carries
FORTY WORDS of text, all of them figure captions. The tick labels are pixels. So the vector path's
calibration, a fit through tick-label positions whose residual is the evidence, has nothing to fit.

WHY THE DESIGNER SUPPLIES THE AXES. Three options existed: OCR the labels, infer them from
gridline counts, or ask. OCR would mean a tesseract system dependency for one datasheet, and it
fails in exactly the way C224 warned about — an axis misread that fits perfectly and is invisible
to the residual. Inference from gridline spacing cannot distinguish 0..2 from 0..20. So the axis
RANGES come from the designer, who can read them off the plot in seconds, and this module does
everything else. That is the "assisted pixel digitising" the bring-your-own-part plan specified:
the agent proposes points, the designer confirms them against the plot.

THIS DOES NOT RELAX THE VECTOR PATH'S GATES, which B19 explicitly forbids. It replaces a
text-fitted calibration with a designer-CONFIRMED one, and keeps the gate that actually has teeth:
the cross-check against a value the part's own table publishes. On the Toshiba file that check is
unusually strong because TWO different curves each have their own anchor — V_F = 1.2 V at 12 A
(25 degC) and 1.36 V at 12 A (150 degC) — so agreement is not something one lucky scale factor can
manufacture.

WITHOUT AXES IT REFUSES. `digitise_raster` returns `calibration.ok == False` and no curves when no
axes are given, so the existing behaviour — read nothing rather than read something wrong — is what
happens by default. Only an explicit, designer-supplied axis range turns the tracer on.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

# A pixel this dark is ink. The figures are clean black-on-white line art, not scans, so this is
# not a delicate threshold — the histogram is bimodal at the extremes.
_INK_LEVEL = 128
# Frame lines run across most of the plot; gridlines and curves do not.
_FRAME_SPAN = 0.60
# Erosion kernel. Gridlines here are 2-3 px and curve strokes 8-14 px, so a 7x7 erosion deletes
# the grid and keeps the curves. Measured on the Toshiba file: 135 components before, 21 after,
# and the curve band survives as one piece spanning 99.4% of the plot height.
_ERODE = 7
# A traced point may sit this far (px) from the previous row's point and still be the same curve.
_TRACK_JUMP = 14.0
# A track shorter than this fraction of the plot height is an annotation fragment, not a curve.
_MIN_TRACK_SPAN = 0.10


def _groups(idx: np.ndarray, gap: int = 3) -> list[tuple[int, int]]:
    """Consecutive runs in a sorted index array, as (first, last)."""
    out: list[list[int]] = []
    for i in idx.tolist():
        if out and i - out[-1][-1] <= gap:
            out[-1].append(i)
        else:
            out.append([i])
    return [(g[0], g[-1]) for g in out]


def find_frame(gray: np.ndarray) -> Optional[dict]:
    """The plot box, from the projection profiles of the ink.

    The frame is the outermost pair of lines that run across most of the image in each direction.
    Gridlines share that property, which is why the OUTERMOST group is taken rather than the
    darkest: an interior gridline can be darker than the frame where curves pile onto it.
    """
    dark = gray < _INK_LEVEL
    h, w = dark.shape
    rows = np.where(dark.sum(axis=1) > _FRAME_SPAN * w)[0]
    cols = np.where(dark.sum(axis=0) > _FRAME_SPAN * h)[0]
    if len(rows) < 2 or len(cols) < 2:
        return None
    rg, cg = _groups(rows), _groups(cols)
    if len(rg) < 2 or len(cg) < 2:
        return None
    top, bottom = rg[0], rg[-1]
    left, right = cg[0], cg[-1]
    # Centre of each frame stroke, so a thick frame does not bias the scale by half its width.
    y_top = (top[0] + top[1]) / 2.0
    y_bot = (bottom[0] + bottom[1]) / 2.0
    x_left = (left[0] + left[1]) / 2.0
    x_right = (right[0] + right[1]) / 2.0
    if x_right - x_left < 0.2 * w or y_bot - y_top < 0.2 * h:
        return None
    return {"x_left": x_left, "x_right": x_right, "y_top": y_top, "y_bottom": y_bot,
            "width_px": x_right - x_left, "height_px": y_bot - y_top}


def _band(gray: np.ndarray, frame: dict) -> np.ndarray:
    """Ink with the gridlines eroded away and everything outside the frame removed."""
    from scipy import ndimage
    dark = gray < _INK_LEVEL
    band = ndimage.binary_erosion(dark, structure=np.ones((_ERODE, _ERODE), bool))
    pad = _ERODE // 2 + 1
    out = np.zeros_like(band)
    y0, y1 = int(frame["y_top"]) + pad, int(frame["y_bottom"]) - pad
    x0, x1 = int(frame["x_left"]) + pad, int(frame["x_right"]) - pad
    out[y0:y1, x0:x1] = band[y0:y1, x0:x1]
    return out


def _row_runs(row: np.ndarray) -> list[float]:
    """Centres of the ink runs in one scan line."""
    out, start = [], None
    for i, v in enumerate(row.tolist()):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start + i - 1) / 2.0)
            start = None
    if start is not None:
        out.append((start + len(row) - 1) / 2.0)
    return out


def trace_curves(gray: np.ndarray, frame: dict, *,
                 max_curves: int = 8) -> list[list[tuple[float, float]]]:
    """Follow each curve down the plot, in pixel coordinates.

    TOP-DOWN, AND THAT IS NOT ARBITRARY. These families fan out at high current and collapse onto
    each other near the origin, where five curves become one blob 45 px wide. Seeding at the top
    starts from the row where they are MOST separated and follows each one into the crowd; seeding
    at the bottom would start inside the blob with nothing to separate. It also matches what the
    engine needs, since conduction loss is dominated by the high-current end.

    Curves that cross are followed by nearest-neighbour continuity. Where two genuinely merge, one
    track takes the shared run and the other ends — a track that stops is reported by its span, not
    silently padded, because an invented point in the middle of a merge is exactly the "reads
    something wrong" this whole path exists to avoid.
    """
    band = _band(gray, frame)
    y_start = int(frame["y_top"]) + _ERODE
    y_end = int(frame["y_bottom"]) - _ERODE
    tracks: list[list[tuple[float, float]]] = []
    seeded = False
    for y in range(y_start, y_end):
        centres = _row_runs(band[y])
        if not seeded:
            # Seed on the first row that resolves several curves at once.
            if len(centres) >= 2:
                tracks = [[(float(y), c)] for c in centres[:max_curves]]
                seeded = True
            continue
        taken: set[int] = set()
        for t in tracks:
            last_x = t[-1][1]
            best, best_d = None, 1e9
            for j, c in enumerate(centres):
                if j in taken:
                    continue
                d = abs(c - last_x)
                if d < best_d:
                    best_d, best = d, j
            if best is not None and best_d <= _TRACK_JUMP:
                t.append((float(y), centres[best]))
                taken.add(best)
    span = frame["height_px"]
    return [t for t in tracks if len(t) >= _MIN_TRACK_SPAN * span]


def _to_value(px: float, lo_px: float, hi_px: float, lo: float, hi: float, log: bool) -> float:
    f = (px - lo_px) / (hi_px - lo_px)
    if log:
        return float(10.0 ** (np.log10(lo) + f * (np.log10(hi) - np.log10(lo))))
    return float(lo + f * (hi - lo))


def curve_values(track: list[tuple[float, float]], frame: dict, axes: dict) -> list[list[float]]:
    """One traced curve in DATA coordinates, using the designer's axis ranges."""
    ax, ay = axes["x"], axes["y"]
    out = []
    for py, px in track:
        x = _to_value(px, frame["x_left"], frame["x_right"],
                      ax["min"], ax["max"], ax.get("log", False))
        y = _to_value(py, frame["y_bottom"], frame["y_top"],
                      ay["min"], ay["max"], ay.get("log", False))
        out.append([x, y])
    return out


def value_at(curve: list[list[float]], y_value: float) -> Optional[float]:
    """The x this curve reaches at a given y, or None if it never reaches it.

    NONE RATHER THAN AN EXTRAPOLATION. A track that stopped at a merge does not know where it went
    next, and answering anyway is how a digitiser reports a number nobody drew.
    """
    ys = [p[1] for p in curve]
    xs = [p[0] for p in curve]
    if not ys or not (min(ys) <= y_value <= max(ys)):
        return None
    order = np.argsort(ys)
    return float(np.interp(y_value, np.asarray(ys)[order], np.asarray(xs)[order]))


def cross_check(curve: list[list[float]], anchors: list[dict]) -> dict:
    """Compare the traced curve against values the part's own table publishes.

    THIS IS THE GATE, not a fit residual. B19 is explicit that the residual is not evidence: on a
    raster figure there is no tick-label fit to take a residual OF, and C224 showed that even where
    there is one, two different axis defects fit a straight line with residual exactly zero. Only a
    number the datasheet states independently can say the axes were read right.
    """
    rows = []
    for a in anchors:
        got = value_at(curve, a["y"])
        if got is None:
            rows.append({**a, "got": None, "error_pct": None, "agrees": False,
                         "note": "the curve does not reach this point"})
            continue
        err = abs(got - a["x"]) / abs(a["x"]) * 100.0 if a["x"] else None
        rows.append({**a, "got": round(got, 4),
                     "error_pct": None if err is None else round(err, 2),
                     "agrees": err is not None and err <= a.get("tol_pct", 5.0)})
    checked = [r for r in rows if r["got"] is not None]
    return {"checked": bool(checked),
            "agrees": bool(checked) and all(r["agrees"] for r in checked),
            "anchors": rows}


def figure_images(pdf_bytes: bytes, page_no: int) -> list[dict]:
    """Every bitmap on a page, as greyscale arrays, largest first.

    Page furniture (vendor logos, package drawings) arrives here too and is left in: it is the
    caller that knows which figure it wants, and silently dropping images by size would be a guess
    of exactly the kind this module exists to avoid.
    """
    import io as _io

    import fitz
    from PIL import Image

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_no]
    out = []
    for info in page.get_images(full=True):
        xref = info[0]
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.n > 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            gray = np.array(Image.open(_io.BytesIO(pix.tobytes("png"))).convert("L"))
        except Exception:
            continue
        rects = page.get_image_rects(xref)
        out.append({"xref": xref, "gray": gray,
                    "width": gray.shape[1], "height": gray.shape[0],
                    "rect": [round(float(v), 2) for v in
                             (tuple(rects[0]) if rects else (0, 0, 0, 0))]})
    out.sort(key=lambda d: d["width"] * d["height"], reverse=True)
    return out


def candidate_figures(pdf_bytes: bytes) -> list[dict]:
    """Every bitmap in the document that looks like a plot, for the designer to choose from.

    "Looks like a plot" is only: a frame was found, and it covers a decent share of the image. That
    is a deliberately weak filter. A package outline drawing also has long straight lines and may
    well pass — which is fine, because the designer is choosing from a rendered picture and the
    axis ranges have to be typed in anyway. A filter tuned to be clever here would hide the one
    figure somebody actually wanted, and the cost of an extra row in a list is nothing.

    Pages carrying vector figures are NOT excluded either: a datasheet can mix the two, and
    `curve_extract` already reports what it can read from a page. The two paths offer their own
    figures and the designer picks; nothing here decides on their behalf.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = []
    for pi in range(doc.page_count):
        for img in figure_images(pdf_bytes, pi):
            # Skip the tiny page furniture — logos and rule marks cannot be plots at this size.
            if img["width"] < 200 or img["height"] < 200:
                continue
            frame = find_frame(img["gray"])
            if frame is None:
                continue
            area = (frame["width_px"] * frame["height_px"]) / float(img["width"] * img["height"])
            if area < 0.25:
                continue
            out.append({"page": pi + 1, "page_index": pi, "xref": img["xref"],
                        "width": img["width"], "height": img["height"],
                        "rect": img["rect"], "frame_area_pct": round(100.0 * area, 1),
                        "caption": _caption_near(doc[pi], img["rect"])})
    return out


def _caption_near(page, rect: list) -> str:
    """The figure caption, from the page's text layer.

    The captions ARE text even on a page whose figures are bitmaps — on the Toshiba file they are
    the only text there is. So the designer sees "Fig. 9.1 IF - VF" beside the picture and knows
    which axes to type, which is what makes the axis entry a five-second job rather than a puzzle.
    """
    try:
        import fitz
        x0, y0, x1, y1 = rect
        # A caption sits just under its figure. 42 pt covers the one- and two-line forms.
        band = fitz.Rect(x0 - 6, y1, x1 + 6, y1 + 42)
        txt = " ".join(w[4] for w in page.get_text("words")
                       if fitz.Rect(w[:4]).intersects(band))
        return " ".join(txt.split())[:120]
    except Exception:
        return ""


def digitise_raster(pdf_bytes: bytes, page_no: int, xref: int,
                    axes: Optional[dict] = None,
                    anchors: Optional[list[dict]] = None) -> dict:
    """A PROPOSAL for one raster figure. Nothing here is trusted.

    `axes` is the designer's, and without it this refuses — the same shape as the vector path's
    `calibration.ok == False`, and the same outcome the file had before this module existed.
    """
    imgs = [i for i in figure_images(pdf_bytes, page_no) if i["xref"] == xref]
    if not imgs:
        return {"ok": False, "reason": f"no image with xref {xref} on page {page_no + 1}",
                "calibration": {"ok": False}, "curves": []}
    gray = imgs[0]["gray"]
    frame = find_frame(gray)
    if frame is None:
        return {"ok": False, "reason": "no plot frame found in the image",
                "calibration": {"ok": False}, "curves": []}
    if not axes:
        return {"ok": False,
                "reason": ("this figure is a bitmap and its tick labels are pixels, so the axis "
                           "ranges cannot be read from the page - supply them to digitise it"),
                "calibration": {"ok": False}, "frame": frame, "curves": []}

    tracks = trace_curves(gray, frame)
    curves = []
    for i, t in enumerate(tracks):
        vals = curve_values(t, frame, axes)
        entry = {"index": i, "n_points": len(vals), "points": vals,
                 "span_pct": round(100.0 * len(t) / frame["height_px"], 1)}
        if anchors:
            entry["cross_check"] = cross_check(vals, anchors)
        curves.append(entry)
    # The caption is text even here — on this datasheet it is the ONLY text on the page — so the
    # proposal can cite the figure it came off exactly as a vector proposal does.
    caption = ""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        caption = _caption_near(doc[page_no], imgs[0]["rect"])
    except Exception:
        caption = ""

    return {"ok": True, "source": "raster", "page": page_no + 1, "xref": xref,
            "frame": frame, "caption": caption,
            "calibration": {"ok": True, "source": "designer", "axes": axes},
            "curves": curves}
