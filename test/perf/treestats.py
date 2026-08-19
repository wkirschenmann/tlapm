#!/usr/bin/env python3
"""Summarize a TLAPM_TREE_STATS trace (stderr of `tlapm -N`).

The probe (src/proof/p_gen.ml) emits one line per generated obligation:

    [TREE] ob depth=D ctx=C kind=K

and one enter/exit pair per step list (`Steps` node) of the proof tree:

    [TREE] enter depth=D base=B
    [TREE] exit depth=D delta=N

This script compares two cost proxies, counted in "hypothesis slots":

  flat  = sum over obligations of their full context size -- what the
          current flattening pays: every obligation carries (and every
          per-obligation pass walks) its whole context;
  dfs   = sum over Steps nodes of the hypotheses ADDED at that node
          (delta), plus the largest module-level base -- what a
          depth-first traversal that maintains one incremental context
          would pay: each hypothesis is processed once per tree node
          that introduces it, not once per obligation below it.

The ratio flat/dfs bounds the redundancy that a lazy, tree-addressed
context assembly could remove from the per-obligation preparation.

Usage: treestats.py TRACE_FILE
"""

import re
import sys
from collections import Counter


def main(path):
    ob_re = re.compile(r"\[TREE\] ob depth=(\d+) ctx=(\d+) kind=(\w+)")
    enter_re = re.compile(r"\[TREE\] enter depth=(\d+) base=(\d+)")
    exit_re = re.compile(r"\[TREE\] exit depth=(\d+) delta=(-?\d+)")

    n_obs = 0
    flat = 0
    ctx_max = 0
    depth_hist = Counter()
    kind_hist = Counter()
    n_steps = 0
    sum_delta = 0
    delta_max = 0
    base0_max = 0
    depth_max = 0

    with open(path) as f:
        for line in f:
            m = ob_re.search(line)
            if m:
                d, c = int(m.group(1)), int(m.group(2))
                n_obs += 1
                flat += c
                ctx_max = max(ctx_max, c)
                depth_hist[d] += 1
                kind_hist[m.group(3)] += 1
                depth_max = max(depth_max, d)
                continue
            m = enter_re.search(line)
            if m:
                d, b = int(m.group(1)), int(m.group(2))
                if d == 0:
                    base0_max = max(base0_max, b)
                depth_max = max(depth_max, d)
                continue
            m = exit_re.search(line)
            if m:
                n_steps += 1
                delta = int(m.group(2))
                sum_delta += delta
                delta_max = max(delta_max, delta)

    if n_obs == 0:
        print(f"{path}: no [TREE] ob lines found", file=sys.stderr)
        return 1

    dfs = sum_delta + base0_max
    print(f"trace              : {path}")
    print(f"obligations        : {n_obs}  ({dict(sorted(kind_hist.items()))})")
    print(f"steps nodes        : {n_steps}")
    print(f"max tree depth     : {depth_max}")
    print(f"obligations/depth  : {dict(sorted(depth_hist.items()))}")
    print(f"context size       : mean {flat / n_obs:.1f}   max {ctx_max}")
    print(f"delta per node     : mean {sum_delta / max(n_steps, 1):.1f}   "
          f"max {delta_max}")
    print(f"flat cost (sum ctx): {flat}")
    print(f"dfs cost (sum delta + module base): {dfs}")
    print(f"flat/dfs ratio     : {flat / max(dfs, 1):.1f}x")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
