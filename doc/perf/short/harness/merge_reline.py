#!/usr/bin/env python3
"""Fold the chain re-measurement into the sweep, idempotently.

The re-measurement rows are written as phase L -- the extended clock -- for one
reason: an abort verdict transfers between machines and a duration does not.  The
cap is 12 GB wherever the run happens, so "the cap refused an allocation" is a
fact about the file; "it took 2547 s to get there" is a fact about the host.
Labelling the rows L lets every verdict the campaign settles reach the document
the moment it is measured, while its timings wait until the new boot owns the
whole line and the curve can be drawn from one machine.

Phase A -- the single anchor run taken before the plan changed -- is not folded.
It is kept in chain_reline.csv for the host factor and nothing else.

Run from anywhere; paths are relative to this file.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHORT = os.path.dirname(HERE)
SWEEP = os.path.join(SHORT, "short_sweep.csv")
RELINE = os.path.join(SHORT, "chain_reline.csv")


def main():
    with open(SWEEP) as f:
        rd = csv.DictReader(f)
        fields = list(rd.fieldnames)
        rows = list(rd)
    have = {tuple(r[k] for k in fields) for r in rows}

    with open(RELINE) as f:
        new = [r for r in csv.DictReader(f) if r["phase"] == "N"]

    added = 0
    for r in new:
        r = dict(r, phase="L")
        key = tuple(r[k] for k in fields)
        if key in have:
            continue
        have.add(key)
        rows.append(r)
        added += 1

    if not added:
        print("nothing to fold")
        return 0

    with open(SWEEP, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("folded %d row%s" % (added, "" if added == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
