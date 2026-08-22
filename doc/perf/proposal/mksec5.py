# -*- coding: utf-8 -*-
"""Section 05: throughput, latency floor and peak memory — one chart per metric,
all four corpora on the same log axis, one point per pull request."""
import os, math, sweeplib

S = os.environ.get("SWEEP_DIR", os.path.dirname(os.path.abspath(__file__)))
rows, BOOT = sweeplib.load()
ITER, ITER_SPREAD = sweeplib.load_iteration_latency()
ICHAIN = sweeplib.load_iteration_latency_chain()
KEYS = sweeplib.load_keystroke()
SPREAD = rows.get("_spread", {})
DNC   = "DNC"      # measured, run did not complete (generic)
CEIL  = "CEIL"     # stopped at the timeout ceiling
ABORT = "ABORT"    # aborted against the address-space cap
FAILED = (DNC, CEIL, ABORT)
#  None = not measured at all

OBL = {"synth300": 1800, "synth100": 600, "tiny": 71, "ffi": 9967, "mono": 29965}
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

# Which pull requests carry content from tlaplus/tlapm#286 (the commit messages name the
# reference implementation), and which the short proposal keeps.  Both are properties of
# the branch, so they are listed once here and drive the label colours.
FROM_286 = {"c05", "c06", "c07", "c09", "c14", "c15", "c20", "c21", "c22", "c23", "c24"}
SELECTED = {"c05", "c06", "c07", "c09", "c12", "c13", "c14", "c19", "c25"}
VIOLET, GREEN = "var(--lbl-286)", "var(--lbl-keep)"
PTS = [p[1] for p in PRS]

# hue = corpus family, dash = size inside the family
PUB, PRIV = "var(--s-pub)", "var(--s-priv)"
SERIES = [("public synthetic, 1 800", "synth300", PUB,  None),
          ("public synthetic, 600",   "synth100", PUB,  "5 3"),
          ("public synthetic, 71",    "tiny",     PUB,  "1 3"),
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

def iterchain(pt):
    """median warm iteration latency on the large specification; CEIL when the run
       was stopped at the ceiling rather than finishing"""
    r = ICHAIN.get(pt)
    if not r:
        return None
    ms, _, _, done = r
    return ms if done else CEIL

def iterlat(pt, cp=None):
    """median iteration latency at this point, ms; measured on the 1 800-obligation
       corpus only, so it is a single series rather than one per corpus"""
    return ITER.get(pt)

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
        pt = PRS[i][1]
        keep = pt in SELECTED
        col = GREEN if keep else ("%s" % VIOLET if pt in FROM_286 else "currentColor")
        op = "1" if (keep or pt in FROM_286) else ".45"
        deco = ' text-decoration="underline"' if (keep and pt in FROM_286) else ""
        o.append('<text x="%.1f" y="%d" text-anchor="end" font-family="IBM Plex Mono, monospace" '
                 'font-size="9.5" fill="%s" opacity="%s"%s transform="rotate(-45 %.1f %d)">%s</text>'
                 % (xs(i), H-B+15, col, op, deco, xs(i), H-B+15, lab))
    lx, ly, row = L, T-13, 0
    o.append('<g font-family="IBM Plex Sans, sans-serif" font-size="11">')
    for lab, cp, col, dash in SERIES:
        w = 30 + int(5.9*len(lab))
        if lx + w > W - R - 130 and row == 0:      # keep clear of the note on the right
            row, lx, ly = 1, L, T + 2
        da = ' stroke-dasharray="%s"' % ("4 2.5" if dash == "5 3" else "1.5 2.5") if dash else ""
        o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="2"%s/>'
                 % (lx, ly, lx+14, ly, col, da))
        o.append('<text x="%d" y="%d" fill="currentColor">%s</text>' % (lx+19, ly+3.5, lab))
        lx += w
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
A("""  <p><strong>The commit labels are colour-coded.</strong>
  <span style="color:var(--lbl-keep);font-weight:600">Green</span> is content the short proposal keeps;
  <span style="color:var(--lbl-286);font-weight:600">violet</span> is content that came from
  <a href="https://github.com/tlaplus/tlapm/issues/286">tlaplus/tlapm#286</a> and that the short
  proposal drops; <span style="color:var(--lbl-keep);font-weight:600;text-decoration:underline">green
  underlined</span> is both &mdash; from #286 and kept. Grey is new here and dropped. Provenance is
  read from the commit messages, which name the reference implementation each one came from.</p>
  <p>The pattern is worth reading off the axis: <strong>the short proposal keeps #286&rsquo;s
  structural work and drops its micro-fix batch.</strong> Everything violet &mdash; the level
  slicing, the <code>Ctx</code> index, the SMT regexes, <code>app_ix</code>, the flatten guard, the
  obligation comment &mdash; comes from one commit of that issue, and none of it moves any metric here
  beyond its own spread. What survives from #286 is the deque lookups, the single-pass expansion, the
  two prunes and the linear ENABLED scan.</p>""")
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
A('    <h4 style="margin:0 0 2px">Iteration latency</h4>')
A('    <p style="font-size:13.5px;color:var(--ink-2);margin:0 0 12px">The wait after editing one proof '
  'step in a file whose fingerprints are all present: parse, elaborate, generate, check every '
  'obligation against the cache, report the hits, prove the one that changed. This is the loop a '
  'user actually sits in, and it is the run in which a warm cache is exercised rather than bypassed. '
  'Median of three runs on the public 1 800-obligation corpus and of two on the private '
  'refinement chain, whose proving range is restricted to its widest failure-free span (3 773 '
  'obligations) so the number measures tlapm rather than the re-attempt of obligations this '
  'environment cannot prove &mdash; parsing, elaboration and generation still cover the whole '
  '14 522-line module. Worst spread %.0f&nbsp;%% and %.0f&nbsp;%%. Lower is better.</p>'
  % (100*max(ITER_SPREAD.values()) if ITER_SPREAD else 0,
     100*max((v[1] for v in ICHAIN.values()), default=0)))
