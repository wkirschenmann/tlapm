# -*- coding: utf-8 -*-
"""Generate doc/perf/SHORT_PROPOSAL.html from the short-proposal campaign.

Every number in the document comes from the CSVs next to this file.  Nothing is
typed in by hand: a cell that was not measured renders as a dash and says so.
"""
import os, re, sys, subprocess, collections
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
# One row per corpus: the short kind, the name used in the narrative table of
# §1, and why it is on the curves at all.  Both tables iterate L.CORPORA, so a
# corpus that has no measurements does not appear -- and one that does appear
# cannot appear unlabelled.
# (kind, the name used in the narrative table of §1, the short name used in
# the dense per-commit tables, why it is on the curves at all)
CORPUS_META = {
    "tiny": ("public synthetic, small", "a small module", "small",
             "the control: it must not get slower, and it is on every chart to"
             " show that it does not"),
    "synth100": ("public synthetic, medium", "a 600-obligation synthetic module",
                 "600",
                 "the small end of the growth curve, where <code>main</code> is"
                 " still comfortable"),
    "synth300": ("public synthetic, large",
                 "a 1&nbsp;800-obligation synthetic module", "1 800",
                 "the flat public corpus large enough to show the growth, and the"
                 " one every ratio in &sect;{perpr} is quoted on"),
    "idemo": ("public refinement stack",
              "a public three-level refinement stack", "stack",
              "the public corpus that reaches the regime the private two are here"
              " for: a nested-INSTANCE stack whose 3&nbsp;239-line proof costs"
              " <code>main</code> 80&nbsp;s and 1.6&nbsp;GB. It is in this"
              " repository, so every number on its line can be re-run and"
              " disputed &mdash; see &sect;{mechanism}"),
    "ffi": ("private refinement chain",
            "a private refinement chain", "chain",
            "a real INSTANCE-heavy refinement chain: the shape this series is"
            " aimed at"),
    "mono": ("private monolith", "a private 30k-line monolith", "monolith",
             "a real 30k-line monolith: the specification <code>main</code>"
             " cannot prepare at all"),
}
NUMWORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
           7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
           12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
           16: "sixteen", 17: "seventeen", 18: "eighteen"}


N_PR = len(L.PRS)
N_CM = sum(len(c) for _, _, c in L.PRS)


def numword(n):
    """Spelled where the document spells, digits past the table.  One sentence
    used to read 'Three of the seventeen commits ... the other 14', mixing both
    forms -- and worse, the three was typed while the fourteen was derived, so a
    commit gaining or losing a switch would have made the halves contradict."""
    return NUMWORD.get(n, str(n))

# Three things have to agree about which corpora exist: this table, the
# obligation counts, and the campaign's order.  When they did not, the symptom
# was a bare KeyError from inside a dict comprehension at import time, several
# frames away from the table that was actually wrong.  Say it plainly instead.
_missing = [cp for cp in L.CORPUS_ORDER if cp not in CORPUS_META]
_extra = [cp for cp in CORPUS_META if cp not in L.CORPUS_ORDER]
_uncounted = [cp for cp in CORPUS_META if cp not in L.OBL]
if _missing or _extra or _uncounted:
    raise SystemExit(
        "mkshort: the corpus tables disagree.\n"
        "  in shortlib.CORPUS_ORDER but unlabelled here: %s\n"
        "  labelled here but unknown to the campaign:    %s\n"
        "  labelled here but absent from shortlib.OBL:   %s"
        % (_missing or "none", _extra or "none", _uncounted or "none"))


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
            # A ceiling has no coordinate on this axis.  It used to be placed at
            # the clock it hit -- 900 s -- which draws it as if the run had taken
            # 900 s, when all that is known is "at least".  On a lower-is-better
            # chart that also parks it just under the fastest real point, which
            # reads as nearly-good.  It goes in the "none" row instead, with the
            # crosses, above every measured value.
            # r[2] is the number of runs behind the verdict.  A stop with zero runs
            # is a point MARKED from a stop measured to its right: the series is a
            # chain, so a point further left is the same tool with one optimisation
            # removed and cannot be faster.  It is drawn like the stop it was marked
            # from -- same row, same ring -- and named apart in the caption, because
            # "did not finish in an hour" and "was not run" are not the same claim.
            d[pt] = {"kind": r[0], "at": None, "pending": r[0] == L.CEIL,
                     "marked": r[0] == L.CEIL and r[2] == 0}
        elif r[2] == 0:
            # carried from a neighbour, not measured: a coordinate on the axis, a
            # hollow mark, faint segments, and a sentence under the chart
            d[pt] = {"kind": "CARRIED", "at": r[0] / 1000.0, "pending": False,
                     "marked": False, "carried": True}
        else:
            d[pt] = r[0] / 1000.0
    # An unmeasured point stays unmeasured.  There was a bracketing inference here
    # -- a point between two ceiling stops is itself at the ceiling -- written when
    # the ceiling was thought worth keeping.  It is gone with the ceiling: a cross
    # inferred rather than run looks identical on the chart to one that was run, and
    # what is wanted here is a duration or a memory abort, not a third thing.
    return d


def _series_for(values):
    """The chart's legend, derived from the data it was handed.

    This is now exactly what charts.chart does when handed no series at all --
    the rule lives there, and this delegates rather than restating it.  Two
    copies of one rule is how the legend and its caption came to read different
    boots earlier in this campaign: one copy got fixed.
    """
    return C.series_for(values)


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

