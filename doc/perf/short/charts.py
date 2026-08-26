# -*- coding: utf-8 -*-
"""One chart shape, used for every curve in the short proposal.

x is the branch: one point per commit, main at the left.  y is log, because the
corpora span three decades and the shape of each curve is what carries meaning.
A run that did not complete is a mark in a band below the axis, never a number
(a cross for a result, a ring for an inconclusive protocol timeout):
a ratio against a ceiling or an abort would be fiction.
"""
import math
import shortlib as L

W, H = 900, 340
PADL, PADR, PADT, PADB = 66, 54, 30, 82   # PADR is the end-label gutter
ZONE = 18                              # the "did not complete" band above the baseline

PUB, PRIV = "var(--s-pub)", "var(--s-priv)"
FAIL = "var(--fail)"
BG = "var(--card)"   # the surface a hollow mark is punched out of
END_LABEL_GAP = 11.5   # px; below this two end labels collide
VIOLET, TEAL = "var(--lbl-286)", "var(--lbl-keep)"

# Hue says whether the corpus can be published; dash separates members inside
# each hue.  Dash is NOT rank: the three flat synthetics happen to run
# solid/medium/dotted from large to small, but the refinement stack -- added
# later, and larger than synth300 -- takes its own long dash rather than
# claiming solid and pushing every other public series onto a different one.
# A reader comparing two versions of this page must not find a series wearing
# somebody else's line.
#
# Two hues is the whole palette (validated: worst adjacent CVD delta-E 14.3),
# so a sixth corpus does not need a sixth colour, and a corpus with no
# measurements never reaches the legend -- _series_for filters this list by
# what actually has points.
def _obl(cp):
    """The obligation count, from the campaign rather than from this line.

    It was typed here, and when the control corpus turned out to have twenty
    obligations rather than seventy-one the legend went on saying seventy-one --
    the number was corrected in shortlib and this copy was missed.
    """
    return "{:,}".format(L.OBL[cp]).replace(",", "\u00a0")


