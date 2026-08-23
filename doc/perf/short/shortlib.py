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

# the 17 measured points, and the pull request each commit belongs to
POINTS = ["p%02d" % i for i in range(18)]
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
]
ENDPOINTS = ["p00"] + [c[-1] for _, _, c in PRS]

OBL = {"tiny": 71, "synth100": 600, "synth300": 1800, "ffi": 9967, "mono": 29965}
CORPORA = ["tiny", "synth100", "synth300", "ffi", "mono"]


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

    # per (corpus, field), the boot carrying the most measured points
    def field_of(r):
        return "gen" if int(r["gen_ms"]) != -2 else "prep"

    tally = collections.Counter()
    for r in data:
        tally[(r["corpus"], field_of(r), r["boot"])] += 1
    line_boot = {}
    for (cp, fld, b), n in tally.items():
        k = (cp, fld)
        if k not in line_boot or n > tally[(cp, fld, line_boot[k])]:
            line_boot[k] = b
    # phase L supersedes a ceiling it was run to resolve, on the same line's boot
    longer = {(r["point"], r["corpus"]) for r in data
              if r["phase"] == "L" and r["boot"] == line_boot.get((r["corpus"], "prep"))}

    out = collections.defaultdict(dict)
    for r in data:
        fld = field_of(r)
        if r["boot"] != line_boot.get((r["corpus"], fld)):
            continue
        if r["phase"] != "L" and (r["point"], r["corpus"]) in longer \
                and fld == "prep" and int(r["prep_rc"]) == 124:
            continue
        k = (r["point"], r["corpus"])
        out[k]["sha"] = r["sha"]
        g, grc = int(r["gen_ms"]), int(r["gen_rc"])
        p_, prc = int(r["prep_ms"]), int(r["prep_rc"])
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
    boot = boot or max(boots, key=lambda b: sum(1 for k in runs if k[0] == b))
    used = {}
    for (b, cp, mt, pt), v in runs.items():
        if b != boot or len(v) < 3:
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
    # same shape.  What gives it away is the obligation count -- a real run of a
    # corpus reports the same number every time -- so a row that reports materially
    # fewer than that corpus's usual count is dropped rather than averaged in.
    usual = {}
    for cp in {r["_cp"] for r in raw}:
        counts = collections.Counter(r["_obl"] for r in raw if r["_cp"] == cp)
        usual[cp] = max(counts, key=lambda n: (counts[n], n))
    short = [r for r in raw if r["_obl"] < 0.9 * usual[r["_cp"]]]
    raw = [r for r in raw if r not in short]
    runs, boots = collections.defaultdict(list), set()
    rep = {}
    for r in raw:
        boots.add(r["boot"])
        k = (r["boot"], r["_cp"], r["point"])
        runs[k].append((int(r["ms"]), int(r["rc"])))
        rep[k] = r["_obl"]
    if not boots:
        return {}, None
    boot = boot or max(boots, key=lambda b: sum(1 for k in runs if k[0] == b))
    out = {}
    for (b, cp, pt), v in runs.items():
        if b != boot:
            continue
        if any(rc == 124 for _, rc in v):
            # keep the wall clock the ceiling was hit at, so the point can be drawn
            out[(cp, pt)] = (CEIL, 0.0, len(v), rep[(b, cp, pt)],
                             max(m for m, _ in v))
            continue
        ms = [m for m, _ in v]
        med = int(statistics.median(ms))
        sp = (max(ms) - min(ms)) / float(max(ms)) if max(ms) else 0.0
        out[(cp, pt)] = (med, sp, len(ms), rep[(b, cp, pt)], med)
    return out, boot


def load_keystroke(path=None, boot=None):
    """{point: (median_s, spread, n)} -- didChange to publishDiagnostics.

    A point measured at several repetition counts keeps the largest: the small
    effects were re-run at n = 10 precisely because n = 3 could not separate them,
    and pooling the two would put the weaker evidence back in.
    """
    path = path or os.path.join(S, "short_keystroke.csv")
    if not os.path.exists(path):
        return {}, None
    vals, boots = collections.defaultdict(list), set()
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["kind"] != "edit":
                continue
            boots.add(r["boot"])
            vals[(r["boot"], r["point"], int(r.get("n", 0) or 0))].append(float(r["seconds"]))
    if not boots:
        return {}, None
    boot = boot or max(boots, key=lambda b: sum(1 for k in vals if k[0] == b))
    best = {}
    for (b, pt, n), v in vals.items():
        if b != boot:
            continue
        if pt not in best or n > best[pt][0]:
            best[pt] = (n, v)
    out = {}
    for pt, (n, v) in best.items():
        med = statistics.median(v)
        sp = (max(v) - min(v)) / float(max(v)) if max(v) else 0.0
        out[pt] = (med, sp, len(v))
    return out, boot


def keystroke_ranges(path=None, boot=None):
    """{point: (n, lo, hi)} at the largest repetition count measured per point."""
    path = path or os.path.join(S, "short_keystroke.csv")
    if not os.path.exists(path):
        return {}
    vals, boots = collections.defaultdict(list), set()
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["kind"] != "edit":
                continue
            boots.add(r["boot"])
            vals[(r["boot"], r["point"], int(r.get("n", 0) or 0))].append(float(r["seconds"]))
    if not boots:
        return {}
    boot = boot or max(boots, key=lambda b: sum(1 for k in vals if k[0] == b))
    best = {}
    for (b, pt, n), v in vals.items():
        if b == boot and (pt not in best or n > best[pt][0]):
            best[pt] = (n, min(v), max(v))
    return best


def fmt_ms(v, unit="s"):
    if v in FAILED:
        return {DNC: "&mdash;", CEIL: "timed out", ABORT: "OOM"}[v]
    if unit == "ms" or v < 1000:
        return "%d ms" % v
    return ("%.1f s" if v < 100000 else "%d s") % (v / 1000.0)


def fmt_kb(v):
    if v in FAILED:
        # on a memory column the failure to name is the memory one
        return {DNC: "&mdash;", CEIL: "timed out", ABORT: "OOM"}[v]
    return "%.0f MB" % (v / 1024.0) if v < 1024 * 1024 else "%.2f GB" % (v / 1048576.0)


def ratio(a, b):
    """a / b as a times-figure, or None when either side is not a number."""
    if not isinstance(a, int) or not isinstance(b, int) or not b:
        return None
    return a / float(b)