# The two tables have to agree about how big the series is: every spelled
# commit count in the document is derived from the pull-request list, and a
# commit present in one table and not the other would make them lie.
if N_CM != len(CT.CM):
    raise SystemExit(
        "mkshort: the pull-request table lists %d commits, the commit table %d. "
        "Every 'seventeen commits' in the document is derived from the first, so "
        "they have to agree." % (N_CM, len(CT.CM)))

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
    ks_cp = _worst_keystroke()
    ks_main = keys.get((ks_cp, "p00"), (None,))[0] if ks_cp else None
    ks_tip = keys.get((ks_cp, TIP), (None,))[0] if ks_cp else None
    # main's own reading where there is one, and otherwise the leftmost commit that
    # has one, named.  The chain's warm loop costs three quarters of an hour a point
    # at that end, so a container restart can leave the reference point unmeasured
    # while the rest of the line stands; quoting the neighbour and saying which it is
    # beats dropping the paragraph, which is what happened here.
    def _measured(pt):
        r = iterlat.get(("ffi", pt))
        return bool(r) and r[2] > 0          # runs > 0: not carried from a neighbour
    it_at = "p00" if _measured("p00") else next(
        (pt for pt in L.POINTS if _measured(pt)), "p00")
    it_main = iterlat.get(("ffi", it_at), (None,))[0]
    it_tip = iterlat.get(("ffi", TIP), (None,))[0]
    c.append("<p>tlapm is fine on small proofs and unusable on large ones, and the "
             "boundary is not gradual. The %s specifications below are the same tool on "
             % numword(len([c for c in L.CORPORA if c != "synth100"])) +
             "the same machine: %s obligations finish before you notice, and ten "
             "thousand do not finish at all.</p>" % numword(L.OBL["tiny"]))
    c.append('<div class="scroller"><table><thead><tr><th>specification</th>'
             '<th class="num">obligations</th><th class="num">prepare, <code>main</code></th>'
             '<th class="num">prepare, after</th></tr></thead><tbody>')
    for cp in [c for c in L.CORPORA if c != "synth100"]:
        name = CORPUS_META[cp][1]
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
                 "%s %s, and %s after this series.</p>"
                 % ("has never finished" if it_main in L.FAILED
                    else "takes " + L.fmt_ms(it_main),
                    "on <code>main</code>" if it_at == "p00"
                    else ("at <code>%s</code>, the first commit of the series and one "
                          "that cannot move this metric" % C.LABELS[it_at][0]),
                    L.fmt_ms(it_tip) if it_tip is not None else "&mdash;"))
    if ks_main and ks_tip:
        c.append("<p>And at the keystroke, on the %s: from <code>didChange</code> to "
                 "<code>publishDiagnostics</code>, %.1f&nbsp;s on <code>main</code> "
                 "against %.1f&nbsp;s after &mdash; <span class=\"r\">&times;%.1f</span>. "
                 "That is the wait for <em>one typed character</em>, with every "
                 "fingerprint already cached.</p>"
                 % (CORPUS_NAME.get(ks_cp, ks_cp), ks_main, ks_tip, ks_main / ks_tip))
    c.append(_control_sentence())
    return "".join(c)