SERIES = [("public synthetic, " + _obl("synth300"), "synth300", PUB,  None),
          ("public synthetic, " + _obl("synth100"), "synth100", PUB,  "5 3"),
          ("public synthetic, " + _obl("tiny"),     "tiny",     PUB,  "1 3"),
          # long-short, not another plain dash: rendered at this size "9 3" was
          # indistinguishable from synth100's "5 3", which makes the dash stop
          # being a secondary encoding and leaves two same-hue series told
          # apart only by where they happen to sit.
          ("public refinement stack", "idemo",    PUB,  "11 3 2 3"),
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
    """Axis bounds hugging the data rather than snapping to whole decades.

    Snapping wasted most of the plot on empty space: a series running from 93 ms
    to 73 s was drawn on an axis from 10 ms to 100 s.  The bounds now sit a
    quarter-decade outside the data, and the 1/2/5 ticks are whatever falls
    inside."""
    lo_ax, hi_ax = lo / 1.25, hi * 1.25
    ticks = []
    for e in range(int(math.floor(math.log10(lo_ax))),
                   int(math.ceil(math.log10(hi_ax))) + 1):
        for m in (1, 2, 5):
            v = m * 10.0 ** e
            if lo_ax <= v <= hi_ax:
                ticks.append(v)
    return lo_ax, hi_ax, ticks


def _tick(v):
    if v >= 1000 and v % 1000 == 0:
        return "%gk" % (v / 1000.0)
    return "%g" % v


def series_for(values):
    """Whichever of the standard series this data actually has points for.

    The one place that decides it.  The default legend of every chart comes
    from here, and so does any caller that needs the same list for a caption --
    a legend and its caption disagreeing is a real failure this document has
    already had."""
    return [t for t in SERIES
            if any(v is not None for v in (values.get(t[1]) or {}).values())]


def chart(aria, values, unit, fmt_end, series=None, points=None, rule=None,
          better=None):
    """values: {corpus: {point: number | {"kind","at"} | sentinel | None}}

    rule: (value, label) drawn as a labelled horizontal reference line -- the cap a
    failing run hit, so a cross sitting on it reads as "this is where it stopped".

    Passing no series means "whichever of the standard ones this data has": the
    default USED to be the whole list, so adding a sixth corpus to SERIES put a
    legend entry for it on every chart that had not been measured yet -- a line
    in the key pointing at nothing drawn.  Filtering here makes the legend a
    consequence of the data rather than of the constant."""
    series = series or series_for(values)
    ends = []            # end labels, placed after every series is drawn
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
    # a band under the axis is only needed when some failure has no coordinate on
    # this metric; when every point can be placed, the band is dead space
    needs_band = any(
        (isinstance(v, dict) and not v.get("at")) or (not isinstance(v, dict) and v in L.FAILED)
        for cp in values for v in values[cp].values() if v is not None)
    zone = ZONE if needs_band else 0
    # Which SIDE the band sits on is a property of the metric, not of the layout.
    # On a lower-is-better axis the bottom of the chart is the best possible
    # place to be, so a run that never finished, parked down there, reads as the
    # best result on the chart.  It is the worst one.  The band goes above the
    # plot for those metrics and below it for higher-is-better.
    band_top = (better == "lower")
    # The legend is laid out before the plot, because how many rows it needs
    # decides where the plot can start.  Row 1 used to be drawn at PADT + 2 --
    # two pixels INSIDE the plot area -- and a third row was not handled at
    # all: the loop only wrapped once, so a sixth series would have run off the
    # right edge without saying so.  Rendering the page is the only way that
    # shows up, which is why it survived five corpora.
    LEG_ROW = 16
    rows, lx = [[]], PADL
    for t in series:
        w = 30 + int(5.9 * len(t[0]))
        if lx + w > W - PADR and rows[-1]:
            rows.append([]); lx = PADL
        rows[-1].append((lx, t)); lx += w
    leg_base = PADT + LEG_ROW * (len(rows) - 1)   # where the legend ends
    top = leg_base + (zone if band_top else 0)    # where the plot starts
    bot = H - PADB - (0 if band_top else zone)
    band_y = (top - zone / 2.0) if band_top else (bot + zone / 2.0)
    band_rule = top if band_top else bot
    y = lambda v: bot - (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (bot - top)
    o = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, aria)]
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="currentColor" stroke-width="1" '
             'opacity=".35"/>' % (PADL, H - PADB, W - PADR, H - PADB))
    if needs_band:
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="currentColor" '
                 'stroke-width="0.8" stroke-dasharray="2 3" opacity=".3"/>'
                 % (PADL, band_rule, W - PADR, band_rule))
    for v in ticks:
        yy = y(v)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="currentColor" '
                 'stroke-width="0.6" opacity=".13"/>' % (PADL, yy, W - PADR, yy))
        o.append('<text x="%d" y="%.1f" text-anchor="end" font-family="IBM Plex Mono, monospace" '
                 'font-size="10" fill="currentColor" opacity=".65">%s</text>'
                 % (PADL - 8, yy + 3.5, _tick(v)))
    o.append('<text x="%d" y="%d" text-anchor="end" font-family="IBM Plex Mono, monospace" '
             'font-size="9.5" fill="currentColor" opacity=".55">%s</text>' % (PADL - 8, top + (14 if band_top else -10), unit))
    if needs_band:
        o.append('<text x="%d" y="%.1f" text-anchor="end" font-family="IBM Plex Mono, '
                 'monospace" font-size="9" fill="currentColor" opacity=".55">none</text>'
                 % (PADL - 8, band_y + 3))
    # a faint rule at each pull-request boundary, so the eye can group the commits
    for i, pt in enumerate(points):
        if pt in PR_END and pt != points[-1]:
            o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="currentColor" '
                     'stroke-width="0.6" opacity=".10"/>' % (xs(i) + xs(1) / 2 - PADL / 2, top - 4,
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
                pts.append((y(at) if at else band_y, False))
            elif v in L.FAILED:
                pts.append((band_y, False))
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
            if isinstance(v, dict) and v.get("carried"):
                # Not a measurement: the same value as its neighbour, on a point the
                # campaign could not re-run.  Hollow, in the series colour, with the
                # segments either side already drawn faint.
                o.append('<circle cx="%.1f" cy="%.1f" r="3.2" fill="%s" stroke="%s" '
                         'stroke-width="1.6"/>' % (xs(i), pts[i][0], BG, col))
                continue
            if isinstance(v, dict) or v in L.FAILED:
                cy = pts[i][0]
                r = 4.0
                if isinstance(v, dict) and v.get("pending"):
                    # A ring is a run given a full hour and still unfinished: the
                    # clock is ours, so what is established is "not practical",
                    # not a number.  A cross is the cap refusing an allocation --
                    # settled, and nothing more to learn by waiting.  Both sit in
                    # the "none" row because neither has a coordinate on the axis;
                    # the shape is what separates them.
                    o.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" '
                             'stroke="%s" stroke-width="2"/>'
                             % (xs(i), cy, r - 0.4, FAIL))
                else:
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
            ends.append([y(v) + 3.5, col, fmt_end(v)])
    # End labels live in a gutter to the right of the plot, and are placed only now.
    # Inside the plot two series ending close together put their labels on top of
    # each other -- the 1 800-obligation corpus and the small one end 12 px apart --
    # and nudging them apart there only moved one of them onto a curve.  A gutter
    # fixes the class of problem rather than this instance: labels can be spread
    # vertically without ever landing on data.
    ends.sort()
    for k in range(1, len(ends)):
        if ends[k][0] - ends[k - 1][0] < END_LABEL_GAP:
            ends[k][0] = ends[k - 1][0] + END_LABEL_GAP
    for ey, ecol, etxt in ends:
        o.append('<text x="%.1f" y="%.1f" font-family="IBM Plex Mono, monospace" '
                 'font-size="10.5" font-weight="600" fill="%s">%s</text>'
                 % (W - PADR + 6, ey, ecol, etxt))
    for i, pt in enumerate(points):
        lab, from286 = LABELS[pt]
        col = VIOLET if from286 else (TEAL if pt != "p00" else "currentColor")
        op = "1" if pt in PR_END or from286 else ".6"
        wt = ' font-weight="600"' if pt in PR_END else ""
        o.append('<text x="%.1f" y="%d" text-anchor="end" font-family="IBM Plex Mono, monospace" '
                 'font-size="9.5" fill="%s" opacity="%s"%s transform="rotate(-45 %.1f %d)">%s</text>'
                 % (xs(i), H - PADB + 15, col, op, wt, xs(i), H - PADB + 15, lab))
    o.append('<g font-family="IBM Plex Sans, sans-serif" font-size="11">')
    for r, entries in enumerate(rows):
        ly = leg_base - 14 - LEG_ROW * (len(rows) - 1 - r)
        for lx, (lab, cp, col, dash) in entries:
            da = ' stroke-dasharray="%s"' % dash if dash else ""
            o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" '
                     'stroke-width="2"%s/>'
                     % (lx, ly - 4, lx + 20, ly - 4, col, da))
            o.append('<text x="%d" y="%d" fill="currentColor" opacity=".8">%s</text>'
                     % (lx + 25, ly, lab))
    o.append('</g></svg>')
    return "".join(o)


