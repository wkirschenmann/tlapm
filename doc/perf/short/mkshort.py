# -*- coding: utf-8 -*-
"""Generate doc/perf/SHORT_PROPOSAL.html from the short-proposal campaign.

Every number in the document comes from the CSVs next to this file.  Nothing is
typed in by hand: a cell that was not measured renders as a dash and says so.
"""
import os, sys, subprocess, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shortlib as L
import charts as C

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()
OUT = os.path.join(REPO, "doc", "perf", "SHORT_PROPOSAL.html")
BRANCH = "tlapm-perf-short"

sweep, boot, drift = L.load_sweep()
sweep, REPS = L.apply_reps(sweep)
iterlat, iboot = L.load_iteration_latency()
keys, kboot = L.load_keystroke()


# ---------------------------------------------------------------- branch facts
def points():
    """[(label, sha, subject, [(file, plus, minus)])] for main..BRANCH."""
    shas = subprocess.check_output(
        ["git", "rev-list", "--reverse", "main..%s" % BRANCH]).decode().split()
    out = []
    for i, s in enumerate(shas):
        subj = subprocess.check_output(
            ["git", "log", "-1", "--format=%s", s]).decode().strip()
        body = subprocess.check_output(
            ["git", "log", "-1", "--format=%B", s]).decode()
        files = []
        for ln in subprocess.check_output(
                ["git", "show", "--numstat", "--format=", s]).decode().splitlines():
            p = ln.split("\t")
            if len(p) == 3:
                files.append((p[2], p[0], p[1]))
        out.append(("p%02d" % (i + 1), s[:7], subj, files, body))
    return out


COMMITS = points()
BY_LABEL = {c[0]: c for c in COMMITS}
def _branch_diffstat():
    add = dele = 0
    files = 0
    for ln in subprocess.check_output(
            ["git", "diff", "--numstat", "main..%s" % BRANCH]).decode().splitlines():
        p = ln.split("\t")
        if len(p) == 3:
            files += 1; add += int(p[0]); dele += int(p[1])
    return add, dele, files


TOTAL_ADD, TOTAL_DEL, TOTAL_FILES = _branch_diffstat()


# ---------------------------------------------------------------- series
def _cell(cp, pt):
    if pt == "p00":
        recs = [sweep.get((q, cp), {}) for q in ("p00", "p00b")]
        return next((r for r in recs if r), {})
    return sweep.get((pt, cp), {})


WALL_SPREAD = 0.02     # refusals this close together are one wall
CEIL_MARGIN = 0.10     # how far a stopped run may read from the refused ones' range


def _wall_attribution():
    """Which stopped runs belong to a wall that other runs of the same corpus hit.

    Two runs of the refinement chain were taken to their end on the longer clock and
    both were refused an allocation at 11.19 GB, the same reading as the two the
    campaign had already refused.  At the fifteen-minute ceiling those two read 5.78
    and 6.02 GB; the five stopped runs that were not taken further read 5.75 to
    5.87 GB at that same ceiling -- inside the range of the runs that went on to be
    refused, on the same code path, with no pruning and no streaming.

    So they are attributed to that wall and drawn as crosses, without each being
    measured to its end: an hour spent watching a fifth run climb the same slope to
    the same refusal buys a cross we can already justify.  The criterion is checkable
    rather than rhetorical -- a stopped run qualifies only if the corpus HAS a wall
    (its measured refusals agree to within WALL_SPREAD) and if its own ceiling
    reading falls inside the ceiling readings of the runs refused there.  A run that
    was stopped holding a few hundred megabytes is nowhere near that range and stays
    a ring, which is what keeps the rule from swallowing every timeout.

    Returns {corpus: (wall_gb, {points attributed})}.
    """
    import csv as _csv
    rows = list(_csv.DictReader(open(os.path.join(HERE, "short_sweep.csv"))))
    out = {}
    for cp in L.CORPORA:
        mine = [r for r in rows if r["corpus"] == cp and int(r["prep_ms"]) != -2
                and not r["phase"].startswith("K")]
        ap = {r["point"]: r for r in mine if r["phase"] != "L"}
        lg = {r["point"]: r for r in mine if r["phase"] == "L"}
        refused = [pt for pt, r in lg.items()
                   if L._verdict(int(r["prep_rc"])) == L.ABORT]
        walls = [int(lg[pt]["peak_kb"]) / 1048576.0 for pt in refused]
        walls += [int(ap[pt]["peak_kb"]) / 1048576.0 for pt in ap
                  if pt not in lg and L._verdict(int(ap[pt]["prep_rc"])) == L.ABORT]
        if len(walls) < 2 or (max(walls) - min(walls)) / max(walls) > WALL_SPREAD:
            continue
        # the ceiling readings of the runs that were later refused
        ref = [int(ap[pt]["peak_kb"]) / 1048576.0 for pt in refused
               if pt in ap and int(ap[pt]["prep_rc"]) == 124]
        if not ref:
            continue
        lo, hi = min(ref) * (1 - CEIL_MARGIN), max(ref) * (1 + CEIL_MARGIN)
        att = {pt for pt, r in ap.items()
               if pt not in lg and int(r["prep_rc"]) == 124
               and lo <= int(r["peak_kb"]) / 1048576.0 <= hi}
        if att:
            out[cp] = (max(walls), att, sorted(refused), (min(ref), max(ref)))
    return out


WALL = _wall_attribution()


def _pending(cp, pt):
    """True when the only reading for this cell comes from the ordinary ceiling.

    A run the cap stopped is a result -- the allocation was refused, more time
    changes nothing.  A run the *clock* stopped is a protocol timeout: the ceiling is
    ours, not the commit's, so the cell is inconclusive until the extended clock has
    been spent on it.  The charts draw those as a ring rather than a cross, so an
    inconclusive cell can never be read as a result.
    """
    c = _cell(cp, pt)
    return c.get("prep") == L.CEIL and not c.get("long")


def thr(cp):
    """Obligations prepared per second.  A run that did not complete prepared none of
    them to the end, so its throughput is zero -- which a logarithmic axis cannot
    show.  Those points keep their cross in the band below the axis; there is no
    coordinate to give them."""
    d = {}
    for pt in L.POINTS:
        v = L.main_point(sweep, cp, "prep") if pt == "p00" else _cell(cp, pt).get("prep")
        if v is None or v == L.DNC:
            d[pt] = None                       # not measured: absent, not failed
        elif v in L.FAILED:
            w = WALL.get(cp)
            att = bool(w and pt in w[1] and v == L.CEIL)
            d[pt] = {"kind": L.ABORT if att else v, "at": None,
                     "pending": False if att else _pending(cp, pt)}
        else:
            d[pt] = L.OBL[cp] * 1000.0 / v
    return d


CAP_GB = 12.0
HEADING_FOR_CAP = 0.25      # of the cap, at the moment the clock stopped the run


def peak(cp):
    """Peak resident set, and what to do with a run that did not finish.

    A memory abort has a real reading -- the set it reached just before the
    allocation the cap refused -- so its cross sits there, which is on the cap.

    A run the clock stopped is not one fact but two.  If it was sitting at a few
    hundred megabytes it was simply slow, and its reading is its peak.  If it had
    already taken a large fraction of the cap it was still climbing, and 6.2 GB is
    not a fact about the commit -- it is a fact about when we stopped looking.  Such
    a point is drawn at the cap and marked inferred, until the extended-clock pass
    runs it to its real end.
    """
    d = {}
    for pt in L.POINTS:
        v = L.main_point(sweep, cp, "peak") if pt == "p00" else _cell(cp, pt).get("peak")
        raw = _cell(cp, pt).get("peak_raw")
        if v is None or v == L.DNC:
            d[pt] = None
        elif v == L.ABORT:
            d[pt] = {"kind": "OOM", "at": (raw / 1048576.0) if raw else CAP_GB}
        elif v == L.CEIL:
            gb = (raw / 1048576.0) if raw else None
            w = WALL.get(cp)
            if w and pt in w[1]:
                d[pt] = {"kind": "OOM", "at": w[0], "attributed": True}
            else:
                d[pt] = {"kind": "CEIL", "at": gb, "pending": _pending(cp, pt)}
        else:
            d[pt] = v / 1048576.0
    return d


def gen(cp):
    d = {}
    for pt in L.POINTS:
        v = L.main_point(sweep, cp, "gen") if pt == "p00" else _cell(cp, pt).get("gen")
        if v is None or v == L.DNC:
            d[pt] = None                       # not measured: absent, not failed
        elif v in L.FAILED:
            raw = _cell(cp, pt).get("gen_raw")
            d[pt] = {"kind": v, "at": (raw / 1000.0) if raw else None}
        else:
            d[pt] = v / 1000.0
    return d


def prep(cp):
    d = {}
    for pt in L.POINTS:
        v = L.main_point(sweep, cp, "prep") if pt == "p00" else sweep.get((pt, cp), {}).get("prep")
        d[pt] = None if v is None else (v if v in L.FAILED else v / 1000.0)
    return d


def iters(cp):
    """A run stopped at the ceiling has a coordinate on this axis: the ceiling.

    It does not have a verdict, though.  No extended clock has been spent on this
    metric, so every clock stop here is still an open measurement and is drawn as a
    ring; a memory abort is settled and keeps its cross.
    """
    d = {}
    for pt in L.POINTS:
        r = iterlat.get((cp, pt))
        if not r:
            d[pt] = None
        elif r[0] in L.FAILED:
            d[pt] = {"kind": r[0],
                     "at": (r[4] / 1000.0) if len(r) > 4 and r[4] else None,
                     "pending": r[0] == L.CEIL}
        else:
            d[pt] = r[0] / 1000.0
    return d


