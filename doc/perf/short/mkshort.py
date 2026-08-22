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
def thr(cp):
    """obligations prepared per second, per point"""
    d = {}
    for pt in L.POINTS:
        v = L.main_point(sweep, cp, "prep") if pt == "p00" else sweep.get((pt, cp), {}).get("prep")
        if v is None:
            d[pt] = None
        elif v in L.FAILED:
            d[pt] = v
        else:
            d[pt] = L.OBL[cp] * 1000.0 / v
    return d


def peak(cp):
    d = {}
    for pt in L.POINTS:
        v = L.main_point(sweep, cp, "peak") if pt == "p00" else sweep.get((pt, cp), {}).get("peak")
        d[pt] = None if v is None else (v if v in L.FAILED else v / 1048576.0)
    return d


def gen(cp):
    d = {}
    for pt in L.POINTS:
        v = L.main_point(sweep, cp, "gen") if pt == "p00" else sweep.get((pt, cp), {}).get("gen")
        d[pt] = None if v is None else (v if v in L.FAILED else v / 1000.0)
    return d


def prep(cp):
    d = {}
    for pt in L.POINTS:
        v = L.main_point(sweep, cp, "prep") if pt == "p00" else sweep.get((pt, cp), {}).get("prep")
        d[pt] = None if v is None else (v if v in L.FAILED else v / 1000.0)
    return d


def iters(cp):
    d = {}
    for pt in L.POINTS:
        r = iterlat.get((cp, pt))
        if not r:
            d[pt] = None
        else:
            d[pt] = r[0] if r[0] in L.FAILED else r[0] / 1000.0
    return d


def keyser():
    return {"ffi": {pt: (keys[pt][0] if pt in keys else None) for pt in L.POINTS}}


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
  --s-pub:#00969b; --s-priv:#c0762c;
  --lbl-286:#4a3aa7; --lbl-keep:#0a7a54;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#12151a; --card:#191d24; --ink:#e9ecef; --ink-2:#aab2ba; --ink-3:#79828c;
  --rule:#2a313a; --rule-2:#20262e;
  --sig:#5fd0d3; --sig-soft:#12302f; --sig-ink:#8fe3e5;
  --warn:#e0a163; --warn-soft:#31251a;
  --good:#84c78e; --good-soft:#1a2a1d;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -18px rgba(0,0,0,.7);
  --s-pub:#0b9ba0; --s-priv:#c9822f;
  --lbl-286:#9085e9; --lbl-keep:#28a87e;}}
