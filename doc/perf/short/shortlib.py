# -*- coding: utf-8 -*-
"""Readers for the short-proposal campaign.

One campaign, one boot, one machine.  Every row carries /proc/stat btime and
every reader filters to a single boot, so a container restart mid-campaign
shows up as missing cells rather than as a seam averaged into the curve.

Sentinels, never numbers:
  DNC    not measured at this point
  CEIL   exceeded the wall-clock ceiling (timeout, rc 124)
  ABORT  exceeded the address-space cap (rc 134/137)
"""
import os, csv, collections, statistics

S = os.environ.get("SHORT_DIR", os.path.dirname(os.path.abspath(__file__)))

DNC, CEIL, ABORT = "DNC", "CEIL", "ABORT"
FAILED = (DNC, CEIL, ABORT)

# How far two hosts' readings of the anchor cell may differ and still count as the
# same machine.  The campaign's nineteen anchor runs span 8 % between themselves,
# so a threshold under that would reject a host for being ordinary.
ANCHOR_TOL = 0.05

# the 17 measured points, and the pull request each commit belongs to
POINTS = ["p%02d" % i for i in range(22)]
PRS = [
    ("PR1", "correctness fixes",      ["p01", "p02", "p03", "p04", "p05"]),
    ("PR2", "deque lookups",          ["p06"]),
    ("PR3", "single-pass expansion",  ["p07"]),
    ("PR4", "bounded memory",         ["p08", "p09"]),
    ("PR5", "context pruning",        ["p10", "p11"]),
    ("PR6", "prefix-resume caches",   ["p12", "p13", "p14"]),
    ("PR7", "linear ENABLED scan",    ["p15"]),
    ("PR8", "editor obligation pool", ["p16"]),
    ("PR9", "memoized grammar rules",  ["p17"]),
    ("PR10", "memoized expansion substitution", ["p18"]),
    ("PR11", "visibility-invariant caching",    ["p19"]),
    ("PR12", "no identity rebuilds",            ["p20", "p21"]),
]
ENDPOINTS = ["p00"] + [c[-1] for _, _, c in PRS]

OBL = {"tiny": 20, "synth100": 600, "synth300": 1800, "idemo": 2703,
       "gp2": 5957, "ffi": 9967, "dotnet": 28818, "mono": 29965}

# Every corpus this campaign knows how to measure, smallest first.  Which of
# them actually appear on the curves is decided by the data, not by this list:
# a corpus with no rows in the sweep would otherwise contribute an empty line
# and a legend entry pointing at nothing.
CORPUS_ORDER = ["tiny", "synth100", "synth300", "idemo", "gp2", "ffi",
                "dotnet", "mono"]


def _corpora_present(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "short_sweep.csv")
    seen = set()
    try:
        with open(path) as f:
            for r in csv.DictReader(f):
                seen.add(r["corpus"])
    except OSError:
        return set(CORPUS_ORDER)
    return seen


CORPORA = [c for c in CORPUS_ORDER if c in _corpora_present()]


def _verdict(rc):
    if rc == 124:
        return CEIL
    if rc in (134, 137, 2):
        return ABORT
    return None


