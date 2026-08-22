# -*- coding: utf-8 -*-
"""Section 05: throughput, latency floor and peak memory — one chart per metric,
all four corpora on the same log axis, one point per pull request."""
import os, math, sweeplib

S = os.environ.get("SWEEP_DIR", os.path.dirname(os.path.abspath(__file__)))
rows, BOOT = sweeplib.load()
SPREAD = rows.get("_spread", {})
DNC   = "DNC"      # measured, run did not complete (generic)
CEIL  = "CEIL"     # stopped at the timeout ceiling
ABORT = "ABORT"    # aborted against the address-space cap
FAILED = (DNC, CEIL, ABORT)
#  None = not measured at all

OBL = {"synth300": 1800, "synth100": 600, "ffi": 9967, "mono": 29965}
PRS = [("main","c00","the base of the branch"),
       ("fixes","c05","the five bugfixes"),
       ("deque","c06","deque lookups"),
       ("expand","c07","single-pass expansion"),
       ("prune","c09","the two context prunes"),
       ("cache","c12","prefix-resume caches"),
       ("stream","c13","streamed task list"),
       ("enabled","c14","linear ENABLED scan"),
       ("levels","c15","levels without slicing"),
       ("printer","c16","single-pass result printer"),
       ("parser","c17","memoized grammar"),
       ("props","c18","property lookups"),
       ("lsp","c19","editor obligation pool"),
       ("ctx","c20","Ctx index"),
       ("smtlib","c21","SMT escaping regexes"),
       ("app_ix","c22","allocation-free spine walk"),
       ("flatten","c23","skip identity rebuilds"),
       ("comments","c24","obligation comment only when kept"),
       ("levcache","c25","level-cache lifetime"),
       ("const","c26","constant-time constness index")]
LABELS = [p[0] for p in PRS]
PTS = [p[1] for p in PRS]

# hue = corpus family, dash = size inside the family
PUB, PRIV = "var(--s-pub)", "var(--s-priv)"
SERIES = [("public synthetic, 1 800", "synth300", PUB,  None),
          ("public synthetic, 600",   "synth100", PUB,  "5 3"),
          ("private 30k monolith",    "mono",     PRIV, None),
          ("private refinement chain","ffi",      PRIV, "5 3")]

W, H = 900, 320
L, R, T, B = 66, 20, 26, 66
ZONE = 18                        # the "no value" band just above the baseline
def xs(i): return L + i*(W-L-R)/(len(PRS)-1)

def get(pt, cp, f):
    r = rows.get((pt, cp))
    if not r or f not in r: return None
    rc = r["m0_rc" if f == "m0_ms" else "m1_rc"]
    if rc == 0: return r[f]
    return CEIL if rc == 124 else (ABORT if rc in (134, 137) else DNC)

def thr(pt, cp):
    v = get(pt, cp, "m1_ms")
    return v if (v is None or v in FAILED) else OBL[cp]*1000.0/v

def peak(pt, cp):
    r = rows.get((pt, cp))
    if not r or "rss_kb" not in r: return None
    if r["m1_rc"] == 0: return r["rss_kb"]/1024.0
    return CEIL if r["m1_rc"] == 124 else (ABORT if r["m1_rc"] in (134, 137) else DNC)

def decades(lo, hi):
    a = math.floor(math.log10(lo)); b = math.ceil(math.log10(hi))
    ticks = []
    for e in range(a, b+1):
        for m in (1, 2, 5):
            v = m*10**e
            if lo/1.6 <= v <= hi*1.6: ticks.append(v)
    return 10**a, 10**b, ticks

def tick_txt(v):
    if v >= 1000 and v % 1000 == 0: return "%gk" % (v/1000.0)
    return "%g" % v