def rate_by_position(series, aria):
    """Preparation rate against how far into the file it has got.

    series: [(label, colour, dash, [(n, seconds), ...], refused)], one per commit.
    `refused` marks a run the cap stopped: its curve ends in the same red cross the
    other charts use for a refusal, rather than in a dot that would read as an end.

    x is obligations prepared, y is the rate over a sliding window -- not the
    running average, which would hide the shape by carrying the cheap head of the
    file all the way to the right.  A curve that ends before the axis does is a
    run the cap refused there.

    This is the chart that says whether an aborted cell's rate can be read next
    to a completing one's: if the rate falls as position rises, an average over
    the first quarter of a file is not the same quantity as an average over all
    of it.
    """
    # the same frame and the same width as every other chart on the page.  Two
    # departures, both because this chart carries different furniture: a wider right
    # gutter, since it names twelve curves at their ends and PADR is sized for a tick
    # label; and a shallower bottom, since PADB holds the others' rotated commit
    # names and a legend, and here the axis is two lines of plain text.
    W2, H2, PL, PR2, PT2, PB2 = W, H, PADL, 104, PADT, 44
    pts = [t for t in series if len(t[3]) > 40]
    if not pts:
        return ""
    xs_max = max(t[3][-1][0] for t in pts)

    def windows(rows):
        """(position, rate) over windows of a fortieth of the run, at least 25 wide"""
        w = max(25, len(rows) // 40)
        out = []
        for i in range(w, len(rows), w):
            dn = rows[i][0] - rows[i - w][0]
            dt = rows[i][1] - rows[i - w][1]
            if dt > 0 and dn > 0:
                out.append((rows[i][0], dn / dt))
        return out

    curves = [(t[0], t[1], t[2], windows(t[3]), t[4]) for t in pts]
    curves = [c for c in curves if c[3]]
    if not curves:
        return ""
    ys = [r for _, _, _, w, _ in curves for _, r in w]
    # Linear, not logarithmic.  What this chart exists to show is a rate collapsing
    # as position rises; a log axis turns a factor of eight into a gentle slope and
    # hides the very thing being claimed.  The other charts need log because their
    # corpora span three decades -- here every curve is one corpus.
    top = max(ys) * 1.08
    step = 10 ** math.floor(math.log10(top / 4.0))
    for m in (1, 2, 2.5, 5, 10):
        if top / (step * m) <= 6:
            step *= m
            break
    ticks = [t for t in (step * i for i in range(0, 12)) if t <= top]
    x = lambda n: PL + n / float(xs_max) * (W2 - PL - PR2)
    y = lambda v: (H2 - PB2) - (v / top) * (H2 - PB2 - PT2)
    o = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W2, H2, aria)]
    for t in ticks:
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="currentColor" '
                 'stroke-width="1" opacity=".08"/>' % (PL, y(t), W2 - PR2, y(t)))
        o.append('<text x="%d" y="%.1f" text-anchor="end" font-family="IBM Plex Sans, '
                 'sans-serif" font-size="10" fill="currentColor" opacity=".55">%s</text>'
                 % (PL - 6, y(t) + 3, _tick(t)))
    for n in (0, xs_max // 2, xs_max):
        o.append('<text x="%.1f" y="%d" text-anchor="middle" font-family="IBM Plex Sans, '
                 'sans-serif" font-size="10" fill="currentColor" opacity=".55">%s</text>'
                 % (x(n), H2 - PB2 + 15, "{:,}".format(n).replace(",", "\u2009")))
    o.append('<text x="%d" y="%d" text-anchor="middle" font-family="IBM Plex Sans, '
             'sans-serif" font-size="10" fill="currentColor" opacity=".55">obligations '
             'prepared</text>' % ((PL + W2 - PR2) // 2, H2 - PB2 + 32))
    ends = []
    for lab, col, dash, w, refused in curves:
        d = " ".join("%s%.1f %.1f" % ("M" if i == 0 else "L", x(n), y(r))
                     for i, (n, r) in enumerate(w))
        o.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.6" opacity=".85"%s/>'
                 % (d, col, ' stroke-dasharray="%s"' % dash if dash else ""))
        n, r = w[-1]
        if refused:
            g = 3.6
            o.append('<g stroke="%s" stroke-width="2" stroke-linecap="round">'
                     '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
                     '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/></g>'
                     % (FAIL, x(n) - g, y(r) - g, x(n) + g, y(r) + g,
                        x(n) - g, y(r) + g, x(n) + g, y(r) - g))
        else:
            o.append('<circle cx="%.1f" cy="%.1f" r="2.6" fill="%s"/>' % (x(n), y(r), col))
        ends.append([lab, col, x(n), y(r)])
    # A dozen curves end within a few pixels of each other, so the names have to be
    # laid out rather than dropped where the curve stops: nudge each one down until
    # it clears the one above, and hang it on the left of the endpoint when the
    # gutter cannot hold it.  A leader line keeps a nudged name attached to its curve.
    ends.sort(key=lambda e: e[3])
    prev = None
    for e in ends:
        ty = e[3] + 3.5
        if prev is not None and ty - prev < 11.5:
            ty = prev + 11.5
        prev = ty
        e.append(ty)
    for lab, col, ex, ey, ty in ends:
        wid = 6.0 * len(lab)
        if ex + 8 + wid > W2 - 4:
            tx, anchor, lx = ex - 8, ' text-anchor="end"', ex - 6
        else:
            tx, anchor, lx = ex + 8, "", ex + 6
        if abs(ty - 3.5 - ey) > 2:
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                     'stroke-width="1" opacity=".35"/>' % (ex, ey, lx, ty - 3.5, col))
        o.append('<text x="%.1f" y="%.1f"%s font-family="IBM Plex Sans, sans-serif" '
                 'font-size="10.5" fill="%s">%s</text>' % (tx, ty, anchor, col, lab))
    o.append("</svg>")
    return "".join(o)
