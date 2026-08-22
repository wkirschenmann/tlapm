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

    gen and prep are milliseconds, peak is kB.  main is measured twice, as p00
    at the start of the campaign and p00b at the end; the pair is kept apart so
    the drift the campaign carries can be reported instead of hidden.
    """
    path = path or os.path.join(S, "short_sweep.csv")
    raw = []
    with open(path) as f:
        for r in csv.DictReader(f):
            raw.append(r)
    if not raw:
        return {}, None, {}
    boots = {r["boot"] for r in raw}
    boot = boot or max(boots, key=lambda b: sum(1 for r in raw if r["boot"] == b))
    out = collections.defaultdict(dict)
    for r in raw:
        if r["boot"] != boot:
            continue
        k = (r["point"], r["corpus"])
        out[k]["sha"] = r["sha"]
        g, grc = int(r["gen_ms"]), int(r["gen_rc"])
        p, prc = int(r["prep_ms"]), int(r["prep_rc"])
        if g != -2:
            out[k]["gen"] = _verdict(grc) or g
        if p != -2:
            v = _verdict(prc)
            out[k]["prep"] = v or p
            out[k]["peak"] = v or int(r["peak_kb"])
    out = dict(out)
    # the two main measurements, and the drift between them
    drift = {}
    for cp in CORPORA:
        a, b = out.get(("p00", cp)), out.get(("p00b", cp))
        if not a or not b:
            continue
        for f in ("gen", "prep", "peak"):
            if isinstance(a.get(f), int) and isinstance(b.get(f), int):
                lo, hi = min(a[f], b[f]), max(a[f], b[f])
                drift[(cp, f)] = (hi - lo) / float(hi) if hi else 0.0
    return out, boot, drift


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
    runs, boots = collections.defaultdict(list), set()
    rep = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            boots.add(r["boot"])
            cp = ITER_CORPUS.get(r["corpus"], r["corpus"])
            k = (r["boot"], cp, r["point"])
            rc = int(r["rc"])
            runs[k].append((int(r["ms"]), rc))
            rep[k] = int(r["proved"]) + int(r["failed"]) + int(r["trivial"])
    if not boots:
        return {}, None
    boot = boot or max(boots, key=lambda b: sum(1 for k in runs if k[0] == b))
    out = {}
    for (b, cp, pt), v in runs.items():
        if b != boot:
            continue
        if any(rc == 124 for _, rc in v):
            out[(cp, pt)] = (CEIL, 0.0, len(v), rep[(b, cp, pt)])
            continue
        ms = [m for m, _ in v]
        med = int(statistics.median(ms))
        sp = (max(ms) - min(ms)) / float(max(ms)) if max(ms) else 0.0
        out[(cp, pt)] = (med, sp, len(ms), rep[(b, cp, pt)])
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
        return {DNC: "&mdash;", CEIL: "ceiling", ABORT: "aborts"}[v]
    if unit == "ms" or v < 1000:
        return "%d ms" % v
    return ("%.1f s" if v < 100000 else "%d s") % (v / 1000.0)


def fmt_kb(v):
    if v in FAILED:
        return {DNC: "&mdash;", CEIL: "ceiling", ABORT: "aborts"}[v]
    return "%.0f MB" % (v / 1024.0) if v < 1024 * 1024 else "%.2f GB" % (v / 1048576.0)


def ratio(a, b):
    """a / b as a times-figure, or None when either side is not a number."""
    if not isinstance(a, int) or not isinstance(b, int) or not b:
        return None
    return a / float(b)