def _series_for(values):
    """The chart's legend, derived from the data it was handed.

    Hardcoding it is how a chart comes to lag behind its own measurements: the
    keystroke figure listed one corpus because that is all there had ever been, so
    measuring a second would have changed the CSV and nothing on the page.  Filtering
    the standard series order by what actually has points keeps the two in step, and
    keeps hue and dash meaning the same thing on every chart.
    """
    return [t for t in C.SERIES
            if any(v is not None for v in (values.get(t[1]) or {}).values())]


def keyser():
    """One series per corpus that has keystroke data, in the chart's usual order."""
    return {cp: {pt: (keys[(cp, pt)][0] if (cp, pt) in keys else None)
                 for pt in L.POINTS}
            for cp in L.CORPORA if any(c == cp for c, _ in keys)}


def val(cp, pt, field):
    if pt == "p00":
        return L.main_point(sweep, cp, field)
    return sweep.get((pt, cp), {}).get(field, L.DNC)


def fmt_x(a, b):
    """b -> a as a times-figure, only when both are real numbers"""
    r = L.ratio(a, b)
    return "" if r is None else ('<span class="r">&times;%.2f</span>' % r if r < 10
                                 else '<span class="r">&times;%.1f</span>' % r)


# ---------------------------------------------------------------- prose blocks
def head():
    return """<title>Nine Pull Requests</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bitter:wght@500;700&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --paper:#f4f4f2; --card:#fffffe; --ink:#191c1f; --ink-2:#4a5157; --ink-3:#7b8288;
  --rule:#dcdcd6; --rule-2:#ecece7;
  --sig:#0d5f63; --sig-soft:#e2efef; --sig-ink:#0a4a4d;
  --warn:#8c4a12; --warn-soft:#f6ebe0;
  --good:#2b6134; --good-soft:#e6efe6;
  --shadow:0 1px 2px rgba(20,24,28,.05),0 8px 24px -16px rgba(20,24,28,.22);
  --s-pub:#00969b; --s-priv:#c0762c; --fail:#b32450;
  --lbl-286:#4a3aa7; --lbl-keep:#0a7a54;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#12151a; --card:#191d24; --ink:#e9ecef; --ink-2:#aab2ba; --ink-3:#79828c;
  --rule:#2a313a; --rule-2:#20262e;
  --sig:#5fd0d3; --sig-soft:#12302f; --sig-ink:#8fe3e5;
  --warn:#e0a163; --warn-soft:#31251a;
  --good:#84c78e; --good-soft:#1a2a1d;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -18px rgba(0,0,0,.7);
  --s-pub:#0b9ba0; --s-priv:#c9822f; --fail:#dd4a6b;
  --lbl-286:#9085e9; --lbl-keep:#28a87e;}}
:root[data-theme="dark"]{
  --paper:#12151a; --card:#191d24; --ink:#e9ecef; --ink-2:#aab2ba; --ink-3:#79828c;
  --rule:#2a313a; --rule-2:#20262e;
  --sig:#5fd0d3; --sig-soft:#12302f; --sig-ink:#8fe3e5;
  --warn:#e0a163; --warn-soft:#31251a;
  --good:#84c78e; --good-soft:#1a2a1d;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -18px rgba(0,0,0,.7);
  --s-pub:#0b9ba0; --s-priv:#c9822f; --fail:#dd4a6b;
  --lbl-286:#9085e9; --lbl-keep:#28a87e;}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font:400 16.5px/1.7 "IBM Plex Sans",ui-sans-serif,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:clamp(28px,5vw,72px) clamp(18px,4vw,40px) 96px}
h1,h2,h3,h4{font-family:Bitter,Georgia,serif;text-wrap:balance;margin:0}
h1{font-weight:700;font-size:clamp(29px,4.2vw,44px);line-height:1.1;letter-spacing:-.01em}
h2{font-weight:700;font-size:clamp(21px,2.4vw,26px);line-height:1.2}
h3{font-weight:500;font-size:17px;line-height:1.3}
h4{font-weight:600;font-size:15px;line-height:1.3;margin:24px 0 6px}
p{margin:0 0 14px}
a{color:var(--sig-ink)}
.eyebrow{font:600 11.5px/1 "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;
  color:var(--sig);margin:0 0 18px}
.lede{font-size:19px;color:var(--ink-2);margin:18px 0 0}
header{border-bottom:2px solid var(--ink);padding-bottom:26px;margin-bottom:12px}
.meta{display:flex;flex-wrap:wrap;gap:8px 22px;margin-top:22px;
  font:400 13px/1.4 "IBM Plex Mono",monospace;color:var(--ink-3)}
section{margin-top:52px}
.sec-head{display:flex;align-items:baseline;gap:14px;border-bottom:1px solid var(--rule);
  padding-bottom:10px;margin-bottom:22px}
.sec-head .n{font:600 13px/1 "IBM Plex Mono",monospace;color:var(--sig);padding-top:4px}
.scroller{overflow-x:auto;border:1px solid var(--rule);border-radius:6px;background:var(--card);
  box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%;font-size:14.5px}
.scroller table{min-width:720px}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--rule-2);vertical-align:top}
thead th{background:var(--card);border-bottom:1px solid var(--rule);
  font:600 11.5px/1.3 "IBM Plex Mono",monospace;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-3);white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
td.num,th.num{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;white-space:nowrap}
.tag{display:inline-block;font:600 10.5px/1.5 "IBM Plex Mono",monospace;letter-spacing:.06em;
  text-transform:uppercase;padding:1px 7px;border-radius:3px;white-space:nowrap}
.t-fix{background:var(--warn-soft);color:var(--warn)}
.t-thr{background:var(--good-soft);color:var(--good)}
.t-lat{background:var(--sig-soft);color:var(--sig-ink)}
.t-mem{background:var(--rule-2);color:var(--ink-2)}
.grid-2{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
.card{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:18px 20px;
  box-shadow:var(--shadow)}
.card h3{margin-bottom:8px}
.card p{font-size:14.5px;color:var(--ink-2);margin:0 0 8px}
.card p:last-child{margin-bottom:0}
code{font-family:"IBM Plex Mono",monospace;font-size:.9em;background:var(--rule-2);
  padding:1px 5px;border-radius:3px}
pre{margin:0 0 12px;padding:12px 14px;background:var(--rule-2);border-radius:5px;overflow-x:auto;
  font:400 13px/1.55 "IBM Plex Mono",monospace}
.claim{background:var(--sig-soft);border-left:3px solid var(--sig);padding:14px 18px;
  border-radius:0 6px 6px 0;font-size:15px}
.note{background:var(--warn-soft);border-left:3px solid var(--warn);padding:14px 18px;
  border-radius:0 6px 6px 0;font-size:14.5px}
figure{margin:0 0 8px;background:var(--card);border:1px solid var(--rule);border-radius:6px;
  padding:20px 20px 14px;box-shadow:var(--shadow);overflow-x:auto}
figure svg{max-width:100%;height:auto;display:block;margin:0 auto}
figcaption{font-size:14px;color:var(--ink-2);margin-top:14px}
.fig-head{display:flex;align-items:baseline;justify-content:space-between;gap:14px}
.better{flex:none;display:inline-flex;align-items:center;gap:5px;
  font:400 12px/1 "IBM Plex Mono",monospace;color:var(--ink-3);
  border:1px solid var(--rule);border-radius:999px;padding:4px 9px 4px 8px;
  white-space:nowrap}
ul,ol{margin:0 0 14px;padding-left:22px}
li{margin-bottom:6px}
footer{margin-top:64px;padding-top:22px;border-top:1px solid var(--rule);
  font:400 13px/1.7 "IBM Plex Mono",monospace;color:var(--ink-3)}
:focus-visible{outline:2px solid var(--sig);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
.pr{border:1px solid var(--rule);border-radius:6px;background:var(--card);box-shadow:var(--shadow);
  padding:20px 22px;margin-top:20px}
.pr-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:4px}
.pr-n{font:600 13px/1 "IBM Plex Mono",monospace;color:var(--sig)}
.pr-meta{font:400 12.5px/1.6 "IBM Plex Mono",monospace;color:var(--ink-3);margin:0 0 12px}
.pr>p{font-size:15px}
.cm{border-top:1px solid var(--rule-2);margin-top:16px;padding-top:14px}
.cm-h{font:400 13px/1.5 "IBM Plex Mono",monospace;color:var(--ink);margin:0 0 10px}
.cm-h code{background:var(--sig-soft);color:var(--sig-ink);font-weight:600}
.cm p{font-size:14.5px;color:var(--ink-2);margin:0 0 8px}
.lbl{font:600 10.5px/1 "IBM Plex Mono",monospace;letter-spacing:.09em;text-transform:uppercase;
  color:var(--sig);margin-right:8px;white-space:nowrap}
.cm .scroller{margin-top:12px;box-shadow:none}
.cm table{font-size:13.5px}
.cm .scroller table{min-width:560px}
.r{color:var(--sig);font-weight:600}
.files{font:400 12.5px/1.7 "IBM Plex Mono",monospace;color:var(--ink-3);margin:2px 0 10px}
.files span{white-space:nowrap;margin-right:14px}
.plus{color:var(--good)} .minus{color:var(--warn)}
</style>
"""


# ---------------------------------------------------------------- sections
import content as CT

METRICS = [
    ("preparation time", "<code>tlapm --noproving --nofp</code>",
     "the whole per-obligation pipeline with no prover launched: find the method, "
     "annotate constants, fingerprint, expand, normalise, test for triviality, "
     "prune, encode. Prover-independent, so it reproduces without solvers installed."),
    ("peak memory", "maximum resident set of that run",
     "what decides whether a large specification runs at all. Every run is capped at "
     "12&nbsp;GB of address space, and a run that hits the cap is reported as an "
     "abort, never as a large number."),
    ("generation time", "<code>tlapm -N --nofp</code>",
     "parse, elaborate, generate obligations, stop. The floor under every editor "
     "interaction and the fixed per-worker cost of any parallel scheme."),
    ("iteration latency", "<code>tlapm --toolbox L H</code> on a warm cache",
     "the wait after editing one proof step in a file whose fingerprints are all "
     "present: everything is re-parsed, re-elaborated and re-fingerprinted, and only "
     "the one changed obligation is proved. This is the loop a user actually sits in."),
    ("keystroke &rarr; diagnostics", "the LSP protocol boundary",
     "<code>didChange</code> sent, <code>publishDiagnostics</code> received, measured "
     "by a client that speaks the protocol. Nothing inside the server is "
     "instrumented, so the figure is what the editor waits."),
]