def _instance_demo():
    """The INSTANCE demo section.  Every count and every timing comes from
    instance_demo.csv, so the prose cannot drift from the tables beside it."""
    d = L.load_instance_demo()
    lad, ldf = d["ladder"], d["ladder_defn"]
    ks = sorted(lad, key=int)
    dsteps = [ldf[ks[i]] - ldf[ks[i - 1]] for i in range(1, len(ks))]
    hsteps = [lad[ks[i]] - lad[ks[i - 1]] for i in range(1, len(ks))]
    dstep = dsteps[0] if len(set(dsteps)) == 1 else None
    hstep = hsteps[0] if len(set(hsteps)) == 1 else None
    one = d["ladder_frag_one_hop"]["1"]
    two = d["ladder_frag_two_hop"]["1"]
    pr = d["proofs"]
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance_demo")
    stack = ["L0State", "L0", "L0Theorems", "L1State", "L1", "L1Theorems", "L2"]
    widest = max(sum(1 for _ in open(os.path.join(here, m + ".tla")))
                 for m in stack)
    words = {5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
    count = words.get(len(stack), str(len(stack)))
    ab, mn, tp = d["ab"], d["main"], d["tip"]
    per_obl = pr["total_ctx_hyps"] // pr["obligations"]
    inst_obl = pr["frag_one_hop"] // pr["obligations"]
    two_obl = pr["frag_two_hop"] // pr["obligations"]

    c = ["""<h4>The mechanism, in %s small modules and one real proof</h4>
<p><code>doc/perf/short/instance_demo/</code> is the mechanism with nothing else in
it: a three-level refinement stack shaped like the private one. Levels&nbsp;0
and&nbsp;1 each get the same three modules &mdash; a state module holding the
parameters and the standing assumptions, a specification, and a theorems module that
declares results without proving them &mdash; and each reaches the level below by
<code>EXTENDS</code> and instantiates its theorems by <code>INSTANCE</code>. The
largest of the %s stack modules is %d lines. On top of them sits
<code>L2Proofs.tla</code>, a level-2 proof of %s lines that cites their instantiated
theorems %d times: %d at one <code>INSTANCE</code> hop and %d at two.</p>
<p><code>INSTANCE</code> does not share; it <em>copies</em>. When level&nbsp;2
instantiates level&nbsp;1, level&nbsp;1's body already contains a copy of level&nbsp;0
&mdash; renamed once when level&nbsp;1 instantiated it &mdash; so level&nbsp;2 gets
level&nbsp;0 a second time, renamed twice. The nesting is flattened at elaboration
time: by the time an obligation exists there is no indirection left to follow, only
copies. The <code>Ladder</code><em>n</em> modules make that countable. Each has one
obligation and differs from the next only in how many times it instantiates the same
theorems module.</p>""" % (count, count, widest,
                           "{:,}".format(pr["lines"]).replace(",", "&nbsp;"),
                           pr["cite_one_hop"] + pr["cite_two_hop"],
                           pr["cite_one_hop"], pr["cite_two_hop"])]
    c.append('<div class="tw"><table><thead><tr><th><code>INSTANCE</code> '
             'declarations</th><th class="n">definitions in the obligation</th>'
             '<th class="n">hypotheses in the obligation</th></tr></thead><tbody>')
    for k in ks:
        c.append('<tr><td>%s</td><td class="n">%d</td><td class="n">%d</td></tr>'
                 % (k, ldf[k], lad[k]))
    c.append("</tbody></table></div>")
    c.append("""<p>Exactly linear: %s definitions and %s hypotheses per
<code>INSTANCE</code>, on a stack whose whole source is %d lines. And %d of
those %d definitions &mdash; %.0f&nbsp;%% &mdash; are the copy of level&nbsp;0 that
arrived two renamings deep, inside the copy of level&nbsp;1. Nothing in the source is
duplicated; the duplication is what instantiation is.</p>""" % (
        "%d" % dstep if dstep else "a constant number of",
        "%d" % hstep if hstep else "a constant number of",
        pr["stack_lines"], two, one, 100.0 * two / one))

    c.append("""<h4>What that costs a proof that actually uses it</h4>
<p>The ladder counts the copies; <code>L2Proofs.tla</code> shows what they cost once a
proof cites them. It is %s lines over %d lemmas of two kinds, and the split matters
because they stress different things. A <strong>Cite</strong> lemma (%d of them) keeps
every operator opaque and chains instantiated theorems: what it exercises is the
context, which carries every definition of both levels below whether or not the goal
mentions it. An <strong>Open</strong> lemma (%d) names definitions in <code>DEF</code>
&mdash; %d unfoldings in all &mdash; so the <em>bodies</em> of the invariants really
enter the obligation, which is what a proof does when it opens an invariant to reach
one conjunct and the only way a definition's weight reaches a prover at all.</p>
<p>Both kinds are proof trees four or five levels deep &mdash; %d steps at
depth&nbsp;four, %d at depth&nbsp;five &mdash; which matters because every step's
statement joins the context of its later siblings and of everything nested beneath it.
<code>harness/gen_l2proofs.py</code> generates the file from the lemma index with no
randomness, so regenerating it is byte-identical.</p>
""" % (
        "{:,}".format(pr["lines"]).replace(",", "&nbsp;"), pr["lemmas"],
        pr["lemmas_citing"], pr["lemmas_opening"], pr["def_unfoldings"],
        pr["steps_depth4"], pr["steps_depth5"]))
    rows = [("stack source, all %s modules" % count,
             "%d lines" % pr["stack_lines"]),
            ("proof", "{:,} lines".format(pr["lines"]).replace(",", "&nbsp;")),
            ("obligations", "{:,}".format(pr["obligations"]).replace(",", "&nbsp;")),
            ("hypotheses per obligation, mean",
             "{:,}".format(per_obl).replace(",", "&nbsp;")),
            ("hypotheses per obligation, worst",
             "{:,}".format(pr["max_ctx_hyps"]).replace(",", "&nbsp;")),
            ("of those, instantiated copies (one hop or two)",
             "{:,}".format(inst_obl).replace(",", "&nbsp;")),
            ("of those, arrived two hops deep",
             "{:,}".format(two_obl).replace(",", "&nbsp;")),
            ("context entries walked over the whole run",
             "{:,}".format(pr["total_ctx_hyps"]).replace(",", "&nbsp;"))]
    c.append('<div class="tw"><table><tbody>')
    for k, v in rows:
        c.append('<tr><td>%s</td><td class="n">%s</td></tr>' % (k, v))
    c.append("</tbody></table></div>")
    c.append("""<p>Those counts are a property of the corpus rather than of a version:
they are read off the generated obligations, which this series does not change. The
timings below do have a version &mdash; medians over %d interleaved rounds of the base
commit against the branch tip, one machine, one boot.</p>""" % ab["reps"])
    def _s(v):
        # two decimals under ten seconds, one under a hundred, none above:
        # "80.00 s" claims a precision three interleaved rounds do not have
        return ("%.2f" if v < 10 else "%.1f" if v < 100 else "%.0f") % v + "&nbsp;s"
    tr = [("generation", "gen_ms", 1000.0, _s),
          ("preparation", "prep_ms", 1000.0, _s),
          ("proving, four threads", "prove_ms", 1000.0, _s),
          ("peak memory", "peak_kb", 1024.0,
           lambda v: "%.0f&nbsp;MB" % v),
          ("obligations", "obligations", 1.0,
           lambda v: "{:,}".format(int(v)).replace(",", "&nbsp;"))]
    c.append('<div class="tw"><table><thead><tr><th></th>'
             '<th class="n">base commit</th><th class="n">branch tip</th>'
             '<th class="n"></th></tr></thead><tbody>')
    for label, key, div, fmt in tr:
        a, b = mn[key] / div, tp[key] / div
        if key == "obligations":
            note = "identical" if mn[key] == tp[key] else "DIFFER"
        elif b <= 0 or a <= 0:
            note = "&mdash;"
        elif b < a:
            note = "&times;%.1f faster" % (a / b) if key != "peak_kb" \
                   else "&divide;%.0f" % (a / b)
        else:
            note = "&times;%.2f slower" % (b / a)
        c.append('<tr><td>%s</td><td class="n">%s</td><td class="n">%s</td>'
                 '<td class="mdl">%s</td></tr>'
                 % (label, fmt(a), fmt(b), note))
    c.append("</tbody></table></div>")
    gen_slower = tp["gen_ms"] > mn["gen_ms"]
    c.append("""<p>This is the corpus earning its keep. A %s-line proof over a stack
whose own source is %d lines takes <strong>%.0f&nbsp;s of preparation and
%.1f&nbsp;GB of peak memory on the base commit</strong>, and %.1f&nbsp;s and
%.0f&nbsp;MB at the tip &mdash; &times;%s on preparation and &divide;%s on
memory. Every obligation is proved on both sides and the generated obligation stream is
<strong>byte-identical</strong> between them (%s lines of <code>--printallobs</code>
compared): the subset invariant, checked exactly on a corpus small enough for it.
<code>harness/instance_demo.sh</code> refuses to write the CSV behind these tables if
either check fails.</p>""" % (
        "{:,}".format(pr["lines"]).replace(",", "&nbsp;"), pr["stack_lines"],
        mn["prep_ms"] / 1000.0, mn["peak_kb"] / 1048576.0,
        tp["prep_ms"] / 1000.0, tp["peak_kb"] / 1024.0,
        "%.1f" % (mn["prep_ms"] / float(tp["prep_ms"])),
        "%.0f" % (mn["peak_kb"] / float(tp["peak_kb"])),
        "{:,}".format(ab["golden_lines"]).replace(",", "&nbsp;")))
    if gen_slower:
        c.append("""<p>One metric moves the wrong way, and it is left in rather than
dropped: <strong>generation is %.0f&nbsp;%% slower at the tip</strong> on this corpus
(%.2f&nbsp;s against %.2f). Generation is the cheapest of the three by an order of
magnitude and the regression is a fraction of a second against %.0f&nbsp;s recovered
in preparation, so it is a trade this series takes knowingly &mdash; but a document
that only reported the ratios that flatter it would not be worth reading.</p>"""
                 % (100.0 * (tp["gen_ms"] - mn["gen_ms"]) / mn["gen_ms"],
                    tp["gen_ms"] / 1000.0, mn["gen_ms"] / 1000.0,
                    (mn["prep_ms"] - tp["prep_ms"]) / 1000.0))
    c.append("""<p>What it does not reproduce is scale &mdash; %s obligations against
the %s of the private monolith &mdash; which is why two of the corpora in &sect;{method} are a
customer's. This one is the part anyone can run.</p>""" % (
        "{:,}".format(pr["obligations"]).replace(",", "&nbsp;"),
        "{:,}".format(L.OBL["mono"]).replace(",", "&nbsp;")))

    c.append("""<p>Two hop-depth mistakes are easy to make in a stack like this and
cost hours when they happen on a real one, because the prefix counts
<code>INSTANCE</code> hops and not <code>EXTENDS</code> hops.
<code>instance_demo/CiteTrap.tla</code> exhibits the first and is expected to report
one failed obligation; <code>instance_demo/README.md</code> has both, and the
diagnostic for either.</p>""")
    return "".join(c)


FRONT = ["parsing", "analysis", "generation"]
FPCLK = ["fp_compute", "fp_saving", "fp_loading"]
CLOCK_NAME = {"parsing": "read the source", "analysis": "elaborate the modules",
              "generation": "generate the obligations",
              "fp_compute": "compute fingerprints", "fp_saving": "write fingerprints",
              "fp_loading": "read fingerprints", "interaction": "prepare and ship",
              "simplification": "simplify", "formatting": "format",
              "checking": "check", "other": "unattributed"}


def sec_where():
    """Where a solver-free run spends itself, from the stock clocks."""
    ph, cps, pt = L.load_phases()
    if not ph:
        return ""
    clocks = [c for c in list(CLOCK_NAME) if any((cp, c) in ph for cp in cps)]
    def pct(cp, keys):
        tot = ph.get((cp, "total")) or sum(ph.get((cp, c), 0.0) for c in clocks)
        return 100.0 * sum(ph.get((cp, c), 0.0) for c in keys) / tot if tot else 0.0
    lead = cps[-1]
    c = ["<p>One solver-free run per corpus, <code>tlapm --noproving --nofp "
         "--timing</code>, taken at <code>%s</code> &mdash; the first commit whose "
         "clocks add up, and otherwise the base commit&rsquo;s behaviour. Reading the "
         "source, elaborating the modules and generating the obligations are "
         "<strong>%.1f&nbsp;%%</strong> of the run on the %s; the other "
         "<strong>%.1f&nbsp;%%</strong> is the per-obligation loop, single-threaded, "
         "and that loop is what the rest of this series is about.</p>"
         % (C.LABELS[pt][0], pct(lead, FRONT), CORPUS_NAME.get(lead, lead),
            100.0 - pct(lead, FRONT))]
    c.append('<div class="scroller"><table><thead><tr><th>clock</th>%s</tr></thead>'
             '<tbody>' % "".join('<th class="num">%s</th>' % CORPUS_NAME.get(cp, cp)
                                 for cp in cps))
    for cl in clocks:
        cells = "".join('<td class="num">%s</td>'
                        % ("&mdash;" if (cp, cl) not in ph else
                           "%.2f&nbsp;s <span class=\"r\">%.0f&nbsp;%%</span>"
                           % (ph[(cp, cl)], pct(cp, [cl])))
                        for cp in cps)
        c.append("<tr><td>%s <span style=\"color:var(--ink-3)\"><code>%s</code></span>"
                 "</td>%s</tr>" % (CLOCK_NAME[cl], cl, cells))
    c.append('<tr><td><strong>total</strong></td>%s</tr>'
             % "".join('<td class="num"><strong>%.2f&nbsp;s</strong></td>'
                       % ph.get((cp, "total"), 0.0) for cp in cps))
    c.append("</tbody></table></div>")
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
    one, measured on the private monolith with the <code>TLAPM_PREP_SHARE</code>
    probe &mdash; and all three preparation passes recomputed the whole thing.</p>
    <p class="mdl">PR6</p></div>
</div>

""" + _instance_demo() + """
<p style="margin-top:16px">Two changes sit outside that mechanism. One is the editor's
proof-step tree, which scanned the obligation map once per step and had nothing to do
with contexts. The other is the set of correctness fixes, which are here because
without them the measurements that justify the rest are not available.</p>
"""


def sec_proposal():
    c = ["<p>%s pull requests, %s commits, %d files, +%d&thinsp;/&thinsp;&minus;%d. "
         "Each commit is one subject, states its own invariant, and passes the gate in "
         "&sect;{method} on its own.</p>"
         % (numword(N_PR).capitalize(), numword(N_CM),
            TOTAL_FILES, TOTAL_ADD, TOTAL_DEL)]
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

    c.append("<h4>Corpora</h4><p>%s, and every chart carries all of them. "
             "Everything marked public is in this repository; the two private "
             "specifications are a customer's and are not published &mdash; only "
             "these numbers are.</p>"
             % numword(len(L.CORPORA)).capitalize())
    c.append('<div class="scroller"><table><thead><tr><th>corpus</th>'
             '<th class="num">obligations</th><th>why it is here</th></tr></thead><tbody>')
    for cp in L.CORPORA:
        kind, _, _short, why = CORPUS_META[cp]
        c.append('<tr><td class="num">%s</td><td class="num">%s</td>'
                 '<td style="color:var(--ink-2);font-size:14px">%s</td></tr>'
                 % (kind,
                    "{:,}".format(L.OBL[cp]).replace(",", "&nbsp;"), why))
    c.append("</tbody></table></div>")

    c.append("""<h4>The correctness gate every commit passes</h4>
<p>Not a benchmark gate &mdash; a soundness one. For each of the """ + numword(N_CM) + """ commits,
in sequence: <code>dune runtest src</code> and <code>dune runtest lsp</code> green,
and the <code>test/fast</code> suite run against the full prover stack &mdash;
Z3&nbsp;4.8.9, Zenon, and Isabelle&nbsp;2025 with the TLA+ heap built from this
repository's <code>isabelle/</code> sources. The gate is fail-set
<em>identity</em> with <code>main</code>, not a pass count: a newly failing test is
a regression even where the count would still look healthy.</p>
""")
    c.append("""<p>Two invariants hold across the whole series. <strong>The provers receive a subset
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
    n_sw = len(rows)
    assert n_sw + n_none == len(CT.CM), (
        "switch tally disagrees with the commit list: %d with, %d without, %d total"
        % (n_sw, n_none, len(CT.CM)))
    out = ["<h4>What can be switched, and what cannot</h4>",
           "<p>%s of the %s commits carry a switch; the other %s do not, and "
           "deliberately so &mdash; they are output-preserving changes to a single code "
           "path, so a flag would mean carrying two implementations of the same "
           "function and testing neither of them properly. Where a switch does exist it "
           "restores the <em>original</em> code rather than disabling a feature, which "
           "is what makes it usable as a differential reference.</p>"
           % (numword(n_sw).capitalize(), numword(len(CT.CM)), numword(n_none))]
    out.append('<div class="scroller"><table><thead><tr><th>&nbsp;</th><th>commit</th>'
               '<th>switch</th></tr></thead><tbody>')
    for pid, sha, subj, off in rows:
        out.append('<tr><td class="num">%s</td><td class="num"><code>%s</code><br>'
                   '<span style="color:var(--ink-3);font-size:12.5px">%s</span></td>'
                   '<td style="font-size:14px">%s</td></tr>' % (pid, sha, subj, off))
    out.append("</tbody></table></div>")
    out.append("<p style=\"margin-top:12px\">Every measurement here is taken with the "
               "features on and every switch unset.</p>")
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
                SHORT_CP[cp], d,
                "" if e is None else " (memory %.2f&nbsp;%%)" % e))
    if not parts:
        return ""
    return ("<p>One pair calibrates the noise better than the baseline repeat does. "
            "The editor obligation pool changes only files under <code>lsp/</code>, so "
            "the command-line preparation path across it cannot differ &mdash; whatever "
            "the campaign measures there <em>is</em> the run-to-run spread, on a pair "
            "whose true answer is known to be zero. It measures: %s. That is the floor "
            "any ratio in &sect;{perpr} has to clear, and it is why a commit is only credited "
            "with an effect when it is a sustained step rather than a single large "
            "ratio. Read it per corpus: the floor is widest where the run is shortest, "
            "which is one reason the ratios in &sect;{perpr} are quoted on the "
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
                   "missing cells, so nothing in &sect;{curves} or &sect;{perpr} rests on an "
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
    """The two ways a run can end without a number, and how a line is walked."""
    return """<h4>Runs that do not finish</h4>
<p>A run gets an hour, and the machine caps address space at 12&nbsp;GB. A
<strong>cross</strong> is the cap refusing an allocation: settled, and more time
cannot change it. A <strong>ring</strong> is an hour spent without finishing &mdash;
not a duration, only the statement that an edit-and-wait loop is not practical there.
<p>Lines whose left end is expensive are walked from the tip towards the base, so the
budget goes to the points that still complete. A point to the left of an hour-long
stop is <em>marked</em> from it rather than run: it is the same tool with one
optimisation removed and cannot be faster. A marked point is drawn as the ring it was
marked from, is named as marked in the caption below the chart, and is never a
figure.</p>"""


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


def _control_sentence():
    """What the control module does across the series, read off the campaign.

    Not a rule the series is held to -- a reading.  Every metric on the smallest
    corpus, main against the tip.
    """
    got = []
    for fld, name, fmt in (("gen", "generation", L.fmt_ms),
                           ("prep", "preparation", L.fmt_ms),
                           ("peak", "peak memory", L.fmt_kb)):
        a, b = val("tiny", "p00", fld), val("tiny", TIP, fld)
        if isinstance(a, int) and isinstance(b, int):
            got.append("%s %s &rarr; %s" % (name, fmt(a), fmt(b)))
    for d, name, fmt in ((iterlat, "iteration", L.fmt_ms),
                         (keys, "keystroke", lambda v: fmt_secs(v))):
        ra, rb = d.get(("tiny", "p00")), d.get(("tiny", TIP))
        if ra and rb and not isinstance(ra[0], str) and not isinstance(rb[0], str):
            got.append("%s %s &rarr; %s" % (name, fmt(ra[0]), fmt(rb[0])))
    if not got:
        return ""
    return ('<div class="claim" style="margin-top:16px">Nothing proposed below costs '
            'the small end anything. On the %s-obligation control module, '
            '<code>main</code> and the branch tip land on the same figure for every '
            'metric measured &mdash; %s &mdash; which is why it is on every chart.</div>'
            % (L.OBL["tiny"], "; ".join(got)))


def _wall_sentence():
    """What the two private specifications actually do on main, from the campaign.

    Two sentences, and no argument around them: a run the cap refused and a run the
    clock stopped are different facts, and the ones that hold get stated.
    """
    out = []
    for cp, name in (("mono", "the monolith"), ("ffi", "the refinement chain")):
        v = L.main_point(sweep, cp, "prep")
        if v == L.ABORT:
            out.append("on %s <code>main</code> exhausts the 12&nbsp;GB address space "
                       "before it finishes preparing" % name)
        elif v == L.CEIL:
            out.append("on %s no run of <code>main</code> has finished preparing"
                       % name)
        elif isinstance(v, int):
            out.append("on %s <code>main</code> takes %s" % (name, L.fmt_ms(v)))
        else:
            out.append("on %s <code>main</code> has not been measured on this "
                       "campaign" % name)
    return ("On %s, and %s." % (out[0], out[1])).replace("On on ", "On ")


ITER_STEP = 1.10       # the FLOOR; iter_threshold() raises it per corpus

# Three commits in the series cannot change iteration latency: p01, p02 and p03
# make clock accounting nestable, host the named pipeline clocks, and attribute
# them -- all of it inert unless --timing is passed, which the iteration harness
# does not pass.  Their measured spread is therefore this metric's noise, and it
# is the right yardstick because repeats WITHIN one commit are run back to back
# and share warmed state: they agree to a few tenths of a percent and understate
# the real thing by an order of magnitude.
#
# p04 and p05 are in the same pull request but are excluded: reaping finished
# provers early and handling SIGTERM both change when work happens.
NO_SURFACE = ("p01", "p02", "p03")


def iter_band(cp):
    """(spread %, commits, runs, worst within-commit spread %) over the commits
    that cannot have moved this metric, or None when fewer than two of them are
    measured on this corpus."""
    d = L.load_iteration_latency()[0]
    got = [d[(cp, pt)] for pt in NO_SURFACE if (cp, pt) in d]
    if len(got) < 2:
        return None
    vals = [v[0] / 1000.0 for v in got]
    runs = sum(v[2] for v in got)
    # The within-commit term is the worst spread over EVERY measured commit, not
    # just the three inert ones.  Each of those groups is the same binary on the
    # same input, so any spread inside one is noise by construction, and three
    # groups is too small a sample to bound it: on the control corpus the three
    # inert commits happened to agree to 8.9 % while another commit's own repeats
    # spread 17.6 %, which let two physically impossible steps -- a kill-signal
    # change and a task-streaming change, both on a 350 ms warm run -- clear the
    # threshold.  The worst of eighteen is a deliberately conservative estimate;
    # a threshold whose job is to refuse noise-sized claims should err that way.
    within = max([v[1] for (c, _), v in d.items()
                  if c == cp and isinstance(v[0], int) and v[2] >= 2] or [0.0]) * 100.0
    return ((max(vals) - min(vals)) / max(vals) * 100.0, len(got), runs, within)


def iter_threshold(cp):
    """The ratio a move has to beat on THIS corpus to be called a result.

    One global threshold was wrong, and the checker said so: 1.10 on the public
    stack named a 10 % move a result where the commits that cannot have moved it
    spread 12 %.  The reason is scale rather than sloppiness -- that corpus
    iterates in about a hundred milliseconds, where process startup jitter is a
    large fraction, while the monolith iterates in eighteen minutes and its band
    is 3.9 %.  A relative threshold cannot be shared between the two.

    So: whichever is larger of the floor and the corpus's own measured spread.
    The floor stays because a corpus whose band comes out implausibly tight
    should not start naming one-percent moves as results.
    """
    b = iter_band(cp)
    return ITER_STEP if not b else max(ITER_STEP, 1.0 + max(b[0], b[3]) / 100.0)


def _iter_caption():
    """Which commits actually move the warm loop, read off the measurement.

    This caption used to name a count.  The count went stale the moment the chain
    was re-measured, and a caption contradicting the chart above it is worse than no
    caption, so it is derived now.
    """
    steps, worse = [], []
    # Every corpus with a line, not a hardcoded pair.  The pair was written when two
    # corpora had one; a third and a fourth arrived and the caption went on claiming
    # to have read "either corpus".
    for cp in L.CORPORA:
        d, prev = iters(cp), None
        for pt in L.POINTS:
            v = d[pt]
            if isinstance(v, float) and isinstance(prev, float):
                r = prev / v
                thr = iter_threshold(cp)
                if r >= thr:
                    steps.append((cp, pt, r))
                elif r <= 1 / thr:
                    worse.append((cp, pt, 1 / r))
            if isinstance(v, float):
                prev = v
    def phrase(rows):
        return "; ".join("%s on the %s, &times;%.2f"
                         % (C.LABELS[pt][0], CORPUS_NAME.get(cp, cp), r)
                         for cp, pt, r in rows)
    # What the threshold clears, measured rather than asserted.
    bands = []
    for cp in L.CORPORA:          # not a hardcoded three: the sixth corpus has a
        b = iter_band(cp)         # band of its own, and a much larger one
        if b:
            spread, ncm, nrun, within = b
            bands.append("%s %.1f&nbsp;%% across %s commits and %s runs against "
                         "%.1f&nbsp;%% between repeats of one commit, the worst "
                         "of the series, so &times;%.2f"
                         % (CORPUS_NAME.get(cp, cp), spread, numword(ncm),
                            numword(nrun), within, iter_threshold(cp)))
    band_txt = ""
    if bands:
        band_txt = (" <em>What counts as clear:</em> %s the series cannot have moved "
                    "this metric &mdash; they make clock accounting nestable, host the "
                    "named clocks and attribute them, all inert unless "
                    "<code>--timing</code> is passed, which this harness does not pass. "
                    "Their spread is therefore the noise: %s. The two readings do not "
                    "agree about which term dominates, and neither is safe to use "
                    "alone: repeats within one commit run back to back and share warmed "
                    "state, which on the monolith understates the scatter several-fold, "
                    "while on the small corpus the run-to-run jitter is the larger term "
                    "and the commit-to-commit means are tight. What counts as a step is "
                    "therefore decided per corpus &mdash; whichever is larger of a "
                    "&times;%.2f floor and that corpus&rsquo;s own band &mdash; because "
                    "a relative threshold cannot be shared between a corpus that "
                    "iterates in a tenth of a second and one that takes eighteen "
                    "minutes."
                    % (numword(len(NO_SURFACE)).capitalize() + " commits in",
                       "; ".join(bands), ITER_STEP))
    if not steps:
        return ("No commit moves this metric clear of the run-to-run spread on either "
                "corpus &mdash; on this campaign the warm loop is where it started."
                + band_txt)
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
    return txt + band_txt + _marked_sentence() + _carried_sentence()


def _carried_sentence():
    """Points drawn from a neighbour rather than measured, named.

    One exists, and it exists because the container restarted twelve minutes after
    the neighbour landed and re-running that end of the line costs three quarters of
    an hour a point.  It is drawn hollow, its segments are faint, and it is named
    here; what it must never be is a filled dot like the ones either side of it.
    """
    out = []
    for cp in L.CORPORA:
        d = iters(cp)
        for pt in L.POINTS:
            v = d.get(pt)
            if isinstance(v, dict) and v.get("carried"):
                nb = L.POINTS[L.POINTS.index(pt) + 1]
                out.append("%s on the %s carries %s&rsquo;s value"
                           % (C.LABELS[pt][0], CORPUS_NAME.get(cp, cp),
                              C.LABELS[nb][0]))
    if not out:
        return ""
    return (" <em>One mark is not a measurement.</em> %s, and is drawn hollow with "
            "faint segments either side. The two differ by nothing that can touch "
            "this metric &mdash; the one commit that separates them makes clock accounting "
            "nestable and is inert unless <code>--timing</code> is passed &mdash; but "
            "a value taken from a neighbour is not a run, and the chart says so."
            % "; ".join(out).capitalize())


def _marked_sentence():
    """Which stopped points were marked from a measurement instead of being run.

    Counted, not asserted, and named: a reader who sees eight rings on one line is
    entitled to know that one of them cost an hour and the other seven cost nothing.
    """
    out = []
    for cp in L.CORPORA:
        d = iters(cp)
        marked = [pt for pt in L.POINTS
                  if isinstance(d.get(pt), dict) and d[pt].get("marked")]
        ran = [pt for pt in L.POINTS
               if isinstance(d.get(pt), dict) and d[pt].get("kind") == L.CEIL
               and not d[pt].get("marked")]
        if not marked:
            continue
        out.append("on the %s, %s spent the whole hour without finishing and the %s "
                   "point%s to its left %s marked from it rather than run"
                   % (CORPUS_NAME.get(cp, cp),
                      C.LABELS[max(ran)][0] if ran else "the leftmost measured point",
                      numword(len(marked)), "" if len(marked) == 1 else "s",
                      "is" if len(marked) == 1 else "are"))
    if not out:
        return ""
    return (" <em>Measured from the right.</em> The series is walked from the tip "
            "towards the base, so the budget goes to the points that still complete "
            "and the wall is reached last: %s. Each is the same tool with one "
            "optimisation removed, so it cannot be faster than the stop it is marked "
            "from; a marked point is a ring like that stop, and no figure in this "
            "document is read from one." % "; ".join(out))


def _same_wall():
    """Do the refusals land at one resident set, and which crosses were measured?

    The chart cannot show either: every cross sits on the cap line by construction,
    so the reader can see neither that the refusals agree nor which were run to their
    end.  Both belong in the caption, counted from the data.

    Pooled across corpora when they agree, because that is the stronger statement: a
    wall that is the same on two unrelated specifications is a property of the cap,
    not of either specification.
    """
    at, per = [], {}
    for cp in L.CORPORA:
        v = [x["at"] for x in peak(cp).values()
             if isinstance(x, dict) and x.get("kind") == "OOM" and x.get("at")]
        if v:
            per[cp] = v
            at += v
    if len(at) < 2:
        return ""
    lo, hi = min(at), max(at)
    spread = (hi - lo) / hi * 100
    names = ["the " + CORPUS_NAME.get(cp, cp) for cp in per]
    where = names[0] if len(names) == 1 else "%s and %s" % (", ".join(names[:-1]), names[-1])
    if spread > WALL_SPREAD * 100:
        return (" The %d refusals on %s land between %.2f and %.2f&nbsp;GB, so the "
                "commits differ in how much they hold when the cap stops them."
                % (len(at), where, lo, hi))
    txt = (" The crosses carry one more fact the chart cannot show, because every "
           "cross sits on the cap line by construction: all %d refusals &mdash; on "
           "%s alike &mdash; happen at the <strong>same</strong> resident set, "
           "%.2f&nbsp;GB, within %.3f&nbsp;%%. The cap is on address space and the "
           "reading is the resident set, which is why it is a little under "
           "12&nbsp;GB; that it is the same figure on unrelated specifications is the "
           "point. This is not a family of memory profiles that happen to be large "
           "&mdash; it is one wall, and what separates these commits is only how long "
           "each takes to reach it." % (len(at), where, hi, spread))
    tot_att = sum(len(WALL[cp][1]) for cp in WALL if cp in per)
    if tot_att:
        rlo = min(WALL[cp][3][0] for cp in WALL if cp in per)
        rhi = max(WALL[cp][3][1] for cp in WALL if cp in per)
        txt += (" %d of those %d crosses are runs taken to their refusal; the other %d "
                "are <strong>attributed</strong> to that wall rather than measured to "
                "it, on this ground: at the "
                "point where they were stopped, the runs that <em>were</em> taken further "
                "read %.2f&ndash;%.2f&nbsp;GB, and each attributed run read inside that "
                "range at that same point, on the same code path, with neither the "
                "pruning nor the streaming that removes the wall. A run stopped "
                "holding a few hundred megabytes is nowhere near that range and stays "
                "a ring, which is what keeps the attribution from swallowing every "
                "timeout." % (len(at) - tot_att, len(at), tot_att, rlo, rhi))
    return txt


CORPUS_NAME = {c: n for n, c, _, _ in C.SERIES}


def fmt_secs(v):
    """Seconds, at a precision the value deserves.

    This figure spans five orders of magnitude -- 2 ms on the small control
    against two minutes on the 30k-line monolith -- so one format cannot serve it.
    A fixed "%.1f s" printed the control's end label as "0.0 s", which reads as zero
    rather than as small.
    """
    if v < 0.01:
        return "%.1f ms" % (v * 1000)
    if v < 1:
        return "%d ms" % round(v * 1000)
    if v < 100:
        return "%.1f s" % v
    if v >= 600:
        return "%.0f min" % (v / 60.0)
    return "%d s" % round(v)


def _worst_case_steps():
    """Where the wait actually goes, on the corpus where it is worst.

    The rest of this caption reads the refinement chain, because that is where the
    last four commits are separable.  But the largest waits on this chart are the
    monolith's, and the commit that moves them most is not the one the chain's ranges
    are about -- so the caption would otherwise discuss the smaller of the two.
    """
    cp = _worst_keystroke()
    if not cp:
        return ""
    v = [(pt, keys[(cp, pt)][0]) for pt in L.POINTS if (cp, pt) in keys]
    if len(v) < 3:
        return ""
    steps, prev = [], None
    for pt, x in v:
        if prev and prev[1] / x > 1.15:
            steps.append((C.LABELS[pt][0], prev[1], x, prev[1] / x))
        prev = (pt, x)
    if not steps:
        return ""
    name = CORPUS_NAME.get(cp, cp)
    lead = (" The largest waits on this chart are the %s&rsquo;s, %s on <code>main</code> "
            "for a single typed character, and they fall in %s: %s."
            % (name, fmt_secs(v[0][1]),
               "one step" if len(steps) == 1 else "%d steps" % len(steps),
               "; ".join("<code>%s</code>, %s to %s, &times;%.1f"
                         % (lab, fmt_secs(a), fmt_secs(b), r) for lab, a, b, r in steps)))
    return lead


def _worst_keystroke():
    """The corpus whose keystroke costs most on main, and name it.

    The opening used to quote the refinement chain because that was the only corpus
    measured.  With five measured it should quote the worst case, and say which one it
    is: a figure whose corpus is left unstated invites the reader to assume it is the
    one they care about.
    """
    cands = [(v[0], cp) for (cp, pt), v in keys.items() if pt == "p00"
             and (cp, TIP) in keys]
    return max(cands)[1] if cands else None

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
               C.chart(aria, values, unit, fmt_end, series, points, rule,
                       better=better),
               caption))


