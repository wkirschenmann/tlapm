# Per-commit measurement, and why it is shaped this way

`per_commit_sweep.sh` builds one binary per commit of a branch and measures each
one on every corpus it is given.  It exists because group totals hide the two
things a reviewer most needs to know: which commit in a series actually carries
the gain, and which commit costs something.

Both metrics come from stock flags on a stock build — no probe, no patched
binary, nothing the measured commits introduce:

| metric | command | what it is |
|---|---|---|
| `gen` | `tlapm -N --nofp` | parse, elaborate, generate obligations, stop.  The floor of every editor interaction and the fixed per-worker cost of any parallel scheme. |
| `prep` | `tlapm --noproving --nofp` | the whole per-obligation pipeline with no prover launched, so the figure is prover-independent and reproducible without solvers installed. |
| `peak` | `/usr/bin/time -f %M` on the `prep` run | maximum resident set. |

## What the protocol protects against

**One boot.**  Absolute values are not comparable across container restarts, so
every row carries `/proc/stat` `btime` and the readers filter on a single boot.
A campaign split by a restart is not averaged — the seam stays visible, and the
straddling points get re-measured or reported as missing.

**Resume, not restart.**  Keyed on (phase, boot, point, corpus): an interrupted
campaign costs the point that was in flight, not the pass.

**The baseline is measured twice**, once at each end of the campaign, as `c00`
and `c00b`.  The difference between them is the drift the whole curve carries,
and it is not always small: the first run of a campaign meets a cold page cache,
which on small corpora shows up as ~17 % on `gen` while `prep` stays inside
2.5 %.  Charts that need a single baseline use the mean of the two and say so;
the raw table keeps both rows.

**A ceiling and an address-space cap, both reported as themselves.**
`PREP_TIMEOUT` stops a run that will not finish; `ADDR_CAP_KB` (`ulimit -v`)
bounds one that would otherwise take the machine down.  Neither is treated as a
measurement: a run that did not complete is recorded as such, never as a large
number, because a ratio against it would be fiction.  On a corpus where the
baseline does not complete, the honest chart is absolute throughput, not speedup.

**Pass order is chosen for interruption, not for tidiness.**  Small corpora
first, because they give the whole curve cheaply.  On large corpora, `gen` for
every point before any `prep`, and then `prep` from the tip backwards — the
points that do not complete are the baseline ones, so an interrupted campaign
still holds the informative half.

## Running it

```sh
WORKTREE=/tmp/sweep-wt \
CORPORA="synth1800:$PWD/bench/Synth_L300.tla large_chain:/path/Chain.tla" \
BASE=$(git merge-base main my-branch) BRANCH=my-branch \
OUT=sweep.csv ./doc/perf/sweep/per_commit_sweep.sh
```

A corpus whose name starts with `large` or `priv` goes through the two-pass
treatment above; anything else is measured in one pass.  Use a scratch git
worktree so the checkout of each commit does not disturb your working tree, and
keep the machine otherwise idle — `nproc` matters less than having no other
process competing for page cache and memory bandwidth.

`PER_COMMIT_SWEEP.md`, one directory up, is the output of one such campaign over
the 26 commits of the performance branch.
