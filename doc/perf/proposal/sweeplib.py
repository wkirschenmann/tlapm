# -*- coding: utf-8 -*-
"""Merge commit_sweep.csv rows into one record per (point, corpus), one boot only."""
import os, csv, os, collections

S = os.environ.get("SWEEP_DIR", os.path.dirname(os.path.abspath(__file__)))

def load(path=None, boot=None):
    path = path or os.environ.get("SWEEP_CSV", os.path.join(S, "commit_sweep.csv"))
    raw = []
    with open(path) as f:
        for r in csv.DictReader(f):
            raw.append(r)
    if not raw:
        return {}, None
    boots = sorted({r["boot"] for r in raw})
    boot = boot or max(boots, key=lambda b: sum(1 for r in raw if r["boot"] == b))
    out = collections.defaultdict(dict)
    for r in raw:
        if r["boot"] != boot:
            continue
        k = (r["point"], r["corpus"])
        if int(r["m0_ms"]) != -2:
            out[k]["m0_ms"] = int(r["m0_ms"]); out[k]["m0_rc"] = int(r["m0_rc"])
        if int(r["m1_ms"]) != -2:
            out[k]["m1_ms"] = int(r["m1_ms"]); out[k]["m1_rc"] = int(r["m1_rc"])
            out[k]["rss_kb"] = int(r["rss_kb"])
        out[k]["sha"] = r["sha"]
    out = dict(out)
    # main is measured twice, at the start and the end of the campaign: the first
    # run of the campaign meets a cold page cache, so use the mean of the two and
    # keep the spread so it can be reported.
    spread = {}
    # snapshot the raw first-run rows before any filling, so the raw export can
    # show exactly what was measured under each label
    for k in [k for k in list(out) if k[0] == "c00"]:
        out[("c00_first", k[1])] = dict(out[k])
    # a main measurement recorded under either label counts as main's; when both
    # exist the point is their mean, when only one does it is that one.
    for cp in {k[1] for k in out if k[0] in ("c00", "c00b")}:
        a = out.setdefault(("c00", cp), {})
        b = out.get(("c00b", cp), {})
        for f in ("m0_ms", "m0_rc", "m1_ms", "m1_rc", "rss_kb", "sha"):
            if f not in a and f in b:
                a[f] = b[f]
    for (pt, cp) in [k for k in out if k[0] == "c00"]:
        b = out.get(("c00b", cp))
        if not b:
            continue
        a = out[(pt, cp)]
        for f in ("m0_ms", "m1_ms", "rss_kb"):
            if f in a and f in b:
                lo, hi = min(a[f], b[f]), max(a[f], b[f])
                spread[(cp, f)] = (hi - lo) / float(hi) if hi else 0.0
                a[f] = int(round((a[f] + b[f]) / 2.0))
    out["_spread"] = spread
    return out, boot


def load_iteration_latency(path=None, boot=None):
    """median iteration latency per point, in ms, from the warm-cache one-edit runs.

    Iteration latency is what a user waits after editing one proof step in a file
    whose fingerprints are all present: parse, elaborate, generate, check every
    obligation's fingerprint, report the hits, and prove the one that changed.
    Three runs per point; the median is used and the spread is available."""
    import statistics
    path = path or os.path.join(S, "iteration_latency.csv")
    if not os.path.exists(path):
        return {}, {}
    runs = collections.defaultdict(list)
    boots = set()
    with open(path) as f:
        for r in csv.DictReader(f):
            boots.add(r["boot"])
            runs[(r["boot"], r["point"])].append(int(r["ms"]))
    boot = boot or max(boots, key=lambda b: sum(1 for k in runs if k[0] == b))
    med, spread = {}, {}
    for (b, pt), v in runs.items():
        if b != boot:
            continue
        m = statistics.median(v)
        med[pt] = int(m)
        spread[pt] = (max(v) - min(v)) / m if m else 0.0
    return med, spread


def load_iteration_latency_chain(path=None, boot=None):
    """median warm iteration latency on the large private specification, in ms.

    Same protocol as the synthetic one, with two differences forced by the corpus:
    a real prover run leaves 641 of its 9 927 obligations unproved in this
    environment, and those are re-attempted on every warm run, which would make
    the metric measure prover time rather than tlapm.  So the proving range is
    restricted with `--toolbox lo hi` to the widest span containing no failure
    (3 773 obligations, 975 prover-proved and 2 798 trivial) while parsing,
    elaboration and generation still cover the whole 14 522-line module.

    Returns (median_ms, spread, reported, completed) per point; `completed` is
    False for a run stopped at the ceiling, where `reported` says how far it got
    out of 3 774."""
    import statistics
    path = path or os.path.join(S, "iteration_latency_chain.csv")
    if not os.path.exists(path):
        return {}
    runs = collections.defaultdict(list)
    boots = set()
    with open(path) as f:
        for r in csv.DictReader(f):
            boots.add(r["boot"])
            runs[(r["boot"], r["point"])].append(r)
    boot = boot or max(boots, key=lambda b: sum(1 for k in runs if k[0] == b))
    out = {}
    for (b, pt), rs in runs.items():
        if b != boot:
            continue
        ms = [int(r["ms"]) for r in rs]
        m = statistics.median(ms)
        done = all(int(r["rc"]) == 0 for r in rs)
        rep = max(int(r["proved"]) + int(r["trivial"]) for r in rs)
        out[pt] = (int(m), (max(ms)-min(ms))/m if m else 0.0, rep, done)
    return out