def load_sweep(path=None, boot=None):
    """{(point, corpus): {gen, prep, peak}} with sentinels for failures.

    One chart line is one (metric, corpus) pair, and comparability only has to hold
    WITHIN a line: a curve is read against itself, from main to the tip.  So the boot
    is chosen per line, not once for the whole file -- the line with the most points
    on a single boot wins, and that boot is recorded so the document can say which
    machine each curve was measured on.

    That is what makes a campaign survive a restart.  When this one was interrupted,
    nine of its ten lines were already complete on one boot and the tenth had not
    started; choosing globally would have thrown away either the nine or the tenth.
    """
    path = path or os.path.join(S, "short_sweep.csv")
    raw = []
    with open(path) as f:
        for r in csv.DictReader(f):
            raw.append(r)
    if not raw:
        return {}, None, {}
    anchors = [r for r in raw if r["phase"].startswith("K")]
    data = [r for r in raw if not r["phase"].startswith("K")]

    # The campaign re-measures one cell -- the chain's preparation at p14 -- over
    # and over, for one purpose: to say whether two hosts are the same machine as
    # far as this metric is concerned.  Two boots AGREE when both have re-measured
    # it and their medians are within ANCHOR_TOL.  That is what lets a deliberate
    # re-measurement taken today join a curve measured on a host that no longer
    # exists; without it a duration is confined to its own boot, and a line with a
    # hole in it can never be filled once the machine is gone.
    anchor_ms = collections.defaultdict(list)
    for r in anchors:
        if int(r["prep_rc"]) == 0 and int(r["prep_ms"]) > 0:
            anchor_ms[r["boot"]].append(int(r["prep_ms"]))

    # A cell measured on both boots can serve as the bridge when the designated
    # anchor was never run on one of them -- provided it is long enough to be about
    # the processor rather than about starting a process.  The two hosts here agree
    # to 0.4 % on a 149 s run and differ by 2.8x on a 100 ms one, so a short cell
    # would report a different machine for a difference in start-up cost.
    BRIDGE_MIN_MS = 60000
    bridge = collections.defaultdict(list)
    for r in data:
        if int(r["prep_ms"]) >= BRIDGE_MIN_MS and int(r["prep_rc"]) == 0:
            bridge[(r["boot"], r["corpus"], r["point"])].append(int(r["prep_ms"]))

    def hosts_agree(b1, b2, skip=None):
        pairs = []
        a, b = anchor_ms.get(b1), anchor_ms.get(b2)
        if a and b:
            pairs.append((statistics.median(a), statistics.median(b)))
        for (bb, cp, pt), v in bridge.items():
            if bb != b1 or (cp, pt) == skip:
                continue
            w = bridge.get((b2, cp, pt))
            if w:
                pairs.append((statistics.median(v), statistics.median(w)))
        if not pairs:
            return False
        # every shared reading has to agree: one that does not is a host that is
        # not the same machine for some part of this work
        return all(abs(m1 - m2) / float(max(m1, m2)) <= ANCHOR_TOL
                   for m1, m2 in pairs)

    # per (corpus, field), the boot carrying the most measured points
    def fields_of(r):
        """A row can carry both metrics, and then it is a point on both lines.

        Classing such a row by one metric alone left the other line with no boot at
        all: every one of its rows then counted as off-boot, and the line survived
        only because the row was admitted under the first metric's name.  Coverage is
        per line, so a row counts for each line it has a reading on."""
        return [f for f, ms in (("gen", r["gen_ms"]), ("prep", r["prep_ms"]))
                if int(ms) != -2]

    def field_of(r):
        return "gen" if int(r["gen_ms"]) != -2 else "prep"

    # Count POINTS of the line a boot covers, not rows: a boot that repeated one
    # cell twenty times covers one point, and a line drawn from it would be one
    # point long.  Ties go to the newer boot -- when a line has been re-measured
    # end to end on a second machine, that measurement is the deliberate one, and
    # leaving the choice to dictionary order makes the document depend on which
    # row a reader's csv module happened to see first.
    #
    # Only a DURATION counts toward the vote, for the same reason durations are
    # the only readings confined to their own boot: a cell the address-space cap
    # refused, or the ceiling stopped, says the same thing on any host and is
    # admitted from any boot below.  Counting those would let a host win the line
    # on cells it did not actually time -- which is how a chain re-measured end to
    # end on one machine lost to an older host that had merely watched the same
    # nine points run out of memory.
    cover = collections.defaultdict(set)
    for r in data:
        for fld in fields_of(r):
            if int(r[fld + "_rc"]) != 0:
                continue
            cover[(r["corpus"], fld, r["boot"])].add(r["point"])
    line_boot = {}
    for (cp, fld, b), pts in cover.items():
        k = (cp, fld)
        cur = line_boot.get(k)
        if cur is None:
            line_boot[k] = b
            continue
        n_cur = len(cover[(cp, fld, cur)])
        if len(pts) > n_cur or (len(pts) == n_cur and int(b) > int(cur)):
            line_boot[k] = b
    # phase L supersedes a ceiling it was run to resolve, on the same line's boot
    longer = {(r["point"], r["corpus"]) for r in data
              if r["phase"] == "L"
              and (r["boot"] == line_boot.get((r["corpus"], "prep"))
                   or _verdict(int(r["prep_rc"])) == ABORT)}

    out = collections.defaultdict(dict)
    for r in data:
        # Admission is per READING, not per row. A row can carry a generation time
        # and a preparation time, and the two lines can sit on different machines --
        # here they do: preparation was measured over an afternoon and two restarts,
        # generation end to end in a quarter of an hour afterwards. Judging the row
        # by its first reading threw the other one away with it, which emptied a
        # whole column the moment the generation line moved host.
        def admit(fld):
            ms = int(r[fld + "_ms"])
            if ms == -2:
                return False
            if r["boot"] == line_boot.get((r["corpus"], fld)):
                return True
            # An off-boot row is admissible when what it establishes is a VERDICT
            # rather than a duration. The cap is 12 GB on any machine, so "the cap
            # refused an allocation" transfers between hosts; "it finished in 1035 s"
            # does not, unless the two hosts have a shared reading that agrees.
            if r["phase"] != "L":
                return False
            v = _verdict(int(r[fld + "_rc"]))
            if v == ABORT:
                return True
            return v is None and hosts_agree(
                r["boot"], line_boot.get((r["corpus"], fld)),
                skip=(r["corpus"], r["point"]))

        take_gen, take_prep = admit("gen"), admit("prep")
        if not (take_gen or take_prep):
            continue
        if take_prep and r["phase"] != "L" and (r["point"], r["corpus"]) in longer \
                and int(r["prep_rc"]) == 124:
            take_prep = False
            if not take_gen:
                continue
        k = (r["point"], r["corpus"])
        out[k]["sha"] = r["sha"]
        g, grc = (int(r["gen_ms"]), int(r["gen_rc"])) if take_gen else (-2, 0)
        p_, prc = (int(r["prep_ms"]), int(r["prep_rc"])) if take_prep else (-2, 0)
        if g != -2:
            out[k]["gen"] = _verdict(grc) or g
            out[k]["gen_raw"] = g
        if p_ != -2:
            v = _verdict(prc)
            out[k]["prep"] = v or p_
            out[k]["peak"] = v or int(r["peak_kb"])
            out[k]["prep_raw"] = p_
            out[k]["peak_raw"] = int(r["peak_kb"]) or None
            # Phase L is the extended clock.  A verdict that comes from it is settled;
            # one that comes from the ordinary ceiling is still awaiting that run, and
            # the charts mark the two differently.
            out[k]["long"] = (r["phase"] == "L")
    out = dict(out)
    out["_line_boot"] = line_boot

    drift = {}
    by_boot = collections.defaultdict(list)
    for r in anchors:
        v = int(r["prep_ms"])
        if v > 0 and int(r["prep_rc"]) == 0:
            by_boot[r["boot"]].append(v)
    out["_anchors"] = dict(by_boot)
    boots = collections.Counter(line_boot.values())
    boot = boots.most_common(1)[0][0] if boots else None
    if len(by_boot.get(boot, [])) > 1:
        a = by_boot[boot]
        drift[("anchor", "prep")] = (max(a) - min(a)) / float(max(a))
    return out, boot, drift