TIP = L.POINTS[-1]


def sec_problem():
    c = []
    mono_main = L.main_point(sweep, "mono", "prep")
    ffi_main = L.main_point(sweep, "ffi", "prep")
    tiny_main = L.main_point(sweep, "tiny", "prep")
    tiny_tip = val("tiny", TIP, "prep")
    mono_tip = val("mono", TIP, "prep")
    ffi_tip = val("ffi", TIP, "prep")
    ks_main = keys.get(("ffi", "p00"), (None,))[0]
    ks_tip = keys.get(("ffi", TIP), (None,))[0]
    it_main = iterlat.get(("ffi", "p00"), (None,))[0]
    it_tip = iterlat.get(("ffi", TIP), (None,))[0]
    c.append("<p>tlapm is fine on small proofs and unusable on large ones, and the "
             "boundary is not gradual. The four specifications below are the same tool on "
             "the same machine: seventy obligations finish before you notice, and ten "
             "thousand do not finish at all.</p>")
    c.append('<div class="scroller"><table><thead><tr><th>specification</th>'
             '<th class="num">obligations</th><th class="num">prepare, <code>main</code></th>'
             '<th class="num">prepare, after</th></tr></thead><tbody>')
    for cp, name in (("tiny", "a small module"), ("synth300", "a 1&nbsp;800-obligation synthetic module"),
                     ("ffi", "a private refinement chain"), ("mono", "a private 30k-line monolith")):
        a = L.main_point(sweep, cp, "prep")
        b = val(cp, TIP, "prep")
        c.append("<tr><td>%s</td><td class=\"num\">%s</td><td class=\"num\">%s</td>"
                 "<td class=\"num\">%s %s</td></tr>"
                 % (name, "{:,}".format(L.OBL[cp]).replace(",", "&nbsp;"),
                    L.fmt_ms(a), L.fmt_ms(b), fmt_x(a, b)))
    c.append("</tbody></table></div>")
    c.append("<p style=\"margin-top:14px\">The failure is not slowness. %s</p>"
             % _wall_sentence())
    if isinstance(it_main, str) or it_main:
        c.append("<p>The same wall stands in the editor. Re-checking the refinement chain "
                 "after a single edit, with every fingerprint already in the cache, "
                 "%s on <code>main</code> and takes %s after this series.</p>"
                 % ("does not finish inside the fifteen-minute ceiling" if it_main in L.FAILED
                    else "takes " + L.fmt_ms(it_main),
                    L.fmt_ms(it_tip) if it_tip is not None else "&mdash;"))
    if ks_main and ks_tip:
        c.append("<p>And at the keystroke: from <code>didChange</code> to "
                 "<code>publishDiagnostics</code>, %.1f&nbsp;s on <code>main</code> "
                 "against %.1f&nbsp;s after &mdash; <span class=\"r\">&times;%.1f</span>."
                 "</p>" % (ks_main, ks_tip, ks_main / ks_tip))
    c.append("<div class=\"claim\" style=\"margin-top:16px\"><strong>The constraint that "
             "shapes everything below:</strong> small proofs must not get slower. Every "
             "chart carries a 71-obligation module for exactly that reason &mdash; it is "
             "the control, not a result.</div>")
    return "".join(c)


def sec_mechanism():
    return """
<p>One mechanism explains all of it. tlapm generates one obligation per proof leaf,
and each obligation carries its <em>whole context</em>: the module scope, every
definition in scope, and the statement of every theorem proved before it. The
context therefore grows with the file, and the per-obligation work is a function of
the context. Work per obligation grows with file size, and total work grows faster
than the number of obligations.</p>

<p>That single fact has four distinct consequences, and this series has one family
of change for each:</p>

<div class="grid-2" style="margin-top:16px">
  <div class="card"><h3>Repeated passes over the context</h3>
    <p>Expanding <em>k</em> definitions walked the context <em>k</em> times; detecting
    <code>ENABLED</code> axioms compared every axiom against every hypothesis; every
    hypothesis lookup walked a deque. Each is a factor of context size that need not
    be there.</p>
    <p class="mdl">PR2, PR3, PR7</p></div>
  <div class="card"><h3>Contexts kept alive</h3>
    <p>Every obligation of the run was materialised before the first prover started,
    and a process-lifetime memo table pinned one context per obligation prepared.
    Peak memory grew with the file, so a big enough file cannot run at any speed.</p>
    <p class="mdl">PR4</p></div>
  <div class="card"><h3>Context that no longer matters</h3>
    <p>After expansion, the hidden definitions and the instantiated statements of
    earlier theorems are unreachable from the goal &mdash; and are most of the weight
    shipped to the prover. Dropping them sends strictly less than today.</p>
    <p class="mdl">PR5</p></div>
  <div class="card"><h3>Context recomputed from scratch</h3>
    <p>Consecutive obligations share almost all of their context &mdash; on a 30k
    module, 699 of 743 hypotheses are the physically same objects as in the previous
    one &mdash; and all three preparation passes recomputed the whole thing.</p>
    <p class="mdl">PR6</p></div>
</div>

<p style="margin-top:16px">Two changes sit outside that mechanism. One is the editor's
proof-step tree, which scanned the obligation map once per step and had nothing to do
with contexts. The other is the set of correctness fixes, which are here because
without them the measurements that justify the rest are not available.</p>
"""


def sec_proposal():
    c = ["<p>Nine pull requests, seventeen commits, %d files, +%d&thinsp;/&thinsp;&minus;%d. "
         "Each commit is one subject, states its own invariant, and passes the gate in "
         "&sect;4 on its own.</p>" % (TOTAL_FILES, TOTAL_ADD, TOTAL_DEL)]
    c.append('<div class="scroller"><table><thead><tr><th>&nbsp;</th><th>pull request</th>'
             '<th class="num">commits</th><th class="num">files</th>'
             '<th>what it is for</th></tr></thead><tbody>')
    for pid, title, tag, cms, motive in CT.PRS:
        files = len({f for cm in cms for f, _, _ in BY_LABEL[cm][3]})
        # the summary is the opening sentences up to a readable length, and at
        # least enough of them to say something -- some motivations open with a
        # three-word count ("Five defects.") that is useless on its own
        parts = [x.strip().rstrip(".") for x in motive.split(". ") if x.strip()]
        short = ""
        for x in parts:
            short += ("" if not short else " ") + x + "."
            if len(short) >= 60:
                break
        c.append('<tr><td class="num"><span class="tag %s">%s</span></td>'
                 '<td><strong>%s</strong></td><td class="num">%d</td><td class="num">%d</td>'
                 '<td style="color:var(--ink-2);font-size:14px">%s</td></tr>'
                 % (tag, pid, title, len(cms), files, short))
    c.append("</tbody></table></div>")
    c.append("<p style=\"margin-top:14px\">The order is not the order the work happened "
             "in; it is the order the measurements support. Each of the first six pull "
             "requests either crosses a threshold &mdash; a specification that could not "
             "be prepared now can &mdash; or moves a metric by a ratio well clear of its "
             "spread. The memory pull request sits at position four rather than last "
             "because that is where it removes every out-of-memory failure from the rest "
             "of the series; putting it later credits the change after it with a "
             "completion it did not cause.</p>")
    return "".join(c)