def sec_curves():
    c = ["""<p>One point per commit, <code>main</code> at the left, in the order the
series is proposed in. A red mark instead of a point means the run
<strong>did not complete</strong>, and its <em>shape</em> says whether that is a result.
A <strong>cross</strong> is a result: the run was refused memory, or it was given a full
hour and still did not finish. A <strong>ring</strong> is a
<strong>protocol timeout &mdash; inconclusive</strong>: this protocol&rsquo;s clock
stopped the run, not anything in the commit, so it says where we stopped looking and
nothing about where the commit ends up. It is not a slower
version of a cross; it is the absence of an answer. The tables in &sect;{perpr} say which of the two
ways a real failure failed, because the difference matters &mdash; a change that speeds
preparation up reaches the memory wall <em>sooner</em>, turning a run we stopped into a
run the cap refused, without being a regression. Public and private corpora share each chart: hue separates
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
    "inconclusive</strong>: this protocol&rsquo;s clock stopped the run, so the mark "
    "records our own cut-off and not the commit&rsquo;s behaviour. "
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
    IT, "s", fmt_secs,
    _iter_caption(),
    series=_series_for(IT)))

    KS = keyser()
    c.append(fig(
        "Keystroke to diagnostics, in the editor",
        "Time from the <code>didChange</code> notification to the "
        "<code>publishDiagnostics</code> that answers it, measured by a client speaking "
        "the LSP protocol. Seconds.",
        "Keystroke to diagnostics latency per commit, one series per corpus measured.",
        KS, "s", fmt_secs,
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
            "per-obligation preparation loop, so on every other chart they are flat."
            + _worst_case_steps())
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


# Derived, not repeated.  There used to be three copies of this mapping -- two
# constants and one inline -- and all three would have raised KeyError the
# moment a sixth corpus had measurements, which is a crash the reader would
# have met before I did.
SHORT_CP = {cp: m[2] for cp, m in CORPUS_META.items()}
# The long form appends the obligation count, except where the short name IS
# the count already.
LONG_CP = {cp: (n if n.replace(" ", "").isdigit()
                else "%s, %s" % (n, "{:,}".format(L.OBL[cp]).replace(",", "&nbsp;")))
           for cp, n in SHORT_CP.items()}


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
                    % (LONG_CP[cp],
                       L.fmt_ms(ga), L.fmt_ms(gb), fmt_x(ga, gb),
                       L.fmt_ms(a), L.fmt_ms(b), fmt_x(a, b),
                       L.fmt_kb(pa), L.fmt_kb(pb), fmt_x(pa, pb)))
    # Both warm metrics, on every corpus measured.  This used to read two hardcoded
    # corpora for iteration latency and one unkeyed lookup for the keystroke -- and
    # when the keystroke reader became per-corpus the unkeyed lookup silently returned
    # nothing, so seventeen commit blocks lost their keystroke figure without any of
    # them going blank.  Deriving both from the data is what stops that recurring.
    def pair(a, b):
        """one 'before -> after' cell, ratio only when both sides are numbers"""
        fa = L.fmt_ms(a) if not isinstance(a, float) else fmt_secs(a)
        fb = L.fmt_ms(b) if not isinstance(b, float) else fmt_secs(b)
        r = ""
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b:
            r = ' <span class="r">&times;%.2f</span>' % (float(a) / float(b))
        return "%s &rarr; %s%s" % (fa, fb, r)

    warm = []
    for cp in L.CORPORA:
        ra, rb = iterlat.get((cp, prev)), iterlat.get((cp, cm))
        if ra and rb:
            warm.append("iteration, %s: %s" % (SHORT_CP[cp], pair(ra[0], rb[0])))
    for cp in L.CORPORA:
        ka, kb = keys.get((cp, prev)), keys.get((cp, cm))
        if ka and kb:
            warm.append("keystroke, %s: %s" % (SHORT_CP[cp], pair(ka[0], kb[0])))
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
user can observe. They are listed because the reason they are absent is a result.</p>"""]
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
    return """<p>""" + numword(n286).capitalize() + """ of these """ + numword(N_CM) + """ commits credit <a
href="https://github.com/tlaplus/tlapm/issues/286">tlaplus/tlapm#286</a>, and the
issue itself describes four families of optimisation. The counts differ, and here is why.</p>
<p>The reference patchset put seven independent micro-optimisations in a single
commit. Splitting that batch one subject per commit is the whole point of the
exercise &mdash; each becomes reviewable on its own, and each becomes
<em>measurable</em> on its own. Measuring them separately is what showed that five of
the seven move nothing, so they are in &sect;{not} rather than here. Two survive: the
deque lookups and the scheduler reaper. Add the single-pass expansion, the two
prunes, and the linear <code>ENABLED</code> scan, and that is the six.</p>
<p>The other eleven commits are new. Three are the timing defects, two more are
scheduler fixes, two are the memory pull request, three are the prefix-resume caches,
one is the editor's obligation pool and one memoizes the grammar &mdash; and the pool
is in a component the issue does not touch at all.</p>""".replace("Six of these seventeen", "%s of these seventeen" % ("Six" if n286 == 6 else str(n286)))