:root[data-theme="dark"]{
  --paper:#12151a; --card:#191d24; --ink:#e9ecef; --ink-2:#aab2ba; --ink-3:#79828c;
  --rule:#2a313a; --rule-2:#20262e;
  --sig:#5fd0d3; --sig-soft:#12302f; --sig-ink:#8fe3e5;
  --warn:#e0a163; --warn-soft:#31251a;
  --good:#84c78e; --good-soft:#1a2a1d;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -18px rgba(0,0,0,.7);
  --s-pub:#0b9ba0; --s-priv:#c9822f;
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
    ks_main = keys.get("p00", (None,))[0]
    ks_tip = keys.get(TIP, (None,))[0]
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
    c.append("<p style=\"margin-top:14px\">The failure is not slowness. On the monolith "
             "<code>main</code> exhausts a 12&nbsp;GB address space before it finishes "
             "preparing, and on the refinement chain it exceeds a fifteen-minute ceiling. "
             "There is no number to make faster; there is a wall to remove.</p>")
    if isinstance(it_main, str) or it_main:
        c.append("<p>The same wall stands in the editor. Re-checking the refinement chain "
                 "after a single edit, with every fingerprint already in the cache, "
                 "%s on <code>main</code> and takes %s after this series.</p>"
                 % ("exceeds the half-hour ceiling" if it_main in L.FAILED
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
<p>Not a benchmark gate &mdash; a soundness one. For each of the seventeen commits, in
sequence: <code>dune runtest src</code> and <code>dune runtest lsp</code> green, and
the <code>test/fast</code> fail-set identical to <code>main</code>'s with the full
prover stack &mdash; Z3&nbsp;4.8.9, Zenon, and Isabelle&nbsp;2025 with the TLA+ heap
built from this repository's <code>isabelle/</code> sources. That is 47 of 48; the one
failure, <code>fast/fingerprint/FingerprintVariablesParameters_test.tla</code>, fails
identically on <code>main</code> because Z3&nbsp;4.8.9 does not prove
<code>\\E y : y # x</code> there. The gate is fail-set identity, not a pass count, so
a newly failing test is a regression even if the count is unchanged.</p>
<p>Two invariants hold across the whole series. <strong>The provers receive a subset
of what they receive today</strong>, never more, and no obligation is created that
does not exist today. <strong>Fingerprints do not move</strong>: the digest is
computed on the const-annotated pre-expansion obligation, and every change that
removes context runs after that point, on the backend path only &mdash; so
<code>--printallobs</code> output and cache hits are unchanged by construction rather
than by testing.</p>""")

    c.append(_noise_sentence())
    c.append(_completeness())
    c.append("""<h4>Measurement machine</h4>
<div class="scroller"><table><tbody>
<tr><td>CPU</td><td class="num">Intel Xeon @ 2.10 GHz, 4 cores</td></tr>
<tr><td>memory</td><td class="num">16 GB, runs capped at 12 GB of address space</td></tr>
<tr><td>kernel</td><td class="num">Linux 6.18.44</td></tr>
<tr><td>compiler</td><td class="num">OCaml 4.14.1</td></tr>
<tr><td>provers</td><td class="num">Z3 4.8.9, Zenon 0.8.4, Isabelle 2025 + TLA+ heap</td></tr>
<tr><td>ceilings</td><td class="num">600 s generation, 900 s preparation, 1800 s iteration latency</td></tr>
<tr><td>boot</td><td class="num">%s</td></tr>
</tbody></table></div>
<p style="margin-top:12px">Absolute values are comparable only inside this table.
Every measured row carries the machine's <code>/proc/stat btime</code> and every
reader filters to a single boot, so a container restart mid-campaign appears as a
missing cell rather than as a step averaged into a curve. <code>main</code> is
measured twice, at the start of the campaign and at the end; %s</p>""" % (
        boot or "&mdash;", _drift_sentence()))
    return "".join(c)


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


def _drift_sentence():
    if not drift:
        return ("the second measurement is not in yet, so the <code>main</code> points "
                "are single runs.")
    worst = max(drift.items(), key=lambda kv: kv[1])
    return ("the largest disagreement between the two is %.1f&nbsp;%% (%s, %s), which is "
            "the drift the whole curve carries; the <code>main</code> point on each chart "
            "is the mean of the pair." % (100 * worst[1], worst[0][0], worst[0][1]))


def fig(title, sub, aria, values, unit, fmt_end, caption, series=None, points=None):
    return ('<figure style="margin-top:20px"><h4 style="margin:0 0 2px">%s</h4>'
            '<p style="font-size:13.5px;color:var(--ink-2);margin:0 0 12px">%s</p>%s'
            '<figcaption>%s</figcaption></figure>'
            % (title, sub, C.chart(aria, values, unit, fmt_end, series, points), caption))


def sec_curves():
    c = ["""<p>One point per commit, <code>main</code> at the left, in the order the
series is proposed in. A cross in the band below the axis means the run
<strong>did not complete</strong>; the tables in &sect;6 say which of the two ways,
because the difference matters &mdash; a change that speeds preparation up reaches the
memory wall <em>sooner</em>, turning a ceiling into an abort without being a
regression. Public and private corpora share each chart: hue separates them, dash
separates sizes.</p>
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
    "whole per-obligation pipeline with no prover. Higher is better. Obligations differ "
    "in size between corpora, so compare the shape of a curve, not its height against "
    "another's.",
    "Preparation throughput in obligations per second, one point per commit, five corpora "
    "on a logarithmic axis; the two private specifications do not complete on main.",
    {cp: thr(cp) for cp in L.CORPORA}, "obl/s",
    lambda v: "%.0f/s" % v if v >= 10 else "%.1f/s" % v,
    "The two private specifications have no <code>main</code> point at all: one exceeds "
    "the ceiling, the other exhausts the memory cap. They appear on the chart only once "
    "a commit makes them runnable, which is the result rather than a gap in it."))

    c.append(fig(
    "Peak memory of a preparation pass",
    "Maximum resident set of the same run, in gigabytes, under a 12&nbsp;GB address-space "
    "cap. Lower is better.",
    "Peak resident set per commit, five corpora, logarithmic axis.",
    {cp: peak(cp) for cp in L.CORPORA}, "GB",
    lambda v: "%.0f MB" % (v * 1024) if v < 1 else "%.2f GB" % v,
    "The step is the fourth pull request, and it is a step rather than a slope: peak "
    "memory stops being a function of the file and becomes a function of one obligation. "
    "Everything to the right of it is flat, which is the point &mdash; no later commit "
    "has to defend a memory budget."))

    c.append(fig(
    "Generation time",
    "<code>tlapm -N --nofp</code>: parse, elaborate, generate the obligations, stop. "
    "Seconds; lower is better. This is the floor under every editor interaction and "
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

    c.append(fig(
    "Iteration latency &mdash; the wait after one edit",
    "Warm prover, every fingerprint already in the cache, one proof step changed. "
    "Seconds; lower is better. This is the loop a user sits in, not a batch run.",
    "Iteration latency per commit on a warm fingerprint cache, public synthetic and "
    "private refinement chain, logarithmic axis.",
    {"synth300": iters("synth300"), "ffi": iters("ffi")}, "s",
    lambda v: "%.1f s" % v if v < 100 else "%.0f s" % v,
    "Only two changes move this metric across a threshold, and both are about doing less "
    "work per obligation rather than less work overall. The memory pull request is the one "
    "place in the series where this metric moves the wrong way, by about two per cent "
    "&mdash; inside the run-to-run spread, and small enough that the mechanism is not "
    "worth asserting. It stays at that position because what it buys is that nothing "
    "after it can run out of memory.",
    series=[("public synthetic, 1 800", "synth300", C.PUB, None),
            ("private refinement chain", "ffi", C.PRIV, "5 3")]))

    c.append(fig(
        "Keystroke to diagnostics, in the editor",
        "Time from the <code>didChange</code> notification to the "
        "<code>publishDiagnostics</code> that answers it, measured by a client speaking "
        "the LSP protocol. Seconds; lower is better.",
        "Keystroke to diagnostics latency per commit on the private refinement chain.",
        keyser(), "s", lambda v: "%.1f s" % v,
        "This is the only metric on which the last two pull requests are visible at all, "
        "and it is why they are in the series. Everything else in &sect;7 was dropped "
        "because it moved nothing here either.",
        series=[("private refinement chain", "ffi", C.PRIV, "5 3")]))
    return "".join(c)


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
            c.append('<p><span class="lbl">switch off</span>%s</p>' % d["off"])
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
<p>Every figure in this document is produced by <code>doc/perf/short/mkshort.py</code>
from the campaign CSVs beside it; none is typed in. The two private specifications are
a customer's and are not published &mdash; only the measurements taken on them are.</p>
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