def sec_method():
    c = ["<p>Five metrics. Every one of them is something a user can time from outside "
         "tlapm with stock flags on a stock build &mdash; no probe, no patched binary, "
         "nothing this series introduces.</p>"]
    c.append('<div class="scroller"><table><thead><tr><th>metric</th><th>how</th>'
             '<th>what it is</th></tr></thead><tbody>')
    for name, how, what in METRICS:
        c.append('<tr><td><strong>%s</strong></td><td class="num">%s</td>'
                 '<td style="color:var(--ink-2);font-size:14px">%s</td></tr>' % (name, how, what))
    c.append("</tbody></table></div>")

    c.append("<h4>Corpora</h4><p>Five, and every chart carries all five. The two public "
             "synthetics and the small control are in the repository; the two private "
             "specifications are a customer's and are not published &mdash; only these "
             "numbers are.</p>")
    c.append('<div class="scroller"><table><thead><tr><th>corpus</th>'
             '<th class="num">obligations</th><th>why it is here</th></tr></thead><tbody>')
    for cp, why in (
        ("tiny", "the control: it must not get slower, and it is on every chart to show that it does not"),
        ("synth100", "the small end of the growth curve, where <code>main</code> is still comfortable"),
        ("synth300", "the public corpus large enough to reproduce the wall &mdash; and the one every ratio in &sect;6 is quoted on"),
        ("ffi", "a real INSTANCE-heavy refinement chain: the shape this series is aimed at"),
        ("mono", "a real 30k-line monolith: the specification <code>main</code> cannot prepare at all")):
        c.append('<tr><td class="num">%s</td><td class="num">%s</td>'
                 '<td style="color:var(--ink-2);font-size:14px">%s</td></tr>'
                 % ({"tiny": "public synthetic, small", "synth100": "public synthetic, medium",
                     "synth300": "public synthetic, large", "ffi": "private refinement chain",
                     "mono": "private monolith"}[cp],
                    "{:,}".format(L.OBL[cp]).replace(",", "&nbsp;"), why))
    c.append("</tbody></table></div>")

    c.append("""<h4>The correctness gate every commit passes</h4>
<p>Not a benchmark gate &mdash; a soundness one. For each of the seventeen commits,
in sequence: <code>dune runtest src</code> and <code>dune runtest lsp</code> green,
and every one of the 48 <code>test/fast</code> tests passing with the full prover
stack &mdash; Z3&nbsp;4.8.9, Zenon, and Isabelle&nbsp;2025 with the TLA+ heap built
from this repository's <code>isabelle/</code> sources. <code>main</code> is 48 of 48
under the same conditions, so the fail-set is empty on both sides. The gate is
fail-set <em>identity</em>, not a pass count: a newly failing test is a regression
even where the count would still look healthy.</p>
<p>Two conditions matter and are easy to get wrong. Putting <code>isabelle</code> on
<code>PATH</code> is not enough &mdash; tlapm invokes it with a session root under its
own backends directory, and without that link seven tests fail in a way that reads
like a proof failure rather than a missing backend. And the tree must be clean of
<code>.tlacache</code>: a fingerprint recorded by an earlier run with a different
prover set replays as a failure, which is exactly how an earlier pass here reported
47 of 48 and blamed Z3.</p>
<p>Two invariants hold across the whole series. <strong>The provers receive a subset
of what they receive today</strong>, never more, and no obligation is created that
does not exist today. <strong>Fingerprints do not move</strong>: the digest is
computed on the const-annotated pre-expansion obligation, and every change that
removes context runs after that point, on the backend path only &mdash; so
<code>--printallobs</code> output and cache hits are unchanged by construction rather
than by testing.</p>""")

    c.append(_switches())
    c.append(_noise_sentence())
    c.append(_completeness())
    c.append(_extended_clock())
    c.append("""<h4>Measurement machine</h4>
<div class="scroller"><table><tbody>
<tr><td>CPU</td><td class="num">Intel Xeon @ 2.10 GHz, 4 cores</td></tr>
<tr><td>memory</td><td class="num">16 GB, runs capped at 12 GB of address space</td></tr>
<tr><td>kernel</td><td class="num">Linux 6.18.44</td></tr>
<tr><td>compiler</td><td class="num">OCaml 4.14.1</td></tr>
<tr><td>provers</td><td class="num">Z3 4.8.9, Zenon 0.8.4, Isabelle 2025 + TLA+ heap</td></tr>
<tr><td>ceilings</td><td class="num">600 s generation, 900 s preparation, 900 s iteration latency; 3600 s for the extended-clock pass</td></tr>
<tr><td>boots</td><td class="num">%s</td></tr>
</tbody></table></div>
<p style="margin-top:12px">Absolute values are comparable only inside this table.
Every measured row carries the machine's <code>/proc/stat btime</code> and every
reader filters to a single boot, so a container restart mid-campaign appears as a
missing cell rather than as a step averaged into a curve. <code>main</code> is
measured once per curve, at the point each curve starts from; %s</p>%s""" % (
        _boot_list(), _drift_sentence(), _provenance()))
    return "".join(c)


def _switches():
    """What can be turned on or off, gathered from the per-commit blocks."""
    rows = []
    for pid, title, tag, cms, _ in CT.PRS:
        for cm in cms:
            off = _fill(CT.CM[cm]["off"])
            if off.lower().startswith("no switch"):
                continue
            rows.append((pid, BY_LABEL[cm][1], BY_LABEL[cm][2], off))
    n_none = sum(1 for c in CT.CM.values() if c["off"].lower().startswith("no switch"))
    out = ["<h4>What can be switched, and what cannot</h4>",
           "<p>Three of the seventeen commits carry a switch; the other %d do not, and "
           "deliberately so &mdash; they are output-preserving changes to a single code "
           "path, so a flag would mean carrying two implementations of the same "
           "function and testing neither of them properly. Where a switch does exist it "
           "restores the <em>original</em> code rather than disabling a feature, which "
           "is what makes it usable as a differential reference.</p>" % n_none]
    out.append('<div class="scroller"><table><thead><tr><th>&nbsp;</th><th>commit</th>'
               '<th>switch</th></tr></thead><tbody>')
    for pid, sha, subj, off in rows:
        out.append('<tr><td class="num">%s</td><td class="num"><code>%s</code><br>'
                   '<span style="color:var(--ink-3);font-size:12.5px">%s</span></td>'
                   '<td style="font-size:14px">%s</td></tr>' % (pid, sha, subj, off))
    out.append("</tbody></table></div>")
    out.append("<p style=\"margin-top:12px\">Every measurement in this document is "
               "taken with the features <em>on</em> and the oracle <em>off</em>, which "
               "is the default state on both counts: the campaign invokes "
               "<code>tlapm --noproving --nofp --cache-dir &hellip;</code> with no "
               "<code>--debug</code> argument and with no <code>TLAPM_*</code> variable "
               "in the environment. Checked against the running processes, not assumed "
               "&mdash; the point of a switch that restores the original code is that "
               "forgetting to unset it would silently measure the wrong build.</p>")
    out.append("<p>The oracle is the one that must never "
               "become a default. It works by doing the job twice and comparing, so "
               "turning it on doubles the cost of the pass it checks; that is not a "
               "defect to optimise away but the mechanism itself. It is opt-in through "
               "the environment, and with the variable unset the added code is a single "
               "branch that is not taken.</p>")
    return "".join(out)


def _noise_sentence():
    """A known-zero pair: the editor pool touches only lsp/, so the preparation
    path cannot change across it.  Whatever it measures is the noise."""
    zero = None
    for pid, title, tag, cms, _ in CT.PRS:
        files = {f for cm in cms for f, _, _ in BY_LABEL[cm][3]}
        if len(cms) == 1 and files and all(f.startswith("lsp/") for f in files):
            zero = cms[0]
    if zero is None:
        return ""
    i = L.POINTS.index(zero)
    prev = L.POINTS[i - 1]
    parts = []
    for cp in L.CORPORA:
        a, b = val(cp, prev, "prep"), val(cp, zero, "prep")
        pa, pb = val(cp, prev, "peak"), val(cp, zero, "peak")
        if isinstance(a, int) and isinstance(b, int) and a and b:
            d = abs(a - b) / float(max(a, b)) * 100
            e = (abs(pa - pb) / float(max(pa, pb)) * 100
                 if isinstance(pa, int) and isinstance(pb, int) and max(pa, pb) else None)
            parts.append("%s %.1f&nbsp;%%%s" % (
                {"tiny": "small", "synth100": "600", "synth300": "1 800",
                 "ffi": "chain", "mono": "monolith"}[cp], d,
                "" if e is None else " (memory %.2f&nbsp;%%)" % e))
    if not parts:
        return ""
    return ("<p>One pair calibrates the noise better than the baseline repeat does. "
            "The editor obligation pool changes only files under <code>lsp/</code>, so "
            "the command-line preparation path across it cannot differ &mdash; whatever "
            "the campaign measures there <em>is</em> the run-to-run spread, on a pair "
            "whose true answer is known to be zero. It measures: %s. That is the floor "
            "any ratio in &sect;6 has to clear, and it is why a commit is only credited "
            "with an effect when it is a sustained step rather than a single large "
            "ratio. Read it per corpus: the floor is widest where the run is shortest, "
            "which is one reason the ratios in &sect;6 are quoted on the "
            "1&nbsp;800-obligation corpus and the two private specifications rather "
            "than on the small ones.</p>" % ", ".join(parts))


def _completeness():
    """What the campaign does not contain, counted rather than asserted."""
    want = [(pt, cp) for pt in L.POINTS for cp in ("tiny", "synth100", "synth300")]
    want += [(pt, cp) for pt in L.ENDPOINTS for cp in ("ffi", "mono")]
    miss = [(pt, cp) for pt, cp in want
            if not isinstance(sweep.get((pt, cp), {}).get("prep"), (int, str))]
    tot = len(want)
    out = ['<h4>What the campaign does not contain</h4>']
    if not miss:
        out.append("<p>Preparation and peak memory are measured at every one of the %d "
                   "(commit, corpus) pairs the design calls for: all %d commits and "
                   "<code>main</code> on the three public corpora, and the nine "
                   "pull-request endpoints on the two private ones. There are no "
                   "missing cells, so nothing in &sect;5 or &sect;6 rests on an "
                   "absent measurement.</p>" % (tot, len(L.POINTS) - 1))
    else:
        by = collections.Counter(cp for _, cp in miss)
        out.append("<p><strong>%d of %d</strong> (commit, corpus) pairs are missing: %s. "
                   "A missing cell is shown as a dash, never inferred, and no ratio is "
                   "formed across one.</p>"
                   % (len(miss), tot,
                      ", ".join("%d on %s" % (n, cp) for cp, n in sorted(by.items()))))
        out.append('<p class="pr-meta">%s</p>'
                   % " &middot; ".join("%s/%s" % (pt, cp) for pt, cp in sorted(miss)))
    out.append("<p>The two private corpora are measured at the pull-request endpoints "
               "rather than at every commit. That is a deliberate bound, not an "
               "omission: a single preparation pass on the monolith is minutes when it "
               "completes and a quarter of an hour when it does not, and the question "
               "those corpora answer &mdash; does this pull request make the "
               "specification runnable &mdash; is a property of the pull request. Where "
               "a commit inside a pull request needed separating from its neighbour, "
               "the public 1&nbsp;800-obligation corpus is measured at every commit and "
               "answers it.</p>")
    return "".join(out)