A('    ' + chart("Iteration latency",
    "Iteration latency after a single edit with a full fingerprint cache, one point per pull request: 8.8 seconds on main falling to 2.5 seconds, with the steps at the deque lookups, the single-pass expansion and the prefix caches.",
    {"synth300": [iterlat(p) for p in PTS], "synth100": [None]*len(PTS),
     "tiny": [None]*len(PTS), "ffi": [iterchain(p) for p in PTS],
     "mono": [None]*len(PTS)}, "ms",
    lambda v: "%.2f s" % (v/1000.0)))
A("""    <figcaption>On the public corpus three changes carry it &mdash; the deque lookups
    (&times;1.51), the single-pass expansion (&times;1.46) and the prefix-resume caches (&times;1.30).
    On the real specification only <em>two</em> do, and the shape is different: <code>main</code>, the
    bugfixes and the deque fix never finish a warm re-check inside half an hour (they report 3 501,
    3 561 and 3 578 of 3 774 obligations), the single-pass expansion takes it to 143.9 s, and the
    caches to 34.6 s &mdash; &times;4.1, the largest single step on this metric anywhere. The prunes
    are &times;1.01 there and &times;1.08 on the synthetic: they cut the work a prover sees, not the
    work a warm re-check does. <code>tlapm -N</code> with no cache is kept in the raw table as the floor it
    is: it measures the part of the loop that runs before any obligation is looked up, which is why it
    ranks the deque fix first on a corpus where the deque fix does not break the wall.</figcaption>""")
A('  </figure>')

def keystroke(pt):
    r = KEYS.get(pt)
    return r[0]*1000 if r else None