def chart(sub, aria, values, unit, fmt_end):
    """values: {corpus: [per-point value | DNC | None]}"""
    flat = [v for cp in values for v in values[cp] if isinstance(v, float) or isinstance(v, int)]
    if not flat:
        return ('<svg viewBox="0 0 %d 44" role="img" aria-label="%s, not yet measured">'
                '<text x="%d" y="26" font-family="IBM Plex Sans, sans-serif" font-size="12" '
                'fill="currentColor" opacity=".6">%s &mdash; measurement pass still running</text></svg>'
                % (W, aria, L, sub))
    lo, hi, ticks = decades(min(flat), max(flat))
    top, bot = T, H-B-ZONE
    def y(v): return bot - (math.log10(v)-math.log10(lo))/(math.log10(hi)-math.log10(lo))*(bot-top)
    o = []
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="currentColor" stroke-width="1" opacity=".35"/>'
             % (L, H-B, W-R, H-B))
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="currentColor" stroke-width="0.8" '
             'stroke-dasharray="2 3" opacity=".3"/>' % (L, bot, W-R, bot))
    for v in ticks:
        yy = y(v)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="currentColor" stroke-width="0.6" '
                 'opacity=".13"/>' % (L, yy, W-R, yy))
        o.append('<text x="%d" y="%.1f" text-anchor="end" font-family="IBM Plex Mono, monospace" '
                 'font-size="10" fill="currentColor" opacity=".65">%s</text>' % (L-8, yy+3.5, tick_txt(v)))
    o.append('<text x="%d" y="%d" text-anchor="end" font-family="IBM Plex Mono, monospace" '
             'font-size="9.5" fill="currentColor" opacity=".55">%s</text>' % (L-8, T-9, unit))
    o.append('<text x="%d" y="%.1f" text-anchor="end" font-family="IBM Plex Mono, monospace" '
             'font-size="9" fill="currentColor" opacity=".55">none</text>' % (L-8, bot+ZONE/2+3))
    for lab, cp, col, dash in SERIES:
        vs = values[cp]
        seg, segs = [], []
        for i, v in enumerate(vs):
            if v is None or v in FAILED:
                if seg: segs.append(seg); seg = []
            else: seg.append((i, v))
        if seg: segs.append(seg)
        da = ' stroke-dasharray="%s"' % dash if dash else ""
        for sg in segs:
            if len(sg) > 1:
                o.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2"%s/>'
                         % (" ".join("%.1f,%.1f" % (xs(i), y(v)) for i, v in sg), col, da))
        for i, v in enumerate(vs):
            if v is None: continue
            if v in FAILED:
                cy = bot + ZONE/2
                o.append('<g stroke="%s" stroke-width="1.5" opacity=".9"><line x1="%.1f" y1="%.1f" '
                         'x2="%.1f" y2="%.1f"/><line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/></g>'
                         % (col, xs(i)-3.4, cy-3.4, xs(i)+3.4, cy+3.4,
                            xs(i)-3.4, cy+3.4, xs(i)+3.4, cy-3.4))
            else:
                o.append('<circle cx="%.1f" cy="%.1f" r="2.6" fill="%s"/>' % (xs(i), y(v), col))
        last = [(i, v) for i, v in enumerate(vs) if not (v is None or v in FAILED)]
        if last:
            i, v = last[-1]
            o.append('<text x="%.1f" y="%.1f" text-anchor="end" font-family="IBM Plex Mono, monospace" '
                     'font-size="10.5" font-weight="600" fill="%s">%s</text>'
                     % (xs(i)-5, y(v)-7, col, fmt_end(v)))
    for i, lab in enumerate(LABELS):
        o.append('<text x="%.1f" y="%d" text-anchor="end" font-family="IBM Plex Mono, monospace" '
                 'font-size="9.5" fill="currentColor" opacity=".7" transform="rotate(-45 %.1f %d)">%s</text>'
                 % (xs(i), H-B+15, xs(i), H-B+15, lab))
    lx = L
    o.append('<g font-family="IBM Plex Sans, sans-serif" font-size="11">')
    for lab, cp, col, dash in SERIES:
        da = ' stroke-dasharray="4 2.5"' if dash else ""
        o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="2"%s/>'
                 % (lx, T-13, lx+14, T-13, col, da))
        o.append('<text x="%d" y="%d" fill="currentColor">%s</text>' % (lx+19, T-9.5, lab))
        lx += 30 + int(5.9*len(lab))
    o.append('</g>')
    o.append('<text x="%d" y="%d" text-anchor="end" font-family="IBM Plex Sans, sans-serif" '
             'font-size="10.5" fill="currentColor" opacity=".7">&times; = did not complete</text>'
             % (W-R, T-9.5))
    return '<svg viewBox="0 0 %d %d" role="img" aria-label="%s">\n      %s\n    </svg>' % (
        W, H, aria, "\n      ".join(o))