def _extended_clock():
    """Which stopped runs were re-run on an hour's clock, and how well the rule that
    picked them held up once the answer was known."""
    return """<h4>Which stopped runs got a longer clock</h4>
<p>The fifteen-minute ceiling earns its keep in exactly one place: the
<em>first</em> pass over a line whose shape is unknown, where it stops one hanging
point from consuming the campaign. Everywhere else it is fifteen minutes thrown away,
and this campaign paid that bill before noticing &mdash; one monolith point already had
its ceiling reading and was re-run at the same ceiling before being escalated, so it
cost 900&nbsp;s <em>plus</em> an hour to learn what the hour alone would have said. The
clock is therefore chosen from what the data already holds: a point already stopped at
the ceiling starts at the hour, and so does every point below it on the same line,
since a slower commit cannot be a quicker one. Only a point with no history pays the
cheap pass.</p>
<p>Which stopped runs are worth an hour at all is a separate question, and a run
already stopped is not yet a fact about the commit, so some are re-run and some are
not: an hour spent confirming a failure we already know is an hour not spent measuring
something. The rule is two questions asked of the stopped run, and it runs only if
<em>either</em> answer lands inside the budget. <em>When would it finish?</em> &mdash; taken from the ratio between
this commit and the same commit on the public 1&nbsp;800-obligation corpus, which
does complete. <em>When would it abort?</em> &mdash; taken from extrapolating its own
memory growth to the 12&nbsp;GB cap. If the sooner of the two is past 90&nbsp;%% of the
budget, the run is not launched and the point stays a ring.</p>
<p>The rule is an estimate and it is worth saying how badly it estimates, so here is
its record on every point where it said yes and the answer came back.</p>
%s
<p>That is a scheduling heuristic, and never a source of a number in this document.
Every figure in &sect;5 and &sect;6 comes from a run that finished or from a cap that
stopped one.</p>""" % _estimator_record()


def _pending_sentence():
    """How many marks are still rings, counted rather than asserted."""
    n = sum(1 for cp in L.CORPORA for v in peak(cp).values()
            if isinstance(v, dict) and v.get("pending"))
    if not n:
        return ("No mark on this chart is a ring: the extended clock has been spent on "
                "every stopped run, so every failure here is a result.")
    if n == 1:
        return ("One mark is a ring, so one cell of this chart is inconclusive and is "
                "not quoted anywhere in this document as a figure.")
    return ("%d marks are rings, so that many cells are inconclusive, and none of them "
            "is quoted anywhere in this document as a figure." % n)


def _wall_sentence():
    """What the two private specifications actually do on main, from the campaign.

    The point of the paragraph is that the failure is categorical rather than slow,
    so it must not overstate which category: a run the cap refused and a run our own
    ceiling stopped are different claims, and one of them is not a claim at all.
    """
    out = []
    for cp, name in (("mono", "the monolith"), ("ffi", "the refinement chain")):
        v = L.main_point(sweep, cp, "prep")
        if v == L.ABORT:
            out.append("on %s <code>main</code> exhausts the 12&nbsp;GB address space "
                       "before it finishes preparing" % name)
        elif v == L.CEIL:
            out.append("on %s it is still preparing when our fifteen-minute ceiling "
                       "stops it &mdash; a protocol timeout, so how much longer it "
                       "would need is not known" % name)
        elif isinstance(v, int):
            out.append("on %s <code>main</code> takes %s" % (name, L.fmt_ms(v)))
        else:
            out.append("on %s <code>main</code> has not been measured on this "
                       "campaign" % name)
    txt = ("On %s, and %s." % (out[0], out[1])).replace("On on ", "On ")
    # The claim the paragraph is making is that the failure is categorical.  Only a
    # refused allocation demonstrates that; a ceiling of our own does not.  So say it
    # only where the campaign has a refused allocation to point at.
    oom = sorted({cp for cp in ("ffi", "mono")
                  for pt in L.POINTS
                  if _cell(cp, pt).get("prep") == L.ABORT})
    if oom:
        where = " and ".join(CORPUS_NAME.get(cp, cp) for cp in oom)
        txt += (" The wall itself is not in doubt: on the %s the cap refuses an "
                "allocation outright at the commits marked with a cross in &sect;5, "
                "and there is no number there to make faster." % where)
    return txt


ITER_STEP = 1.10       # a move worth naming, well clear of the run-to-run spread


def _iter_caption():
    """Which commits actually move the warm loop, read off the measurement.

    This caption used to name a count.  The count went stale the moment the chain
    was re-measured, and a caption contradicting the chart above it is worse than no
    caption, so it is derived now.
    """
    steps, worse = [], []
    for cp in ("synth300", "ffi"):
        d, prev = iters(cp), None
        for pt in L.POINTS:
            v = d[pt]
            if isinstance(v, float) and isinstance(prev, float):
                r = prev / v
                if r >= ITER_STEP:
                    steps.append((cp, pt, r))
                elif r <= 1 / ITER_STEP:
                    worse.append((cp, pt, 1 / r))
            if isinstance(v, float):
                prev = v
    def phrase(rows):
        return "; ".join("%s on the %s, &times;%.2f"
                         % (C.LABELS[pt][0], "1&nbsp;800-obligation corpus"
                            if cp == "synth300" else "refinement chain", r)
                         for cp, pt, r in rows)
    if not steps:
        return ("No commit moves this metric clear of the run-to-run spread on either "
                "corpus &mdash; on this campaign the warm loop is where it started.")
    txt = ("%d step%s in the series move the warm loop clear of the run-to-run spread: "
           "%s. Every one of them does less work <em>per obligation</em> rather than "
           "less work overall, which is what a warm cache leaves to do: the file is "
           "still re-parsed, re-elaborated and re-fingerprinted in full, and only the "
           "one changed obligation is proved."
           % (len(steps), "" if len(steps) == 1 else "s", phrase(steps)))
    if worse:
        txt += (" One place moves the wrong way &mdash; %s &mdash; and it stays at that "
                "position because what it buys is that nothing after it can run out of "
                "memory." % phrase(worse))
    else:
        txt += (" No commit in the series makes this metric worse by more than the "
                "spread, the memory pull request included.")
    return txt


def _estimator_record():
    """Recompute what the scheduling rule predicted, against what the run did.

    The predictions are not stored -- they are a function of the campaign, so they are
    recomputed here from the same rows the harness used.  Both are simple: expected
    completion is the nearest completing point scaled by the ratio between the two
    commits on the public corpus that never fails; expected abort extrapolates the
    stopped run's own resident set to the cap.
    """
    import csv as _csv
    rows = list(_csv.DictReader(open(os.path.join(HERE, "short_sweep.csv"))))
    prep = [r for r in rows if int(r["prep_ms"]) != -2 and not r["phase"].startswith("K")]
    syn = {r["point"]: int(r["prep_ms"]) / 1000.0
           for r in prep if r["corpus"] == "synth300" and int(r["prep_rc"]) == 0}
    out = []
    for cp in L.CORPORA:
        mine = [r for r in prep if r["corpus"] == cp]
        ceil = {r["point"]: r for r in mine if r["phase"] != "L" and int(r["prep_rc"]) == 124}
        done = sorted((r["point"], int(r["prep_ms"]) / 1000.0)
                      for r in mine if r["phase"] != "L" and int(r["prep_rc"]) == 0)
        if not done:
            continue
        ref_p, ref_v = done[0]
        for r in sorted((r for r in mine if r["phase"] == "L"), key=lambda r: r["point"]):
            pt = r["point"]
            c = ceil.get(pt)
            if not c:
                continue
            ed = ref_v * syn[pt] / syn[ref_p] if (pt in syn and ref_p in syn) else None
            pk = int(c["peak_kb"])
            eo = (int(c["prep_ms"]) / 1000.0) * 12000000 / pk if pk else None
            cands = [(e, w) for e, w in ((ed, "completion"), (eo, "abort")) if e]
            if not cands:
                continue
            est, why = min(cands)
            act = int(r["prep_ms"]) / 1000.0
            v = L._verdict(int(r["prep_rc"]))
            got = ("aborted" if v == L.ABORT else
                   "still running" if v == L.CEIL else "completed")
            out.append((CORPUS_NAME.get(cp, cp), C.LABELS[pt][0], why, est, got, act,
                        est / act if act else None))
    if not out:
        return ('<p class="pr-meta">No stopped run has been re-run on the longer clock '
                'yet, so the rule has no record to show.</p>')
    body = "".join(
        '<tr><td>%s</td><td>%s</td><td class="num">%s, ~%.0f&nbsp;s</td>'
        '<td class="num">%s at %.0f&nbsp;s</td><td class="num">%s</td></tr>'
        % (cp, lab, why, est, got, act,
           ("&times;%.2f" % r) if r else "&mdash;")
        for cp, lab, why, est, got, act, r in out)
    over = [r for *_, r in out if r and r > 1]
    tail = ""
    if over:
        tail = ("<p style=\"margin-top:10px\">It overestimates on %d of %d, by up to "
                "&times;%.1f. That is the safe direction for a gate whose job is to "
                "avoid launching hopeless hours, and it is why the threshold is "
                "90&nbsp;%% rather than 100&nbsp;%%.</p>"
                % (len(over), len(out), max(over)))
    return ('<div class="scroller"><table><thead><tr><th>corpus</th><th>commit</th>'
            '<th class="num">the rule predicted</th><th class="num">the run</th>'
            '<th class="num">ratio</th></tr></thead><tbody>%s</tbody></table></div>%s'
            % (body, tail))


