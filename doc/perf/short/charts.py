# -*- coding: utf-8 -*-
"""One chart shape, used for every curve in the short proposal.

x is the branch: one point per commit, main at the left.  y is log, because the
corpora span three decades and the shape of each curve is what carries meaning.
A run that did not complete is a cross in a band below the axis, never a number:
a ratio against a ceiling or an abort would be fiction.
"""
import math
import shortlib as L

W, H = 900, 340
PADL, PADR, PADT, PADB = 66, 20, 30, 82
ZONE = 18                              # the "did not complete" band above the baseline

PUB, PRIV = "var(--s-pub)", "var(--s-priv)"
FAIL = "var(--fail)"
VIOLET, TEAL = "var(--lbl-286)", "var(--lbl-keep)"

# hue = public or private, dash = size inside the family
SERIES = [("public synthetic, 1 800", "synth300", PUB,  None),
          ("public synthetic, 600",   "synth100", PUB,  "5 3"),
          ("public synthetic, 71",    "tiny",     PUB,  "1 3"),
          ("private 30k monolith",    "mono",     PRIV, None),
          ("private refinement chain","ffi",      PRIV, "5 3")]

# short label per commit, and whether that commit's message cites tlaplus/tlapm#286
LABELS = {
    "p00": ("main",        False),
    "p01": ("clocks/nest", False),
    "p02": ("clocks/host", False),
    "p03": ("clocks/wire", False),
    "p04": ("reaper",      True),
    "p05": ("sigterm",     False),
    "p06": ("deque",       True),
    "p07": ("expansion",   True),
    "p08": ("stream",      False),
    "p09": ("levelcache",  False),
    "p10": ("prune/defs",  True),
    "p11": ("prune/facts", True),
    "p12": ("prefix",      False),
    "p13": ("normalize",   False),
    "p14": ("oracle",      False),
    "p15": ("enabled",     True),
    "p16": ("pool",        False),
    "p17": ("grammar",     False),
}
PR_END = set(L.ENDPOINTS)


def _decades(lo, hi):
    a, b = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
    ticks = []
    for e in range(a, b + 1):
        for m in (1, 2, 5):
            v = m * 10 ** e
            if lo / 1.6 <= v <= hi * 1.6:
                ticks.append(v)
    return 10.0 ** a, 10.0 ** b, ticks


def _tick(v):
    if v >= 1000 and v % 1000 == 0:
        return "%gk" % (v / 1000.0)
    return "%g" % v


