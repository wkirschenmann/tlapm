# -*- coding: utf-8 -*-
"""Per-line sanity checks, run on every refresh.

One chart line is one (metric, corpus) pair.  Two things are worth catching while
a campaign is still running rather than at the end:

  * the control corpus must be FLAT.  It is on every chart to support the claim
    that small proofs do not get slower, so a trend in it is either a real
    regression or a drifting machine -- both worth knowing immediately.
  * a spike is not a step.  A point that differs from both of its neighbours by
    more than a factor is a bad run, not a commit doing something: a step shows
    up as a level change that the following points hold.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shortlib as L

CONTROL = "tiny"
SPIKE = 1.6          # a point this far from BOTH neighbours is a spike, not a step
TREND = 3.0          # percent between the first and last third of the control


def check(sweep):
    out = []
    for field in ("gen", "prep", "peak"):
        for cp in L.CORPORA:
            vals = [(i, sweep.get((p, cp), {}).get(field))
                    for i, p in enumerate(L.POINTS)]
            vals = [(i, v) for i, v in vals if isinstance(v, int)]
            if len(vals) < 12:
                continue
            xs = [v for _, v in vals]
            if cp == CONTROL and field != "peak":
                k = max(1, len(xs) // 3)
                a = sum(xs[:k]) / float(k)
                b = sum(xs[-k:]) / float(k)
                d = (b - a) / a * 100
                if abs(d) > TREND:
                    out.append("TREND %s/%s first third %.0f, last third %.0f (%+.1f %%)"
                               % (field, cp, a, b, d))
            for j in range(1, len(xs) - 1):
                p, c, n = xs[j - 1], xs[j], xs[j + 1]
                if not p or not n:
                    continue
                if (c / float(p) > SPIKE and c / float(n) > SPIKE) or \
                   (p / float(c) > SPIKE and n / float(c) > SPIKE):
                    out.append("SPIKE %s/%s at %s: %d between %d and %d"
                               % (field, cp, L.POINTS[vals[j][0]], c, p, n))
    return out


def check_inconclusive(page="/home/user/tlapm/doc/perf/SHORT_PROPOSAL.html"):
    """The page claims no inconclusive cell is quoted as a figure.  Hold it to that.

    A protocol timeout still has a memory reading -- the run did occupy that much
    before we stopped it -- and the temptation is to use the number anyway.  The
    charts refuse to, by drawing a ring; this refuses to in prose, by looking for
    that reading in the rendered page in the shapes the document formats memory in.
    Its elapsed time is not checked: that is the ceiling by construction.
    """
    import io, os
    if not os.path.exists(page):
        return []
    import mkshort as M
    h = io.open(page, encoding="utf-8").read()
    out = []
    for cp in L.CORPORA:
        for pt, v in M.peak(cp).items():
            if not (isinstance(v, dict) and v.get("pending")):
                continue
            c = M._cell(cp, pt)
            # Only the memory reading is checked.  The elapsed time of a protocol
            # timeout IS the ceiling by construction, so it carries no information
            # and matching it would just find the ceiling in the machine table.
            for field, raw in (("peak", c.get("peak_raw")),):
                if not raw:
                    continue
                shapes = [L.fmt_kb(raw), "%.2f GB" % (raw / 1048576.0),
                          "%d MB" % round(raw / 1024.0)]
                for sh in set(shapes):
                    if sh and sh in h:
                        out.append("QUOTED %s/%s %s reads \"%s\" in the page, but that "
                                   "cell is an inconclusive protocol timeout"
                                   % (cp, pt, field, sh))
    return out


def check_demo_readme():
    """The corpus README quotes figures in prose; instance_demo.csv holds them.

    Prose cannot be generated from a slot the way the document's cells are, so
    it is checked instead: regenerating the corpus moves these numbers, and a
    README that still claims the old ones is exactly the kind of stale sentence
    this checker exists to catch.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "instance_demo", "README.md")
    if not os.path.exists(path):
        return ["MISSING instance_demo/README.md, which the document points readers at"]
    txt = open(path).read()
    d = L.load_instance_demo()
    pr, lad, ldf = d["proofs"], d["ladder"], d["ladder_defn"]
    ks = sorted(lad, key=int)
    want = [
        ("%d definitions and %d hypotheses" % (ldf[ks[1]] - ldf[ks[0]],
                                               lad[ks[1]] - lad[ks[0]]),
         "definitions and hypotheses per INSTANCE"),
        ("%d of those %d" % (d["ladder_frag_two_hop"]["1"], ldf[ks[1]] - ldf[ks[0]]),
         "the two-hop share of one INSTANCE"),
        ("{:,} lines".format(pr["lines"]), "proof size"),
        ("{:,} obligations".format(pr["obligations"]), "obligation count"),
        ("%d lemmas" % pr["lemmas"], "lemma count"),
        ("{:,}".format(pr["total_ctx_hyps"]), "context entries walked"),
        ("%d per obligation" % (pr["total_ctx_hyps"] // pr["obligations"]),
         "context entries per obligation"),
        ("%d lines" % pr["stack_lines"], "stack source size"),
        ("%.0f s and %.1f GB" % (d["main"]["prep_ms"] / 1000.0,
                                 d["main"]["peak_kb"] / 1048576.0),
         "cost on the base commit"),
        ("%.1f s and %.0f MB" % (d["tip"]["prep_ms"] / 1000.0,
                                 d["tip"]["peak_kb"] / 1024.0),
         "cost at the tip"),
    ]
    return ["STALE instance_demo/README.md: %s should read \"%s\"" % (why, s)
            for s, why in want if s not in txt]


def check_sixth_corpus():
    """Would the generator survive the next corpus getting measurements?

    Every corpus label lived in three places -- two constants and one inline
    dict -- and all three would have raised KeyError the moment a sixth corpus
    had rows in the sweep.  That is a crash the reader meets before the author
    does, so it is checked here rather than discovered there: the whole
    CORPUS_ORDER is forced on, the document is built to a scratch path, and any
    exception is the finding.
    """
    import importlib, tempfile, os as _os
    saved = L.CORPORA
    try:
        L.CORPORA = list(L.CORPUS_ORDER)
        M = importlib.import_module("mkshort")
        out = M.OUT
        try:
            M.OUT = _os.path.join(tempfile.gettempdir(), "linecheck_preflight.html")
            M.build()
        finally:
            M.OUT = out
    except Exception as e:
        return ["CANNOT BUILD with every corpus in CORPUS_ORDER measured: %s: %s"
                % (type(e).__name__, e)]
    finally:
        L.CORPORA = saved
    return []


def check_iter_threshold():
    """No corpus may name a move a result that its own noise could produce.

    This started as a check on one global constant and immediately earned its
    keep: 1.10 named a 10 % move a result on the public stack, whose band is
    12 %. The threshold is per corpus now, so the check guards the structure --
    it fails if anyone reintroduces a shared constant that sits under a band.
    """
    import mkshort as M
    bad = []
    for cp in L.CORPORA:
        b = M.iter_band(cp)
        if not b:
            continue
        worst = max(b[0], b[3])
        thr = (M.iter_threshold(cp) - 1.0) * 100.0
        # Strictly under, not "at or under".  The threshold is now DERIVED from the
        # band, so equality is the intended construction -- a move has to beat the
        # band, and one exactly its size does not count as a step.  With `<=` the
        # check fired on every corpus whose band exceeds the floor, which is the
        # normal case and not a defect.
        if thr + 1e-9 < worst:
            bad.append("the iteration threshold on %s is %.1f%%, under its own "
                       "noise band of %.1f%% (%.1f%% between commits, %.1f%% within "
                       "one) -- a move that size could be the machine"
                       % (cp, thr, worst, b[0], b[3]))
    return bad


def check_marked_points():
    """A point marked from a neighbour must never reach the page as a duration.

    The chain's left end is settled by walking the series from the right and marking
    everything left of the first hour-long stop.  Those rows carry ms -1, which no
    clock can produce, precisely so that a loader treating them as times is caught
    here rather than by a reader.
    """
    import csv as _csv
    import mkshort as M
    bad = []
    path = os.path.join(L.S, "short_iterlat.csv")
    if not os.path.exists(path):
        return bad
    rows = list(_csv.DictReader(open(path)))
    marked = {(L.ITER_CORPUS.get(r["corpus"], r["corpus"]), r["point"])
              for r in rows if int(r["ms"]) < 0}
    real = {(L.ITER_CORPUS.get(r["corpus"], r["corpus"]), r["point"])
            for r in rows if int(r["ms"]) >= 0 and int(r["rc"]) == 0}
    for cp, pt in sorted(marked - real):
        v = M.iters(cp).get(pt)
        if v is None:
            continue
        if not (isinstance(v, dict) and v.get("marked")):
            bad.append("%s %s was marked from a neighbour, never run, and the document "
                       "reads it as %r" % (cp, pt, v))
    return bad


def check_obligation_counts():
    """The obligation count of a corpus is measurable; check it is the measured one.

    "71 obligations" was published for a module that has twenty -- in a table, in the
    opening sentence and in the control paragraph -- because the count was typed once
    and never read back.  Three of the corpora are proved end to end by the iteration
    harness, which reports what the tool saw, so those three can be checked directly.
    The public stack is checked against its own CSV instead: its iteration fixture
    cites an extra theorem on twenty-six steps, so the fixture legitimately carries
    twenty-six obligations the file does not.  The two private corpora are measured
    over a line range and have no full count here to check against.
    """
    import csv as _csv
    import collections as _c
    bad = []
    path = os.path.join(L.S, "short_iterlat.csv")
    if os.path.exists(path):
        seen = _c.defaultdict(_c.Counter)
        for r in _csv.DictReader(open(path)):
            if int(r["rc"]) == 0:
                seen[r["corpus"]][int(r["proved"]) + int(r["trivial"])] += 1
        for cp in ("tiny", "synth100", "synth300"):
            if not seen.get(cp):
                continue
            n = seen[cp].most_common(1)[0][0]
            if n != L.OBL.get(cp):
                bad.append("%s is published as %s obligations and the harness proves %d "
                           "of them" % (cp, L.OBL.get(cp), n))
    demo = os.path.join(L.S, "instance_demo.csv")
    if os.path.exists(demo):
        for r in _csv.reader(open(demo)):
            if len(r) == 3 and r[0] == "proofs" and r[1] == "obligations":
                if int(r[2]) != L.OBL.get("idemo"):
                    bad.append("the public stack is published as %s obligations and "
                               "instance_demo.csv says %s" % (L.OBL.get("idemo"), r[2]))
    return bad


def check_series_labels():
    """A chart legend that names an obligation count must name the campaign's.

    "public synthetic, 71" survived in the legend after the corpus was found to
    have twenty obligations, because the count lived in two places and only one
    was corrected.
    """
    import re as _re
    import charts as C
    bad = []
    for name, cp, _, _ in C.SERIES:
        m = _re.search(r"([\d\u00a0 ,]{2,})$", name)
        if not m:
            continue
        n = int(_re.sub(r"[^\d]", "", m.group(1)))
        if n != L.OBL.get(cp):
            bad.append("the legend calls %s \"%s\" and the campaign counts %s "
                       "obligations" % (cp, name, L.OBL.get(cp)))
    return bad


def check_vouched_rows():
    """A deliberate re-measurement that no anchor can vouch for is invisible.

    load_sweep admits an off-boot phase-L duration only when the campaign's anchor
    cell has been re-measured on that boot and agrees with the line's host.  A row
    measured on a boot with no anchor is therefore dropped in silence -- which is
    how a sixteen-minute run came to sit in the CSV without reaching any chart.
    """
    import csv as _csv
    import collections as _c
    bad = []
    rows = list(_csv.DictReader(open(os.path.join(L.S, "short_sweep.csv"))))
    anch = {r["boot"] for r in rows
            if r["phase"].startswith("K") and int(r["prep_rc"]) == 0}
    sweep, _boot, _d = L.load_sweep()
    line_boot = sweep.get("_line_boot", {})
    for r in rows:
        if r["phase"] != "L" or int(r["prep_ms"]) <= 0 or int(r["prep_rc"]) != 0:
            continue
        if r["boot"] == line_boot.get((r["corpus"], "prep")):
            continue
        if r["boot"] in anch:
            continue
        # only worth saying when the cell has no admissible reading at all: an older
        # unusable row behind a good one costs the reader nothing
        v = sweep.get((r["point"], r["corpus"]), {}).get("prep")
        if isinstance(v, int):
            continue
        bad.append("%s/%s was measured on boot %s, which nothing can vouch for, so "
                   "no chart can use it -- measure a cell of at least a minute on "
                   "both boots, or the anchor" % (r["corpus"], r["point"], r["boot"]))
    return bad


def check_one_boot_per_cell():
    """A row carrying both metrics is read for both, so both lines must want it.

    The row selection keeps a row when its boot is the boot of the FIRST metric it
    carries, and then reads every metric off it.  That is only sound while a corpus
    whose rows carry both metrics has the same boot chosen for both lines -- if the
    two lines ever diverge, one of them would be quietly reading a duration measured
    on a machine it rejected.  Nothing in the loader prevents that; this does.
    """
    import csv as _csv
    import collections as _c
    rows = list(_csv.DictReader(open(os.path.join(L.S, "short_sweep.csv"))))
    both = _c.defaultdict(int)
    for r in rows:
        if r["gen_ms"] != "-2" and r["prep_ms"] != "-2":
            both[r["corpus"]] += 1
    sweep, _b, _d = L.load_sweep()
    lb = sweep.get("_line_boot", {})
    bad = []
    for cp, n in sorted(both.items()):
        g, p = lb.get((cp, "gen")), lb.get((cp, "prep"))
        if g is not None and p is not None and g != p:
            bad.append("%s has %d rows carrying both metrics, but its generation "
                       "line sits on boot %s and its preparation line on %s, so one "
                       "of the two reads a duration off a boot it rejected"
                       % (cp, n, g, p))
    return bad


def check_golden():
    """the document claims the dump is identical on every corpus -- golden.csv says so"""
    import csv
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden.csv")
    if not os.path.exists(f):
        return ["golden.csv is missing, and section 4 claims the obligation dump is "
                "identical on every corpus"]
    seen = {}
    with open(f) as fh:
        for r in csv.DictReader(fh):
            seen[r["corpus"]] = r["verdict"]
    bad = []
    for cp in L.CORPORA:
        v = seen.get(cp)
        if v is None:
            bad.append("golden.csv has no row for %s, so the claim in section 4 covers "
                       "a corpus nothing checked" % cp)
        elif v != "IDENTICAL":
            bad.append("golden.csv says %s is %s -- section 4 claims no difference on "
                       "any corpus" % (cp, v))
    return bad


if __name__ == "__main__":
    sweep, boot, _ = L.load_sweep()
    # Apply the repeated pass, exactly as the generator does.  Without this the
    # checker reads single samples while the document reads medians, so it reports a
    # trend the reader cannot see and stays silent about one the reader can.
    sweep, _reps = L.apply_reps(sweep)
    msgs = check(sweep) + check_inconclusive() + check_demo_readme() + check_sixth_corpus() + check_iter_threshold() + check_marked_points() + check_obligation_counts() + check_series_labels() + check_vouched_rows() + check_golden() + check_one_boot_per_cell()
    for m in msgs:
        print("LINECHECK " + m)
    if not msgs:
        print("LINECHECK clean")