A('  <figure style="margin-top:20px">')
A('    <h4 style="margin:0 0 2px">Keystroke to diagnostics</h4>')
A("""    <p style="font-size:13.5px;color:var(--ink-2);margin:0 0 12px">Measured at the
    language-server protocol boundary on the refinement chain: spawn the server on stdio,
    <code>initialize</code>, <code>didOpen</code>, then one whitespace-only <code>didChange</code>,
    timed until the <code>publishDiagnostics</code> carrying that document version. No prover, no
    fingerprint invalidation &mdash; this is the wait while typing. Where three samples could not
    separate two neighbours, the pair was re-run at ten; the table gives n per point. Lower is
    better.</p>""")
A('    ' + chart("Keystroke to diagnostics",
    "Keystroke to diagnostics on the refinement chain, one point per pull request: 39.6 seconds on main falling to 5.1 seconds, almost all of it at the deque lookups.",
    {"synth300": [None]*len(PTS), "synth100": [None]*len(PTS), "tiny": [None]*len(PTS),
     "ffi": [keystroke(p) for p in PTS], "mono": [None]*len(PTS)}, "ms",
    lambda v: "%.1f s" % (v/1000.0)))
A("""    <figcaption>One change carries it: the deque lookups, 40.8 s to 10.1 s. After that the
    only step that clears its own spread is the editor obligation pool (6.54 s to 4.51 s, ranges
    disjoint at n=10), with the linear ENABLED scan just behind it (8.59 s to 7.14 s, also disjoint).
    Everything else on this metric is inside the noise, the grammar memo included &mdash; parsing is
    0.85 s of a 40 s keystroke here, so a parser change cannot show on this corpus.</figcaption>""")
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
  '<th class="num">keystroke</th><th class="num">iteration</th><th class="num">gen, 1 800</th><th class="num">prep, 1 800</th>'
  '<th class="num">peak, 1 800</th><th class="num">prep, chain</th><th class="num">prep, 30k</th>'
  '<th class="num">peak, 30k</th></tr></thead>')
A('      <tbody>')
for i, (lab, pt, name) in enumerate(PRS):
    tag = "main" if i == 0 else ("bugfixes" if i == 1 else "#%d" % (i-1))
    it = iterlat(pt)
    ks = KEYS.get(pt)
    A('        <tr><td class="num">%s</td><td>%s</td><td class="num">%s</td><td class="num">%s</td>'
      '<td class="num">%s</td><td class="num">%s</td><td class="num">%s</td><td class="num">%s</td>'
      '<td class="num">%s</td><td class="num">%s</td></tr>'
      % (tag, name,
         ("%.2f s <span style=\'opacity:.55\'>n=%d</span>" % (ks[0], ks[2])) if ks else "&mdash;",
         fmt_ms(it) if it else "&mdash;",
         fmt_ms(get(pt,"synth300","m0_ms")), fmt_ms(get(pt,"synth300","m1_ms")),
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
ia, ib = iterlat("c00"), iterlat("c26")
ka, kb = KEYS.get("c00"), KEYS.get("c26")
A("""  <p style="margin-top:14px"><strong>&times;%.1f on the keystroke, and on the public medium case
  &times;%.1f on iteration latency, &times;%.1f on throughput, &times;%.1f on peak memory.</strong> %d of the nineteen pull requests move
  throughput on that corpus by less than the noise floor on their own; they are in the set because of
  what they do on the two large specifications and because of the mechanism, both of which &sect;6
  states per commit.</p>""" % (ka[0]/kb[0] if ka and kb else 0, ia/float(ib), m1a/float(m1b), pa/float(pb), below))
A('</section>')

sec = "\n".join(o) + "\n"
path = os.environ.get("PROPOSAL_HTML", os.path.join(S, "PROPOSAL.html"))
src = open(path).read()
start = src.index('<section>\n  <div class="sec-head"><span class="n">05</span>')
end = src.index('<section>\n  <div class="sec-head"><span class="n">06</span>')
open(path, "w").write(src[:start] + sec + "\n" + src[end:])
print("section 05: one chart per metric, four corpora, log axis")
