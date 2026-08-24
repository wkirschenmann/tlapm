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
    """ITER_STEP has to clear the noise it claims to clear.

    The constant carried a comment saying it was "well clear of the run-to-run
    spread" and nothing measured it.  The three clock commits cannot have moved
    iteration latency -- they are inert without --timing, which the harness does
    not pass -- so their spread is that noise, and the threshold is now
    accountable to it rather than to a comment.
    """
    import mkshort as M
    bad = []
    for cp in L.CORPORA:
        b = M.iter_band(cp)
        if not b:
            continue
        spread, ncm, nrun, within = b
        worst = max(spread, within)
        if (M.ITER_STEP - 1.0) * 100.0 <= worst:
            bad.append("ITER_STEP %.2f names a %.1f%% move a result on %s, where the "
                       "commits that cannot have moved it spread %.1f%% "
                       "(%.1f%% between commits, %.1f%% within one)"
                       % (M.ITER_STEP, (M.ITER_STEP - 1) * 100, cp, worst,
                          spread, within))
    return bad


if __name__ == "__main__":
    sweep, boot, _ = L.load_sweep()
    # Apply the repeated pass, exactly as the generator does.  Without this the
    # checker reads single samples while the document reads medians, so it reports a
    # trend the reader cannot see and stays silent about one the reader can.
    sweep, _reps = L.apply_reps(sweep)
    msgs = check(sweep) + check_inconclusive() + check_demo_readme() + check_sixth_corpus() + check_iter_threshold()
    for m in msgs:
        print("LINECHECK " + m)
    if not msgs:
        print("LINECHECK clean")