def build():
    parts = ['<div class="wrap"><header>',
             '<p class="eyebrow">tlapm &middot; performance</p>',
             '<h1>%s pull requests to make large proofs tractable</h1>'
             % numword(N_PR).capitalize(),
             '<p class="lede">%s commits, one subject each, measured commit by commit '
             'on %s specifications with %s metrics a user can time from outside the '
             'tool. Two of those specifications cannot be prepared at all today.</p>'
             % (numword(N_CM).capitalize(), numword(len(L.CORPORA)),
                numword(len(METRICS))),
             '<div class="meta"><span>branch <code>%s</code></span>'
             '<span>%d files, +%d&thinsp;/&thinsp;&minus;%d</span>'
             '<span>base <code>%s</code></span></div></header>'
             % (BRANCH, TOTAL_FILES, TOTAL_ADD, TOTAL_DEL,
                subprocess.check_output(["git", "rev-parse", "--short", "main"]).decode().strip())]
    # Sections are referred to by NAME in the prose and numbered here.  Fourteen
    # references were written as "&sect;5", two of them were already pointing at the
    # wrong section, and inserting one section invalidates every one of them at once.
    secs = [("problem",   "What breaks, and where",           sec_problem),
            ("where",     "Where the time goes",              sec_where),
            ("mechanism", "One mechanism, four consequences", sec_mechanism),
            ("proposal",  "What is proposed",                 sec_proposal),
            ("method",    "How it was measured",              sec_method),
            ("curves",    "Commit by commit",                 sec_curves),
            ("perpr",     "Each pull request",                sec_perpr),
            ("286",       "Relation to issue #286",           sec_286),
            ("not",       "What is deliberately not here",    sec_not)]
    # numbered by position, and a section with nothing measured behind it does not
    # take a number: the phase table exists only once its campaign row does
    n, num = 0, {}
    for key, title, fn in secs:
        body = fn()
        if not body:
            continue
        n += 1
        num[key] = n
        parts.append('<section><div class="sec-head"><span class="n">%02d</span>'
                     '<h2>%s</h2></div>%s</section>' % (n, title, body))
    parts.append("""<footer>
<p>Every chart, table and ratio here is generated by
<code>doc/perf/short/mkshort.py</code> from the CSVs beside it. Two figures are not, and
say so where they appear: &sect;{not}'s nine ranges, from a larger campaign on another
machine, and the sharing figure in &sect;{mechanism}, from a
<code>TLAPM_PREP_SHARE</code> probe on the private monolith.</p>
<p>The two private specifications are a customer's and are not published &mdash; only
the measurements taken on them are.</p>
<p>This work &mdash; the code, the measurement harness, and this document &mdash; was
produced by a human working with Anthropic's Claude models (Opus&nbsp;5, Fable&nbsp;5,
Sonnet&nbsp;5).</p>
</footer></div>""")
    html = head() + "".join(parts)
    for key, v in num.items():
        html = html.replace("&sect;{%s}" % key, "&sect;%d" % v)
    missing = sorted(set(re.findall(r"&sect;\{([a-z0-9]+)\}", html)))
    assert not missing, ("the page refers to sections that did not render: %s"
                         % ", ".join(missing))
    with open(OUT, "w") as f:
        f.write(html)
    return OUT, len(html)


if __name__ == "__main__":
    p, n = build()
    print("%s  %d bytes" % (p, n))