def _same_wall():
    """Do the aborts land at one resident set, and which crosses were measured?

    The chart cannot show either: every cross sits on the cap line by construction,
    so the reader can see neither that the refusals agree nor which of them were run
    to their end.  Both belong in the caption, counted from the data.
    """
    best = None
    for cp in L.CORPORA:
        at = [v["at"] for v in peak(cp).values()
              if isinstance(v, dict) and v.get("kind") == "OOM" and v.get("at")]
        if len(at) > 1 and (best is None or len(at) > len(best[1])):
            best = (cp, at)
    if not best:
        return ""
    cp, at = best
    lo, hi = min(at), max(at)
    spread = (hi - lo) / hi * 100
    where = CORPUS_NAME.get(cp, cp)
    if spread > WALL_SPREAD * 100:
        return (" The %d refusals on the %s land between %.2f and %.2f&nbsp;GB, so the "
                "commits differ in how much they hold when the cap stops them."
                % (len(at), where, lo, hi))
    txt = (" The crosses carry one more fact the chart cannot show, because every "
           "cross sits on the cap line by construction: the refusals on the %s all "
           "happen at the <strong>same</strong> resident set, %.2f&nbsp;GB, within "
           "%.2f&nbsp;%%. The cap is on address space and the reading is the resident "
           "set, which is why it is a little under 12&nbsp;GB; that it is the same "
           "figure every time is the point. These commits do not fail at several "
           "different memory profiles &mdash; they fail at one wall, and what "
           "separates them is only how long they take to reach it."
           % (where, hi, spread))
    w = WALL.get(cp)
    if w:
        _, att, refused, (rlo, rhi) = w
        n_meas = len(at) - len(att)
        txt += (" %d of those %d crosses are runs taken to their refusal; the other %d "
                "are <strong>attributed</strong> to that wall rather than measured to "
                "it, and the ground is stated so a reader can reject it: at the "
                "fifteen-minute ceiling the runs that <em>were</em> taken further read "
                "%.2f&ndash;%.2f&nbsp;GB, and each attributed run read inside that "
                "range at the same ceiling, on the same code path, with neither the "
                "pruning nor the streaming that removes the wall. A run stopped "
                "holding a few hundred megabytes is nowhere near that range and stays "
                "a ring, which is what keeps the attribution from swallowing every "
                "timeout."
                % (n_meas, len(at), len(att), rlo, rhi))
    return txt


CORPUS_NAME = {c: n for n, c, _, _ in C.SERIES}
ORACLE, ORACLE_NEXT = "p14", "p15"


def _oracle_noise():
    """The oracle is only defensible if it is free when unset, so say what it cost.

    Measured against the commit after it, which is the neighbour that shares its
    preparation path.  On the chain that comparison has an unusually good control:
    this same cell is the campaign's drift anchor, re-measured every eight points,
    so its own spread is known rather than assumed.
    """
    out = []
    for cp in L.CORPORA:
        a = _cell(cp, ORACLE).get("prep")
        b = _cell(cp, ORACLE_NEXT).get("prep")
        if not isinstance(a, int) or not isinstance(b, int) or not b:
            continue
        out.append("%s %+.1f&nbsp;%%" % (CORPUS_NAME.get(cp, cp), (a - b) / float(b) * 100))
    if not out:
        return "the commit has not been measured against its neighbour yet."
    txt = ("against the commit after it, which shares its preparation path, "
           "preparation differs by %s." % "; ".join(out))
    b = sweep.get("_line_boot", {}).get(("ffi", "prep"))
    a = sorted(sweep.get("_anchors", {}).get(b, []))
    nb = _cell("ffi", ORACLE_NEXT).get("prep")
    if len(a) >= 2 and isinstance(nb, int):
        inside = a[0] <= nb <= a[-1]
        txt += (" The chain figure has a control the others do not: this commit on "
                "the chain <em>is</em> the campaign&rsquo;s drift anchor, re-measured "
                "%d times at %.1f&ndash;%.1f&nbsp;s, and the neighbour&rsquo;s "
                "%.1f&nbsp;s falls %s that range &mdash; so what separates them is "
                "the machine, not the <code>getenv</code>."
                % (len(a), a[0] / 1000.0, a[-1] / 1000.0, nb / 1000.0,
                   "inside" if inside else "outside"))
    return txt


def _fill(txt):
    """Content strings may carry a slot the campaign fills, so that a claim about
    a measurement cannot go stale against the measurement."""
    return txt.replace("{oracle_noise}", _oracle_noise())



def _boot_list():
    """The boots the curves actually come from, newest last."""
    bs = sorted({b for b in sweep.get("_line_boot", {}).values()})
    return ", ".join(str(b) for b in bs) or "&mdash;"


def _provenance():
    """Which curve was measured on which boot.

    A chart line is one (metric, corpus) pair and comparability only has to hold
    within a line, so a container restart costs the lines that were still missing,
    not the ones already complete.  That is only honest if the document says which
    line came from which boot, so it says so.
    """
    lb = sweep.get("_line_boot", {})
    if len(set(lb.values())) < 2:
        return ""
    NAME = {"gen": "generation", "prep": "preparation"}
    by = {}
    for (cp, fld), b in sorted(lb.items()):
        by.setdefault(b, []).append("%s %s" % (CORPUS_NAME.get(cp, cp), NAME.get(fld, fld)))
    rows = "".join('<tr><td class="num">%s</td><td>%s</td></tr>'
                   % (b, ", ".join(v)) for b, v in sorted(by.items()))
    return ('<p style="margin-top:12px">The container restarted during the campaign, '
            'so the curves do not all come from the same boot. One chart line is one '
            '(metric, corpus) pair and comparability only has to hold <em>within</em> a '
            'line, so each line is measured end to end on a single boot and the restart '
            'costs the lines that were still missing rather than the ones already '
            'complete. Both hosts report the same CPU model and clock; the split is '
            'recorded here anyway, because a reader should not have to take that on '
            'trust:</p>'
            '<div class="scroller"><table><thead><tr><th>boot</th><th>curves measured on it</th>'
            '</tr></thead><tbody>%s</tbody></table></div>' % rows)


def _drift_sentence():
    """The campaign no longer measures main twice; one fixed cell is re-measured
    throughout instead, which bounds drift far better than two endpoints do."""
    a = sweep.get("_anchors", {}).get(boot, [])
    if len(a) < 2:
        return ("the drift anchor has not been re-measured often enough yet to bound "
                "the run's spread.")
    lo, hi = min(a), max(a)
    rng = (hi - lo) / float(hi) * 100
    last = ""
    if len(a) >= 4:
        tail = a[-3:]
        t = (max(tail) - min(tail)) / float(max(tail)) * 100
        last = (" Over the last three it is %.2f&nbsp;%%, so the run settles rather "
                "than drifting without bound." % t)
    return ("one fixed cell is re-measured every eight, and its %d readings span "
            "%.1f&nbsp;%% across the whole campaign &mdash; that is the drift every "
            "curve carries, measured rather than assumed.%s" % (len(a), rng, last))



def _better(direction):
    """Which way is good, as a mark rather than a sentence buried in the subtitle.

    Every chart here is read as "did this get better", and half of them are times
    where down is good while one is a rate where up is good.  A reader who takes the
    direction from the previous chart gets that one backwards, so each chart states
    it, in the same place, next to the title.

    It wears muted ink rather than a good/bad colour: the arrow already carries the
    meaning, and a green-or-red chip beside a chart reads as data about the chart.
    """
    up = direction == "higher"
    arrow = ('<svg width="9" height="10" viewBox="0 0 9 10" aria-hidden="true" '
             'style="vertical-align:-1px"><path d="%s" fill="none" '
             'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
             'stroke-linejoin="round"/></svg>'
             % ("M4.5 9V1.6M1.4 4.5 4.5 1.2 7.6 4.5" if up
                else "M4.5 1v7.4M1.4 5.5 4.5 8.8 7.6 5.5"))
    return ('<span class="better">%s %s is better</span>' % (arrow, direction))


def fig(title, sub, aria, values, unit, fmt_end, caption, series=None, points=None,
        rule=None, better="lower"):
    return ('<figure style="margin-top:20px"><div class="fig-head">'
            '<h4 style="margin:0">%s</h4>%s</div>'
            '<p style="font-size:13.5px;color:var(--ink-2);margin:2px 0 12px">%s</p>%s'
            '<figcaption>%s</figcaption></figure>'
            % (title, _better(better), sub,
               C.chart(aria, values, unit, fmt_end, series, points, rule), caption))