def apply_reps(sweep, path=None, boot=None):
    """Replace single-run values by the median of a repeated pass where one exists.

    A run of tens of milliseconds is dominated by process start-up and page-cache
    state, so one sample cannot separate two commits: the control corpus showed a
    10 % step at a commit that only changes a kill signal, and re-measuring the two
    ends back to back put them within 1 ms of each other.  Where a repeated,
    point-interleaved pass exists, its median replaces the sample.
    """
    path = path or os.path.join(S, "short_reps.csv")
    if not os.path.exists(path):
        return sweep, {}
    runs, boots = collections.defaultdict(list), set()
    with open(path) as f:
        for r in csv.DictReader(f):
            if int(r["rc"]) != 0:
                continue
            boots.add(r["boot"])
            runs[(r["boot"], r["corpus"], r["metric"], r["point"])].append(
                (int(r["ms"]), int(r["peak_kb"])))
    if not boots:
        return sweep, {}
    # The boot is chosen per (corpus, metric), for the reason load_sweep chooses it
    # per line: one corpus re-measured on a fresh host must be able to move without
    # dragging the rest of the file with it, and must not be outvoted by the row
    # count of corpora it has nothing to do with.  More rows wins; on a tie the more
    # recent boot does.
    tally = collections.Counter()
    for (b, cp, mt, pt) in runs:
        tally[(cp, mt, b)] += len(runs[(b, cp, mt, pt)])
    line_boot = {}
    for (cp, mt, b), n in sorted(tally.items(), key=lambda kv: (kv[1], kv[0][2])):
        line_boot[(cp, mt)] = b
    used = {}
    for (b, cp, mt, pt), v in runs.items():
        if b != (boot or line_boot.get((cp, mt))) or len(v) < 3:
            continue
        ms = sorted(m for m, _ in v)
        med = ms[len(ms) // 2]
        rec = sweep.setdefault((pt, cp), {})
        rec["gen" if mt == "gen" else "prep"] = med
        if mt == "prep":
            pk = sorted(k for _, k in v if k)
            if pk:
                rec["peak"] = pk[len(pk) // 2]
        used[(cp, mt)] = len(v)
    return sweep, used


def load_rate_by_position(path=None):
    """{(corpus, point): [(n, seconds), ...]} -- one row per obligation prepared.

    Written by the appendix pass, one file per (corpus, point).  A file that stops
    short of the corpus total is a run the cap refused there.
    """
    import glob
    d = path or os.path.join(S, "rate_by_position")
    out = {}
    if not os.path.isdir(d):
        return out
    for f in sorted(glob.glob(os.path.join(d, "*.csv"))):
        base = os.path.basename(f)[:-4]
        if "_" not in base:
            continue
        cp, pt = base.rsplit("_", 1)
        rows = []
        with open(f) as fh:
            for r in csv.DictReader(fh):
                try:
                    rows.append((int(r["n"]), float(r["seconds"])))
                except (KeyError, ValueError):
                    continue
        if rows:
            out[(cp, pt)] = rows
    return out


def load_partial(path=None):
    """{(corpus, point): (obligations prepared, ms)} for runs the cap refused.

    A cell that aborts has no throughput today, only a cross in the band below the
    axis.  It did do work before it died, though, and counting it turns the cross
    into a positioned one: this is how fast the run was going when it stopped.

    The count comes from a separate run under --printallobs, which builds the
    shipped form that plain --noproving skips; so its clock is its own, not the
    timed run's, and the rate is computed from the pair that belongs together.
    """
    path = path or os.path.join(S, "partial_oom.csv")
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            try:
                done, ms = int(r["obl_done"]), int(r["ms"])
            except (KeyError, ValueError):
                continue
            if done > 0 and ms > 0:
                out[(r["corpus"], r["point"])] = (done, ms)
    return out


def main_point(sweep, corpus, field):
    """main's value for a field: the mean of the two measurements when both
    completed, the single one when only one did, else the shared sentinel."""
    vals = [sweep.get((p, corpus), {}).get(field) for p in ("p00", "p00b")]
    nums = [v for v in vals if isinstance(v, int)]
    if nums:
        return int(round(sum(nums) / float(len(nums))))
    for v in vals:
        if v in FAILED:
            return v
    return DNC


def main_raw(sweep, corpus, field):
    """the elapsed time behind main's cell, whatever verdict that cell carries"""
    for p in ("p00", "p00b"):
        v = sweep.get((p, corpus), {}).get(field + "_raw")
        if isinstance(v, int) and v > 0:
            return v
    return None


# The iteration-latency harness names the private refinement chain "chain"; every
# other reader calls it "ffi", after the module.  One vocabulary, mapped on read,
# so a lookup can never silently return nothing -- which it did, and the chart
# drew without its main series.
ITER_CORPUS = {"chain": "ffi"}


def load_iteration_latency(path=None, boot=None):
    """{(corpus, point): (median_ms, spread, runs, reported)} — warm cache, one edit.

    Corpus names are normalised to the sweep's vocabulary on read."""
    path = path or os.path.join(S, "short_iterlat.csv")
    if not os.path.exists(path):
        return {}, None
    raw = []
    with open(path) as f:
        for r in csv.DictReader(f):
            r["_cp"] = ITER_CORPUS.get(r["corpus"], r["corpus"])
            r["_obl"] = int(r["proved"]) + int(r["failed"]) + int(r["trivial"])
            raw.append(r)
    if not raw:
        return {}, None
    # An interrupted run is indistinguishable from a fast one by its exit status:
    # tlapm handles SIGTERM by shutting its provers down, printing the verdicts it
    # already had and exiting 0.  A container restart or the OOM killer produces the
    # same shape.  What gives it away is the obligation count: a run that COMPLETES a
    # corpus reports the same number every time, so one that claims success with
    # materially fewer is a run that was stopped and reported what it had.
    #
    # The check applies only to rows claiming success.  A row stopped by the clock is
    # expected to report a partial count -- that is what being stopped means -- and an
    # earlier version of this guard, which checked every row, threw away the very
    # timeouts the charts need in order to draw a ring.
    done = [r for r in raw if int(r["rc"]) == 0]
    usual = {}
    for cp in {r["_cp"] for r in done}:
        counts = collections.Counter(r["_obl"] for r in done if r["_cp"] == cp)
        usual[cp] = max(counts, key=lambda n: (counts[n], n))
    def truncated(r):
        return (int(r["rc"]) == 0 and r["_cp"] in usual
                and r["_obl"] < 0.9 * usual[r["_cp"]])
    raw = [r for r in raw if not truncated(r)]
    # A run whose status is neither success nor one of the two stops measured
    # nothing at all, and it does not look like it: tlapm exits 3 on a file it
    # cannot check, in 133 ms, which lands in the same column as a very fast
    # iteration.  A harness whose edit named a backend the synthetic corpora do
    # not extend wrote one hundred and eight such rows, and the median of
    # eighteen parse failures is a perfectly plausible-looking figure.  Nothing
    # downstream would have caught it, so it is caught here.
    raw = [r for r in raw if int(r["rc"]) in (0, 124, 134, 137, 2)]
    runs, boots = collections.defaultdict(list), set()
    runs_of = collections.defaultdict(list)
    rep = {}
    for r in raw:
        boots.add(r["boot"])
        k = (r["boot"], r["_cp"], r["point"])
        runs[k].append((int(r["ms"]), int(r["rc"])))
        runs_of[k].append(r["run"])
        rep[k] = r["_obl"]
    if not boots:
        return {}, None
    # The boot is chosen per corpus, for the same reason the sweep chooses it per
    # chart line: a line is one (metric, corpus) pair and comparability only has to
    # hold within a line.  Choosing one boot for the whole file would let a freshly
    # measured corpus evict a complete line measured on an earlier one.
    if boot:
        line_boot = {cp: boot for _, cp, _ in runs}
    else:
        tally = collections.Counter((cp, b) for b, cp, _ in runs)
        line_boot = {}
        # More rows wins; on a tie the more recent boot wins.  Without the second
        # term the choice is dict order, and a line being re-measured passes through
        # a tie exactly when half of it is new -- so which protocol the chart drew
        # would depend on when it was drawn.
        for (cp, b), n in sorted(tally.items(), key=lambda kv: (kv[1], kv[0][1])):
            line_boot[cp] = b
    boot = max(collections.Counter(line_boot.values()).items(),
               key=lambda kv: kv[1])[0] if line_boot else None
    out = {}
    for (b, cp, pt), v in runs.items():
        if b != line_boot.get(cp):
            continue
        if any(rc in (134, 137, 2) for _, rc in v):
            # the address-space cap refused an allocation: settled, and not a time
            out[(cp, pt)] = (ABORT, 0.0, len([m for m, _ in v if m >= 0]),
                             rep[(b, cp, pt)], max(m for m, _ in v))
            continue
        if any(rc == 124 for _, rc in v):
            # Stopped by the clock.  Two ways to get here, and the reader must be
            # able to tell them apart: a run that spent the whole clock and did not
            # finish, and a point MARKED from a stop measured to its right -- the
            # series is a chain, so a point further left is the same tool with one
            # optimisation removed and cannot be faster.  A marked point is written
            # with run 0 and ms -1, which no clock produces; it reports zero runs
            # here, and that is what says "inferred, not measured".
            real = [m for m, _ in v if m >= 0]
            out[(cp, pt)] = (CEIL, 0.0, len(real), rep[(b, cp, pt)],
                             max(real) if real else -1)
            continue
        ms = [m for m, _ in v]
        med = int(statistics.median(ms))
        sp = (max(ms) - min(ms)) / float(max(ms)) if max(ms) else 0.0
        # Run 0 is not a run.  A value written there is CARRIED from a neighbour --
        # the campaign does that only where the neighbour provably cannot differ --
        # and it reports zero runs, which is what tells the page to draw and name it
        # apart from the measurements around it.
        nrun = len([r for r in runs_of[(b, cp, pt)] if r != "0"])
        out[(cp, pt)] = (med, sp, nrun, rep[(b, cp, pt)], med)
    return out, boot


def _keystroke_boot(vals, boot=None):
    """The boot a keystroke figure should be read from.

    Shared deliberately.  This ranking lived twice -- once in load_keystroke and once
    in keystroke_ranges -- and the two drifted apart, so the chart and its own caption
    were reading different boots and the caption quoted numbers absent from the chart.

    Ranked by COMMITS covered, not rows written: a pass that has covered five commits
    must not outrank a finished one covering eighteen, or the figure becomes a
    fragment halfway through a re-measurement.  Rows break a tie, and the newer boot
    breaks an exact one, so a completed re-measurement replaces the series it repeats
    and an unfinished one does not.
    """
    if boot:
        return boot
    boots = {b for b, _, _ in vals}
    if not boots:
        return None
    def rank(b):
        return (len({pt for bb, pt, _ in vals if bb == b}),
                sum(1 for k in vals if k[0] == b), b)
    return max(boots, key=rank)


def load_keystroke(path=None, boot=None):
    """{point: (median_s, spread, n)} -- didChange to publishDiagnostics.

    A point measured at several repetition counts keeps the largest: the small
    effects were re-run at n = 10 precisely because n = 3 could not separate them,
    and pooling the two would put the weaker evidence back in.
    """
    path = path or os.path.join(S, "short_keystroke.csv")
    if not os.path.exists(path):
        return {}, None
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["kind"] != "edit":
                continue
            cp = r.get("corpus") or "ffi"
            per[cp][(r["boot"], r["point"], int(r.get("n", 0) or 0))].append(
                float(r["seconds"]))
    if not per:
        return {}, None
    out, boots = {}, {}
    for cp, vals in per.items():
        b = _keystroke_boot(vals, boot)
        boots[cp] = b
        best = {}
        for (bb, pt, n), v in vals.items():
            if bb != b:
                continue
            if pt not in best or n > best[pt][0]:
                best[pt] = (n, v)
        for pt, (n, v) in best.items():
            med = statistics.median(v)
            sp = (max(v) - min(v)) / float(max(v)) if max(v) else 0.0
            out[(cp, pt)] = (med, sp, len(v))
    # the representative boot, for the machine table: the one carrying the most lines
    rep = collections.Counter(boots.values()).most_common(1)
    return out, (rep[0][0] if rep else None)


def keystroke_ranges(path=None, boot=None):
    """{point: (n, lo, hi)} at the largest repetition count measured per point."""
    path = path or os.path.join(S, "short_keystroke.csv")
    if not os.path.exists(path):
        return {}
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["kind"] != "edit":
                continue
            cp = r.get("corpus") or "ffi"
            per[cp][(r["boot"], r["point"], int(r.get("n", 0) or 0))].append(
                float(r["seconds"]))
    best = {}
    for cp, vals in per.items():
        b = _keystroke_boot(vals, boot)
        for (bb, pt, n), v in vals.items():
            if bb != b:
                continue
            k = (cp, pt)
            if k not in best or n > best[k][0]:
                best[k] = (n, min(v), max(v))
    return best


# How long a run had before the harness stopped it.  A bare "did not finish" leaves
# the reader unable to tell a slow run from a hung one, and the cap is the whole
# content of that cell.  Read it off the rows themselves rather than repeating the
# harness constant here, so the two cannot drift apart.
def _ceiling_label():
    import csv as _csv
    caps = []
    try:
        with open(os.path.join(S, "short_sweep.csv")) as fh:
            for r in _csv.DictReader(fh):
                for f in ("gen", "prep"):
                    if r[f + "_rc"] == "124":
                        caps.append(int(r[f + "_ms"]))
    except (IOError, KeyError, ValueError):
        return "did not finish"
    if not caps:
        return "did not finish"
    m = max(caps) / 60000.0
    return "did not finish in %d min" % round(m) if m < 60 else \
           "did not finish in %.0f h" % (m / 60.0)


CEIL_LABEL = _ceiling_label()


def _failed(v, at):
    """the word for a failure, and for an abort the time it took to reach it.

    A bare "OOM" reads as a property of the file; "OOM after 35 min" says the run
    spent thirty-five minutes climbing before the cap refused it, which is the
    part a reader is trying to size.
    """
    s = {DNC: "&mdash;", CEIL: CEIL_LABEL, ABORT: "OOM"}[v]
    if v is CEIL and isinstance(at, int) and at > 0:
        # The ceiling is per run, not per campaign: this document's cells were
        # stopped at fifteen minutes, and the one added later at an hour. Taking
        # the longest of them for every cell would put an hour's patience on a run
        # that was given a quarter of one.
        m = at / 60000.0
        return "did not finish in %d min" % round(m) if m < 60 \
            else "did not finish in %.0f h" % (m / 60.0)
    if v is ABORT and isinstance(at, int) and at > 0:
        # minutes from a minute up, so the column does not mix "589 s" with
        # "12 min" and make the reader divide before comparing two aborts
        s += " after %d min" % round(at / 60000.0) if at >= 60000 \
             else " after %.0f s" % (at / 1000.0)
    return s


def fmt_ms(v, unit="s", at=None):
    if v in FAILED:
        return _failed(v, at)
    if unit == "ms" or v < 1000:
        return "%d ms" % v
    # Above ten minutes, minutes.  "2665 s" against "40.5 s" makes the reader do the
    # division, and the division is the point of the row.
    if v >= 600000:
        return "%.0f min" % (v / 60000.0)
    return ("%.1f s" if v < 100000 else "%d s") % (v / 1000.0)


def fmt_kb(v, at=None):
    if v in FAILED:
        # on a memory column the failure to name is the memory one
        return _failed(v, at)
    return "%.0f MB" % (v / 1024.0) if v < 1024 * 1024 else "%.2f GB" % (v / 1048576.0)


def ratio(a, b):
    """a / b as a times-figure, or None when either side is not a number."""
    if not isinstance(a, int) or not isinstance(b, int) or not b:
        return None
    return a / float(b)

def load_instance_demo(path=None):
    """The INSTANCE demo readings, as kind/key/value because the halves are
    shaped differently and none is a time series.

    Kinds: 'ladder*' the context table; 'proofs' the level-2 proof module's
    deterministic counts, produced by the probe-carrying binary; 'main' and
    'tip' its timings, medians over 'ab,reps' interleaved rounds of the base
    commit against the branch tip; 'ab' the run's own metadata, including
    whether the two obligation streams came out byte-identical."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "instance_demo.csv")
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            out.setdefault(r["kind"], {})[r["key"]] = int(r["value"])
    return out
