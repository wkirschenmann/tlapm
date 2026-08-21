# The proposal document, and how it is generated

`../PROPOSAL.html` is the self-contained document written to open the pull
requests: the problem, where the time goes, the mechanism the throughput items
exploit, the corpora and method, the curves, and then all nineteen pull requests
commit by commit.  It is a single file with no external assets, so it can be
opened from disk or handed to someone as-is.

It is generated, not hand-edited.  Sections 5 and 6 — the curves, the tables and
every number in the per-commit blocks — come from the sweep CSV and from `git`
itself, so they cannot drift from the branch:

| script | what it writes |
|---|---|
| `sweeplib.py` | merges the sweep CSV into one record per (point, corpus), filtered to a single boot |
| `mksec5.py` | section 5: the three charts and the per-pull-request table |
| `mksec6.py` | section 6: one block per pull request, one sub-block per commit — file list and per-file line counts read from `git show --numstat`, measurements read from the CSV |
| `mkmeasdoc.py` | `../PER_COMMIT_SWEEP.md`, the raw per-commit table, plus the chart data list |

```sh
SWEEP_DIR=doc/perf/sweep PROPOSAL_HTML=doc/perf/PROPOSAL.html \
  python3 doc/perf/proposal/mksec5.py
SWEEP_DIR=doc/perf/sweep PROPOSAL_HTML=doc/perf/PROPOSAL.html \
  python3 doc/perf/proposal/mksec6.py
SWEEP_DIR=doc/perf/sweep SWEEP_MD=doc/perf/PER_COMMIT_SWEEP.md \
  python3 doc/perf/proposal/mkmeasdoc.py
```

Each script replaces its own `<section>` in place and leaves the rest of the file
alone, so the prose sections are edited by hand and the measured sections are
never touched by hand.

## Two conventions worth knowing before reading the output

**A run that did not complete is not a number.**  The readers keep
*measured-and-did-not-complete* distinct from *not-measured-yet*: the first draws
a cross in a strip below the axis and prints "does not complete" or "aborts", the
second draws nothing and prints an em dash.  Without that distinction a chart
would assert a failure that was never observed, on a point the sweep simply had
not reached.

**Where the baseline does not complete, there is no ratio.**  On the two large
specifications `main` has no `prep` value at all, so the throughput chart is
absolute obligations per second rather than a speedup — a speedup would need a
denominator that does not exist.

## What the series colours mean

Colour is the corpus family, public synthetic or private specification; the
dashed line is the smaller of the two inside each family.  Both hues were checked
with the data-viz palette validator in light and dark mode — lightness band,
chroma floor, adjacent-pair CVD separation, normal-vision floor and 3:1 contrast
against the chart surface — and they are theme tokens, not literals, so they
adapt to the reader's theme.