def fmt_ms(v):
    if v is None: return "&mdash;"
    if v is CEIL: return "&gt; 900 s"
    if v is ABORT: return "aborts on memory"
    if v is DNC: return "does not complete"
    if v >= 10000: return "%.1f s" % (v/1000.0)
    if v >= 1000: return "%.2f s" % (v/1000.0)
    return "%d ms" % v

def fmt_mb(v):
    if v is None: return "&mdash;"
    if v is CEIL: return "&mdash;"
    if v in (ABORT, DNC): return "at the cap"
    return "%.2f GB" % (v/1024.0) if v >= 1024 else "%d MB" % round(v)

o = []
A = o.append
A('<section>')
A('  <div class="sec-head"><span class="n">05</span><h2>Throughput, latency and memory, one point per pull request</h2></div>')
A("""  <p>The x axis is the branch, in order: <code>main</code>, then the five bugfixes as one point,
  then one point per pull request. All four corpora share one axis in each chart, on a log scale,
  because that is the only way the two ends of the range are legible together &mdash; and the range
  <em>is</em> the subject. Colour is the corpus family, public or private; the dashed line is the
  smaller of the two inside each family.</p>""")
A("""  <p>A cross in the strip below the axis means the run <strong>did not complete</strong>. The table
  says which of the two ways: <code>&gt; 900 s</code> is a run stopped at the fifteen-minute ceiling,
  <code>aborts on memory</code> is one that hit the 12&nbsp;GB address-space cap it was run under
  &mdash; and the distinction matters, because a change that speeds preparation up reaches the memory
  wall <em>sooner</em>, turning a timeout into an abort without being a regression. That is why the first chart is throughput and not a speedup: on the two private
  specifications there is no <code>main</code> value to form a ratio against. Every number comes from
  one campaign on one boot of one container; absolute values are not comparable across restarts.</p>""")
A("""  <p><code>main</code> was measured at both ends of the campaign. On the private specifications its
  latency floor repeats to within 0.4&nbsp;% and 2.5&nbsp;%; on the public synthetic it does not,
  because the first run of a campaign meets a cold page cache, so the <code>main</code> point there is
  the mean of the two runs and &sect;4 gives the spread. Every other point is a single run taken
  immediately after its own build.</p>""")

A('  <figure style="margin-top:20px">')
A('    <h4 style="margin:0 0 2px">Preparation throughput</h4>')
A('    <p style="font-size:13.5px;color:var(--ink-2);margin:0 0 12px">Obligations prepared per second '
  '&mdash; <code>tlapm --noproving --nofp</code>, the whole per-obligation pipeline with no prover. '
  'Higher is better. Obligations are not the same size in every corpus, so a curve&rsquo;s height '
  'relative to another&rsquo;s carries obligation cost as much as speed; what each curve says on its '
  'own is its shape.</p>')
A('    ' + chart("Preparation throughput",
    "Preparation throughput in obligations per second, one point per pull request, four corpora on a log axis; the two private specifications do not complete on main.",
    {cp: [thr(p, cp) for p in PTS] for _, cp, _, _ in SERIES}, "obl/s",
    lambda v: "%g" % round(v)))
A('    <figcaption>The three steps that carry throughput are the deque lookups, the single-pass '
  'expansion and the prune of hidden facts. On the two private specifications the branch is what makes '
  'the run exist at all: <code>main</code> has no throughput there, not a low one.</figcaption>')
A('  </figure>')

A('  <figure style="margin-top:20px">')
A('    <h4 style="margin:0 0 2px">Latency floor</h4>')
A('    <p style="font-size:13.5px;color:var(--ink-2);margin:0 0 12px">'
  '<code>tlapm -N --nofp</code>: parse, elaborate, generate obligations, stop. What every editor '
  'interaction pays before anything else happens, and the fixed per-worker cost of any parallel '
  'scheme. Lower is better.</p>')
A('    ' + chart("Latency floor",
    "Parse, elaborate and generate, in milliseconds, one point per pull request, four corpora on a log axis; three commits carry the whole drop.",
    {cp: [get(p, cp, "m0_ms") for p in PTS] for _, cp, _, _ in SERIES}, "ms",
    lambda v: "%.1f s" % (v/1000.0) if v >= 1000 else "%g ms" % round(v)))