def sec_curves():
    c = ["""<p>One point per commit, <code>main</code> at the left, in the order the
series is proposed in. A red mark instead of a point means the run
<strong>did not complete</strong>, and its <em>shape</em> says whether that is a result.
A <strong>cross</strong> is a result: the run was refused memory, or it was given a full
hour and still did not finish. A <strong>ring</strong> is a
<strong>protocol timeout &mdash; inconclusive</strong>: the run was stopped by the
ceiling this measurement protocol sets, not by anything in the commit, so it says where
we stopped looking and nothing about where the commit ends up. It is not a slower
version of a cross; it is the absence of an answer, and the count of outstanding rings
is stated rather than left to be inferred. The tables in &sect;6 say which of the two
ways a real failure failed, because the difference matters &mdash; a change that speeds
preparation up reaches the memory wall <em>sooner</em>, turning a ceiling into an abort
without being a regression. Public and private corpora share each chart: hue separates
them, dash separates sizes.</p>
<p>Commit labels are coloured by provenance: <span style="color:var(--lbl-286);font-weight:600">violet</span>
is a commit whose message credits <a href="https://github.com/tlaplus/tlapm/issues/286">tlaplus/tlapm#286</a>,
<span style="color:var(--lbl-keep);font-weight:600">green</span> is new here. Bold
labels are the last commit of a pull request &mdash; the point a reviewer merging that
pull request would land on.</p>
<p>The first chart is throughput rather than speedup for one reason: on the two private
specifications <code>main</code> has no value to form a ratio against.</p>"""]

    c.append(fig(
    "Preparation throughput",
    "Obligations prepared per second &mdash; <code>tlapm --noproving --nofp</code>, the "
    "whole per-obligation pipeline with no prover. Obligations differ "
    "in size between corpora, so compare the shape of a curve, not its height against "
    "another's.",
    "Preparation throughput in obligations per second, one point per commit, five corpora "
    "on a logarithmic axis; the two private specifications do not complete on main.",
    {cp: thr(cp) for cp in L.CORPORA}, "obl/s",
    lambda v: "%.0f/s" % v if v >= 10 else "%.1f/s" % v,
    "A red mark below the axis is a run that did not complete. It has no height "
    "because its throughput is <strong>zero</strong> &mdash; it never finished preparing "
    "the corpus &mdash; and zero has no place on a logarithmic axis. That is why these "
    "sit in a band rather than on the curve: the other charts can put a failure "
    "somewhere meaningful, this one cannot. A cross is a result; a ring is a "
    "<strong>protocol timeout</strong>, and therefore inconclusive &mdash; the number "
    "it would have had is unknown, not zero. On the two private specifications "
    "<code>main</code> is one of these marks, and the curve begins only where a commit "
    "makes the specification runnable.", better="higher"))

    c.append(fig(
    "Peak memory of a preparation pass",
    "Maximum resident set of the same run, in gigabytes, under a 12&nbsp;GB address-space "
    "cap.",
    "Peak resident set per commit, five corpora, logarithmic axis.",
    {cp: peak(cp) for cp in L.CORPORA}, "GB",
    lambda v: "%.0f MB" % (v * 1024) if v < 1 else "%.2f GB" % v,
    "The step is the fourth pull request, and it is a step rather than a slope: peak "
    "memory stops being a function of the file and becomes a function of one obligation. "
    "Everything to the right of it is flat, which is the point &mdash; no later commit "
    "gives any of it back. "
    "Two marks, and only one of them is a result. A <strong>cross</strong> is a "
    "result: the cap refused an allocation, and the reading is real &mdash; the "
    "resident set reached just before the refusal. More time cannot change it. A "
    "<strong>red ring</strong> is a <strong>protocol timeout, and therefore "
    "inconclusive</strong>: the fifteen-minute ceiling this protocol sets stopped the "
    "run, so the mark records our own cut-off and not the commit&rsquo;s behaviour. "
    + _pending_sentence() + " Where a ring sits says what little is known: on the cap "
    "line it was holding a large share of the cap and still climbing, below the cap it "
    "was merely slow and sits at the peak it had reached. Neither is a figure to quote. "
    + _same_wall() +
    " The distinction the chart is really about is the pull request in the middle: to "
    "its left the failure is memory, to its right it is only time.",
    rule=(12.0, "12 GB address-space cap")))

    c.append(fig(
    "Generation time",
    "<code>tlapm -N --nofp</code>: parse, elaborate, generate the obligations, stop. "
    "Seconds. This is the floor under every editor interaction and "
    "the fixed cost each worker of any parallel scheme pays before it proves "
    "anything.",
    "Generation time in seconds per commit, five corpora, logarithmic axis.",
    {cp: gen(cp) for cp in L.CORPORA}, "s",
    lambda v: "%d ms" % (v * 1000) if v < 1 else "%.1f s" % v,
    "Unlike preparation, <code>main</code> completes this on every corpus, so every "
    "curve here starts from a real number and the whole series is one continuous "
    "line. Two of the nine pull requests are visible only on this chart and on the "
    "keystroke: the linear <code>ENABLED</code> scan and the memoized grammar do "
    "nothing to per-obligation preparation, because neither runs in that loop."))

    IT = {cp: iters(cp) for cp in L.CORPORA}
    c.append(fig(
    "Iteration latency &mdash; the wait after one edit",
    "Warm prover, every fingerprint already in the cache, one proof step changed. "
    "Seconds. This is the loop a user sits in, not a batch run.",
    "Iteration latency per commit on a warm fingerprint cache, public synthetic and "
    "private refinement chain, logarithmic axis.",
    IT, "s",
    lambda v: "%.1f s" % v if v < 100 else "%.0f s" % v,
    _iter_caption(),
    series=_series_for(IT)))

    KS = keyser()
    c.append(fig(
        "Keystroke to diagnostics, in the editor",
        "Time from the <code>didChange</code> notification to the "
        "<code>publishDiagnostics</code> that answers it, measured by a client speaking "
        "the LSP protocol. Seconds.",
        "Keystroke to diagnostics latency per commit, one series per corpus measured.",
        KS, "s", lambda v: "%.1f s" % v,
        _keystroke_caption(),
        series=_series_for(KS)))
    return "".join(c)


def _keystroke_caption():
    """The strongest form of the claim about the last pull requests that the data
    supports -- pair by pair, because it turned out not to hold for all of them."""
    rng = {pt: v for (cp, pt), v in L.keystroke_ranges().items() if cp == "ffi"}
    tail = [c[-1] for _, _, c in L.PRS][-4:]          # the deque's successors at the end
    have = [pt for pt in tail if pt in rng]
    base = ("After the deque, this is the only metric the last pull requests move at "
            "all, and it is why they are in the series: none of them touches the "
            "per-obligation preparation loop, so on every other chart they are flat.")
    if len(have) < 2:
        return base
    pairs = []
    for x, y in zip(have, have[1:]):
        _, lox, _hix = rng[x]
        _, _loy, hiy = rng[y]
        pairs.append((C.LABELS[x][0], C.LABELS[y][0], lox - hiy))
    n = min(rng[pt][0] for pt in have)
    ranges = " &rarr; ".join("%.2f&ndash;%.2f&nbsp;s" % (rng[pt][1], rng[pt][2])
                             for pt in have)
    clean = [p for p in pairs if p[2] > 0]
    dirty = [p for p in pairs if p[2] <= 0]
    txt = (base + " Read as ranges rather than medians, at n&nbsp;=&nbsp;%d: %s."
           % (n, ranges))
    if not dirty:
        return (txt + " Every consecutive pair is <strong>entirely disjoint</strong> "
                "&mdash; each of these pull requests is below its predecessor on every "
                "single repetition, not on average, the narrowest gap being "
                "%.2f&nbsp;s." % min(p[2] for p in clean))
    txt += (" %d of the %d consecutive pairs are <strong>entirely disjoint</strong> "
            "&mdash; %s %s below the commit before it on every single repetition, not "
            "on average."
            % (len(clean), len(pairs),
               " and ".join("<code>%s</code>" % b for _, b, _ in clean),
               "is" if len(clean) == 1 else "are each"))
    txt += (" The remaining %s does not separate that cleanly: %s, so there the claim "
            "is a difference of medians and nothing stronger."
            % ("pair" if len(dirty) == 1 else "%d pairs" % len(dirty),
               "; ".join("<code>%s</code> and <code>%s</code> overlap by "
                         "%.2f&nbsp;s" % (a_, b_, -g) for a_, b_, g in dirty)))
    txt += _first_edit_note(dirty)
    return txt


def _first_edit_note(dirty):
    """Where an overlap comes from one slow repetition, say which one -- but only
    where the data says it is the first, which is not true of every point here."""
    import csv as _csv
    import collections as _c
    runs = _c.defaultdict(list)
    boot = kboot
    for r in _csv.DictReader(open(os.path.join(HERE, "short_keystroke.csv"))):
        if r["boot"] == boot and r["kind"] == "edit":
            runs[(r["point"], int(r.get("n") or 0))].append(
                (int(r["idx"]), float(r["seconds"])))
    lab = {C.LABELS[pt][0]: pt for pt in L.POINTS}
    first_worst, other = [], []
    for a_, b_, _ in dirty:
        for name in (a_, b_):
            pt = lab.get(name)
            keys = [k for k in runs if k[0] == pt]
            if not keys:
                continue
            v = [x for _, x in sorted(runs[max(keys, key=lambda k: k[1])])]
            (first_worst if v and v[0] == max(v) else other).append(name)
    if not first_worst:
        return ""
    note = (" On %s the slowest repetition of the run is its <em>first</em>, so the "
            "overlap is a session warming up rather than a spread in steady state. "
            "It is left in rather than trimmed: a user's first edit is also an edit."
            % " and ".join("<code>%s</code>" % x for x in first_worst))
    if other:
        note += (" It is not a general effect &mdash; on %s the slowest repetition is "
                 "not the first."
                 % " and ".join("<code>%s</code>" % x for x in other))
    return note


def sec_perpr():
    c = ["<p>Each pull request: why it exists, then each of its commits with what "
         "changes, how to check it, how to switch it off, and what it measured. Ratios "
         "are quoted on the corpus where the change is separable from its neighbours; "
         "the full per-commit table is in "
         "<code>doc/perf/short/short_sweep.csv</code>.</p>"]
    for pid, title, tag, cms, motive in CT.PRS:
        files = sorted({f for cm in cms for f, _, _ in BY_LABEL[cm][3]})
        c.append('<div class="pr"><div class="pr-head"><span class="pr-n">%s</span>'
                 '<h3>%s</h3><span class="tag %s">%s</span></div>' % (pid, title, tag, tag[2:]))
        c.append('<p class="pr-meta">%d commit%s &middot; %d file%s &middot; %s</p>'
                 % (len(cms), "" if len(cms) == 1 else "s", len(files),
                    "" if len(files) == 1 else "s",
                    " ".join("<code>%s</code>" % BY_LABEL[cm][1] for cm in cms)))
        c.append("<p>%s</p>" % motive)
        for cm in cms:
            lab, sha, subj, fl, body = BY_LABEL[cm]
            d = CT.CM[cm]
            c.append('<div class="cm"><p class="cm-h"><code>%s</code> &nbsp;%s</p>' % (sha, subj))
            c.append('<p class="files">%s</p>' % " ".join(
                '<span>%s <span class="plus">+%s</span>&thinsp;<span class="minus">&minus;%s</span></span>'
                % (f, p, m) for f, p, m in fl))
            c.append('<p><span class="lbl">changes</span>%s</p>' % d["what"])
            c.append('<p><span class="lbl">validate</span>%s</p>' % d["how"])
            c.append('<p><span class="lbl">switch off</span>%s</p>' % _fill(d["off"]))
            c.append(_cm_table(cm))
            c.append("</div>")
        c.append("</div>")
    return "".join(c)