def chart(aria, values, unit, fmt_end, series=None, points=None, rule=None):
    """values: {corpus: {point: number | {"kind","at"} | sentinel | None}}

    rule: (value, label) drawn as a labelled horizontal reference line -- the cap a
    failing run hit, so a cross sitting on it reads as "this is where it stopped"."""
    series = series or SERIES
    points = points or L.POINTS
    n = len(points)
    xs = lambda i: PADL + i * (W - PADL - PADR) / float(n - 1)
    flat = [v for cp in values for v in values[cp].values()
            if isinstance(v, (int, float)) and not isinstance(v, bool)]
    # a positioned cross has to fit inside the axis too
    flat += [v["at"] for cp in values for v in values[cp].values()
             if isinstance(v, dict) and v.get("at")]
    if not flat:
        return ('<svg viewBox="0 0 %d 46" role="img" aria-label="%s, not yet measured">'
                '<text x="%d" y="27" font-family="IBM Plex Sans, sans-serif" font-size="12" '
                'fill="currentColor" opacity=".6">measurement pass still running'
                '</text></svg>' % (W, aria, PADL))
    lo, hi, ticks = _decades(min(flat), max(flat))
    top, bot = PADT, H - PADB - ZONE
    y = lambda v: bot - (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (bot - top)
    o = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, aria)]
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="currentColor" stroke-width="1" '
             'opacity=".35"/>' % (PADL, H - PADB, W - PADR, H - PADB))
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="currentColor" stroke-width="0.8" '
             'stroke-dasharray="2 3" opacity=".3"/>' % (PADL, bot, W - PADR, bot))
    for v in ticks:
        yy = y(v)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="currentColor" '
                 'stroke-width="0.6" opacity=".13"/>' % (PADL, yy, W - PADR, yy))
        o.append('<text x="%d" y="%.1f" text-anchor="end" font-family="IBM Plex Mono, monospace" '
                 'font-size="10" fill="currentColor" opacity=".65">%s</text>'
                 % (PADL - 8, yy + 3.5, _tick(v)))
    o.append('<text x="%d" y="%d" text-anchor="end" font-family="IBM Plex Mono, monospace" '
             'font-size="9.5" fill="currentColor" opacity=".55">%s</text>' % (PADL - 8, PADT - 10, unit))
    o.append('<text x="%d" y="%.1f" text-anchor="end" font-family="IBM Plex Mono, monospace" '
             'font-size="9" fill="currentColor" opacity=".55">none</text>' % (PADL - 8, bot + ZONE / 2 + 3))
    # a faint rule at each pull-request boundary, so the eye can group the commits
    for i, pt in enumerate(points):
        if pt in PR_END and pt != points[-1]:
            o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="currentColor" '
                     'stroke-width="0.6" opacity=".10"/>' % (xs(i) + xs(1) / 2 - PADL / 2, PADT - 4,
                                                             xs(i) + xs(1) / 2 - PADL / 2, H - PADB))
    if rule:
        rv, rl = rule
        if lo <= rv <= hi:
            ry = y(rv)
            o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" '
                     'stroke-width="1" stroke-dasharray="5 4" opacity=".55"/>'
                     % (PADL, ry, W - PADR, ry, FAIL))
            o.append('<text x="%d" y="%.1f" text-anchor="end" font-family="IBM Plex Mono, '
                     'monospace" font-size="9.5" fill="%s" opacity=".9">%s</text>'
                     % (W - PADR, ry - 4, FAIL, rl))
    for lab, cp, col, dash in series:
        vs = [values.get(cp, {}).get(p) for p in points]
        da = ' stroke-dasharray="%s"' % dash if dash else ""
        # Every point that exists gets a y: a measured value at its value, a failure
        # at the coordinate its failure mode gives it, and a failure with no such
        # coordinate in the band.  The curve is then continuous, and the segments
        # that touch a failure are drawn faint so continuity is not read as
        # measured continuity.
        pts = []
        for i, v in enumerate(vs):
            if v is None:
                pts.append(None)
            elif isinstance(v, dict):
                at = v.get("at")
                pts.append((y(at) if at else bot + ZONE / 2, False))
            elif v in L.FAILED:
                pts.append((bot + ZONE / 2, False))
            else:
                pts.append((y(v), True))
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if a is None or b is None:
                continue
            solid = a[1] and b[1]
            o.append('<polyline points="%.1f,%.1f %.1f,%.1f" fill="none" stroke="%s" '
                     'stroke-width="%s"%s opacity="%s"/>'
                     % (xs(i), a[0], xs(i + 1), b[0], col,
                        "2" if solid else "1.2",
                        da if solid else ' stroke-dasharray="2 3"',
                        "1" if solid else ".4"))
        for i, v in enumerate(vs):
            if v is None:
                continue
            if isinstance(v, dict) or v in L.FAILED:
                cy = pts[i][0]
                r = 4.0
                o.append('<g stroke="%s" stroke-width="2" stroke-linecap="round">'
                         '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
                         '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/></g>'
                         % (FAIL, xs(i) - r, cy - r, xs(i) + r, cy + r,
                            xs(i) - r, cy + r, xs(i) + r, cy - r))
            else:
                rr = 3.2 if points[i] in PR_END else 2.2
                o.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>'
                         % (xs(i), y(v), rr, col))
        done = [(i, v) for i, v in enumerate(vs)
                if not (v is None or isinstance(v, dict) or v in L.FAILED)]
        if done:
            i, v = done[-1]
            o.append('<text x="%.1f" y="%.1f" text-anchor="end" font-family="IBM Plex Mono, monospace" '
                     'font-size="10.5" font-weight="600" fill="%s">%s</text>'
                     % (xs(i) - 5, y(v) - 8, col, fmt_end(v)))
    for i, pt in enumerate(points):
        lab, from286 = LABELS[pt]
        col = VIOLET if from286 else (TEAL if pt != "p00" else "currentColor")
        op = "1" if pt in PR_END or from286 else ".6"
        wt = ' font-weight="600"' if pt in PR_END else ""
        o.append('<text x="%.1f" y="%d" text-anchor="end" font-family="IBM Plex Mono, monospace" '
                 'font-size="9.5" fill="%s" opacity="%s"%s transform="rotate(-45 %.1f %d)">%s</text>'
                 % (xs(i), H - PADB + 15, col, op, wt, xs(i), H - PADB + 15, lab))
    lx, ly, row = PADL, PADT - 14, 0
    o.append('<g font-family="IBM Plex Sans, sans-serif" font-size="11">')
    for lab, cp, col, dash in series:
        w = 30 + int(5.9 * len(lab))
        if lx + w > W - PADR and row == 0:
            row, lx, ly = 1, PADL, PADT + 2
        da = ' stroke-dasharray="%s"' % dash if dash else ""
        o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="2"%s/>'
                 % (lx, ly - 4, lx + 20, ly - 4, col, da))
        o.append('<text x="%d" y="%d" fill="currentColor" opacity=".8">%s</text>' % (lx + 25, ly, lab))
        lx += w
    o.append('</g></svg>')
    return "".join(o)
