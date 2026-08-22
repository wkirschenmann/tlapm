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


if __name__ == "__main__":
    sweep, boot, _ = L.load_sweep()
    msgs = check(sweep)
    for m in msgs:
        print("LINECHECK " + m)
    if not msgs:
        print("LINECHECK clean")