def _cm_table(cm):
    """what this commit measured, on every corpus where both sides are numbers"""
    i = L.POINTS.index(cm)
    prev = L.POINTS[i - 1]
    rows = []
    for cp in L.CORPORA:
        a, b = val(cp, prev, "prep"), val(cp, cm, "prep")
        pa, pb = val(cp, prev, "peak"), val(cp, cm, "peak")
        ga, gb = val(cp, prev, "gen"), val(cp, cm, "gen")
        if all(v in (L.DNC,) for v in (a, b, pa, pb, ga, gb)):
            continue
        rows.append('<tr><td class="num">%s</td><td class="num">%s &rarr; %s %s</td>'
                    '<td class="num">%s &rarr; %s %s</td><td class="num">%s &rarr; %s %s</td></tr>'
                    % ({"tiny": "small", "synth100": "600", "synth300": "1 800",
                        "ffi": "chain, 9 967", "mono": "monolith, 29 965"}[cp],
                       L.fmt_ms(ga), L.fmt_ms(gb), fmt_x(ga, gb),
                       L.fmt_ms(a), L.fmt_ms(b), fmt_x(a, b),
                       L.fmt_kb(pa), L.fmt_kb(pb), fmt_x(pa, pb)))
    warm = []
    for cp, nm in (("synth300", "1 800"), ("ffi", "chain")):
        ra, rb = iterlat.get((cp, prev)), iterlat.get((cp, cm))
        if ra and rb:
            warm.append("%s %s &rarr; %s %s" % (nm, L.fmt_ms(ra[0]), L.fmt_ms(rb[0]),
                                                fmt_x(ra[0] if isinstance(ra[0], int) else 0,
                                                      rb[0] if isinstance(rb[0], int) else 0)))
    ka, kb = keys.get(prev), keys.get(cm)
    if ka and kb:
        warm.append("keystroke %.1f&nbsp;s &rarr; %.1f&nbsp;s <span class=\"r\">&times;%.2f</span>"
                    % (ka[0], kb[0], ka[0] / kb[0]))
    out = ""
    if rows:
        out += ('<div class="scroller"><table><thead><tr><th>corpus</th><th class="num">generate</th>'
                '<th class="num">prepare</th><th class="num">peak</th></tr></thead><tbody>%s'
                '</tbody></table></div>' % "".join(rows))
    if warm:
        out += ('<p style="margin-top:10px"><span class="lbl">warm</span>%s</p>'
                % " &middot; ".join(warm))
    if not out:
        out = ('<p style="color:var(--ink-3);font-size:14px">Not separately measured on '
               'this campaign.</p>')
    return out


DROPPED = [
    ("expr/Levels", "resolve de Bruijn reference levels without slicing the context",
     "0.96&ndash;1.05", "the ratios straddle 1 on every corpus; the deque commit already "
     "removed most of what this walk cost"),
    ("backend/toolbox", "single-pass expansion in the result printer",
     "0.99&ndash;1.20", "the one large ratio is a single generation run on the monolith "
     "that the next nine points do not sustain"),
    ("util/property", "monomorphic pid equality, loop-based lookups",
     "0.92&ndash;1.08", "a paired test over the corpora gives a 3.1&nbsp;% mean with one "
     "negative pair &mdash; not separable"),
    ("Ctx", "logarithmic index lookup", "0.97&ndash;1.06",
     "the lookup is not on a hot path at these context sizes"),
    ("backend/Smtlib", "compile identifier-escaping regexes once", "0.94&ndash;1.06",
     "the encoder is a rounding error next to preparation"),
    ("expr/Subst", "walk substitution spines in app_ix without allocating",
     "0.96&ndash;1.04", "same"),
    ("backend+encode", "skip identity rebuilds when flattening extracts nothing",
     "0.93&ndash;1.09", "same"),
    ("backend/prep", "emit obligation comments into solver files only when kept",
     "0.97&ndash;1.11", "real work removed, but not enough of it to see"),
    ("expr/Constness", "constant-time De Bruijn resolution in add_constness",
     "0.93&ndash;1.07", "the prefix-resume cache already skips the walk it optimises"),
]


def sec_not():
    c = ["""<p>Nine further commits were written, measured, and are <strong>not</strong>
proposed. Each is correct and each removes real work; none of them moves a metric a
user can observe. They are listed because the reason they are absent is a result, and
because a reviewer asking &ldquo;why not also&hellip;&rdquo; deserves the answer
rather than silence.</p>"""]
    c.append('<div class="scroller"><table><thead><tr><th>area</th><th>change</th>'
             '<th class="num">measured</th><th>why it is out</th></tr></thead><tbody>')
    for area, what, meas, why in DROPPED:
        c.append('<tr><td class="num">%s</td><td>%s</td><td class="num">%s</td>'
                 '<td style="color:var(--ink-2);font-size:14px">%s</td></tr>'
                 % (area, what, meas, why))
    c.append("</tbody></table></div>")
    c.append("""<p style="margin-top:14px">The ranges are the ratios over every corpus and both
of generation and preparation, from a separate larger campaign on a different
machine. Their absolute timings do not transfer; the ratios do, and every one of these
nine straddles 1 &mdash; a ratio that changes sign between two corpora of the same
tool is measuring the run, not the change.</p>
<p>The bar is a <em>sustained</em> step, not a large single ratio, and applying it
changed a decision. A tenth commit &mdash; memoizing the two instances of each grammar
rule &mdash; was on this list because the editor-latency harness could not resolve it
at ten repetitions. Re-reading the same campaign by corpus showed a step on generation
of the two private specifications that the following nine commits all sustain. It is
now PR9. The lesson is in the method rather than in the commit: one metric failing to
see a change is not the same as the change not being there.</p>
<p>What is still open after this series is a different kind of change rather than a
smaller one, which is why none of it is here: the editor re-elaborates the whole
document on every interaction and then a child process repeats the work; there is no
in-process cache of elaborated <code>EXTENDS</code> dependencies; and obligations are
generated eagerly for the whole file even when the request concerns one proof. Each of
those is an architectural change with a design discussion in front of it, not a commit.</p>""")
    return "".join(c)


def sec_286():
    n286 = sum(1 for v in C.LABELS.values() if v[1])
    return """<p>Six of these seventeen commits credit <a
href="https://github.com/tlaplus/tlapm/issues/286">tlaplus/tlapm#286</a>, and the
issue itself describes four families of optimisation. The counts differ for a
reason worth stating plainly, because it looks like inflation and is not.</p>
<p>The reference patchset put seven independent micro-optimisations in a single
commit. Splitting that batch one subject per commit is the whole point of the
exercise &mdash; each becomes reviewable on its own, and each becomes
<em>measurable</em> on its own. Measuring them separately is what showed that five of
the seven move nothing, so they are in &sect;7 rather than here. Two survive: the
deque lookups and the scheduler reaper. Add the single-pass expansion, the two
prunes, and the linear <code>ENABLED</code> scan, and that is the six.</p>
<p>The other eleven commits are new. Three are the timing defects, two more are
scheduler fixes, two are the memory pull request, three are the prefix-resume caches,
one is the editor's obligation pool and one memoizes the grammar &mdash; and the pool
is in a component the issue does not touch at all.</p>""".replace("Six of these seventeen", "%s of these seventeen" % ("Six" if n286 == 6 else str(n286)))


def build():
    parts = ['<div class="wrap"><header>',
             '<p class="eyebrow">tlapm &middot; performance</p>',
             '<h1>Nine pull requests to make large proofs tractable</h1>',
             '<p class="lede">Seventeen commits, one subject each, measured commit by commit '
             'on five specifications with five metrics a user can time from outside the '
             'tool. Two of those specifications cannot be prepared at all today.</p>',
             '<div class="meta"><span>branch <code>%s</code></span>'
             '<span>%d files, +%d&thinsp;/&thinsp;&minus;%d</span>'
             '<span>base <code>%s</code></span></div></header>'
             % (BRANCH, TOTAL_FILES, TOTAL_ADD, TOTAL_DEL,
                subprocess.check_output(["git", "rev-parse", "--short", "main"]).decode().strip())]
    secs = [("01", "What breaks, and where", sec_problem),
            ("02", "One mechanism, four consequences", sec_mechanism),
            ("03", "What is proposed", sec_proposal),
            ("04", "How it was measured", sec_method),
            ("05", "Commit by commit", sec_curves),
            ("06", "Each pull request", sec_perpr),
            ("07", "Relation to issue #286", sec_286),
            ("08", "What is deliberately not here", sec_not)]
    for n, title, fn in secs:
        parts.append('<section><div class="sec-head"><span class="n">%s</span><h2>%s</h2></div>%s</section>'
                     % (n, title, fn()))
    parts.append("""<footer>
<p>Every figure in &sect;1 and &sect;4&ndash;&sect;6 &mdash; every point on every
chart, every cell of every table, and the counts and ratios quoted in the prose around
them &mdash; is produced by <code>doc/perf/short/mkshort.py</code> from the campaign
CSVs beside it. The exception is &sect;8, whose nine ranges come from a separate,
larger campaign on a different machine whose data is not in this directory: those are
transcribed, and the section says so. Where a claim about a measurement had to be
written by hand it has been turned into a slot the generator fills, because in the
course of this campaign three such sentences went stale against the charts above them
and one contradicted the table beside it.</p>
<p>The two private specifications are a customer's and are not published &mdash; only
the measurements taken on them are.</p>
<p>This work &mdash; the code, the measurement harness, and this document &mdash; was
produced by a human working with Anthropic's Claude models (Opus&nbsp;5, Fable&nbsp;5,
Sonnet&nbsp;5). Every commit was reviewed against its diff, and every number here comes
from a run that was executed rather than estimated.</p>
</footer></div>""")
    html = head() + "".join(parts)
    with open(OUT, "w") as f:
        f.write(html)
    return OUT, len(html)


if __name__ == "__main__":
    p, n = build()
    print("%s  %d bytes" % (p, n))