A('    <figcaption>Three commits carry all of it &mdash; the deque lookups, the linear ENABLED scan '
  'and the memoized grammar. The prunes and the caches are flat here by construction: none of them '
  'runs before an obligation exists. This is the one metric where every corpus completes on '
  '<code>main</code>, so it is also the one that can be read as a ratio.</figcaption>')
A('  </figure>')

A('  <figure style="margin-top:20px">')
A('    <h4 style="margin:0 0 2px">Peak resident memory</h4>')
A('    <p style="font-size:13.5px;color:var(--ink-2);margin:0 0 12px">Maximum resident set of the '
  'preparation run above. Where a run aborted, the memory <em>is</em> the failure, so the last value '
  'it reached is the cap rather than a measurement of the work.</p>')
A('    ' + chart("Peak resident memory",
    "Peak resident memory in megabytes, one point per pull request, four corpora on a log axis; the drop comes from the prune of hidden facts and the level-cache lifetime fix.",
    {cp: [peak(p, cp) for p in PTS] for _, cp, _, _ in SERIES}, "MB",
    lambda v: "%.2f GB" % (v/1024.0) if v >= 1024 else "%g MB" % round(v)))
A('    <figcaption>Two changes produce the drop: the prune of unreferenced hidden facts, then the '
  'level-cache lifetime fix. Between them they are what turns a run that dies on memory into one that '
  'finishes.</figcaption>')
A('  </figure>')

A('  <div class="scroller" style="margin-top:22px">')
A('    <table>')
A('      <thead><tr><th>point</th><th>change</th>'
  '<th class="num">gen, 1 800</th><th class="num">prep, 1 800</th><th class="num">peak, 1 800</th>'
  '<th class="num">prep, chain</th><th class="num">prep, 30k</th><th class="num">peak, 30k</th></tr></thead>')
A('      <tbody>')
for i, (lab, pt, name) in enumerate(PRS):
    tag = "main" if i == 0 else ("bugfixes" if i == 1 else "#%d" % (i-1))
    A('        <tr><td class="num">%s</td><td>%s</td><td class="num">%s</td><td class="num">%s</td>'
      '<td class="num">%s</td><td class="num">%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
      % (tag, name, fmt_ms(get(pt,"synth300","m0_ms")), fmt_ms(get(pt,"synth300","m1_ms")),
         fmt_mb(peak(pt,"synth300")), fmt_ms(get(pt,"ffi","m1_ms")),
         fmt_ms(get(pt,"mono","m1_ms")), fmt_mb(peak(pt,"mono"))))
A('      </tbody>')
A('    </table>')
A('  </div>')

def num(pt, cp, f):
    v = get(pt, cp, f)
    return v if isinstance(v, int) else None
m0a, m0b = num("c00","synth300","m0_ms"), num("c26","synth300","m0_ms")
m1a, m1b = num("c00","synth300","m1_ms"), num("c26","synth300","m1_ms")
pa, pb = peak("c00","synth300"), peak("c26","synth300")
NOISE = 0.03
below = sum(1 for i in range(1, len(PTS))
            if num(PTS[i-1],"synth300","m1_ms") and num(PTS[i],"synth300","m1_ms")
            and abs(num(PTS[i-1],"synth300","m1_ms")/float(num(PTS[i],"synth300","m1_ms")) - 1) < NOISE)
A("""  <p style="margin-top:14px"><strong>On the public medium case: &times;%.1f on the latency floor,
  &times;%.1f on throughput, &times;%.1f on peak memory.</strong> %d of the nineteen pull requests move
  throughput on that corpus by less than the noise floor on their own; they are in the set because of
  what they do on the two large specifications and because of the mechanism, both of which &sect;6
  states per commit.</p>""" % (m0a/float(m0b), m1a/float(m1b), pa/float(pb), below))
A('</section>')

sec = "\n".join(o) + "\n"
path = os.environ.get("PROPOSAL_HTML", os.path.join(S, "PROPOSAL.html"))
src = open(path).read()
start = src.index('<section>\n  <div class="sec-head"><span class="n">05</span>')
end = src.index('<section>\n  <div class="sec-head"><span class="n">06</span>')
open(path, "w").write(src[:start] + sec + "\n" + src[end:])
print("section 05: one chart per metric, four corpora, log axis")
