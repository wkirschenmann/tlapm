# The harness that produced the campaign

Six scripts and one LSP client. Each is resumable, stamps every row with
`/proc/stat btime`, and reports a run that did not complete as a return code
rather than as a number.

```sh
WORK=/scratch/campaign CORPUS=/path/to/corpora ./short_sweep.sh      # gen, prep, peak
WORK=/scratch/campaign                        ./short_iterlat.sh    # iteration latency
WORK=/scratch/campaign NRUN=10                ./short_keystroke.sh  # keystroke -> diagnostics
WORK=/scratch/campaign LONG_CORPUS=ffi        ./short_longtail.sh   # the extended clock
WORK=/scratch/campaign                        ./short_refresh.sh    # merge, regenerate, commit
```

`WORK` holds the scratch git worktree, one cached binary per commit, and the
CSVs. `CORPUS` holds the `.tla` files. Both default to paths inside a checkout
of this repository. The point list is derived from `main..tlapm-perf-short` at
run time, so adding or removing a commit does not need an edit here.

## What each needs

| script | inputs |
|---|---|
| `short_sweep.sh` | the corpora; builds each commit itself |
| `short_iterlat.sh` | a corpus directory **plus a warm fingerprint cache** and an edited copy of the spec |
| `short_keystroke.sh` | a spec, a line number inside a proof body, and `lsp_keystroke_client.py` |
| `short_longtail.sh` | a sweep CSV with stopped runs in it; re-uses the binaries `short_sweep.sh` cached |
| `short_refresh.sh` | the CSVs; merges them into the repository, regenerates the page, commits the data |
| `short_mono.sh` | one corpus, a point list, and the CSV; picks each point's clock from what the CSV already holds |

The warm-cache fixtures are the one part that cannot simply be re-run: each is a
`.tlacache` directory produced by proving the specification once to completion,
plus a copy of the spec with a single proof step edited. Building one for a
public corpus is a matter of running tlapm once and then touching one step;
building one for either private specification is not possible outside the
customer's tree, and those fixtures are not in this repository.

## The order the sweep runs in, and why a restart is survivable

The sweep iterates **corpus-outer, commit-inner**: it finishes one (metric,
corpus) line end to end before starting the next. That is not the natural
order -- commit-outer would build each binary once -- and it is the important
one, because a chart line is exactly one (metric, corpus) pair and absolute
timings are only ever compared *within* a line. Finish a line and it is usable
whatever happens next; interleave the lines and a machine that goes away
mid-campaign leaves every line half-measured and none of them comparable.

Two things follow from that, and both are in the reader rather than here:

* every row carries `/proc/stat btime`, and the reader picks the boot **per
  line** -- the boot that carries the most rows for that (corpus, metric) pair
  -- so a line completed before a restart is untouched by one after it;
* one fixed cell is re-measured every eight (phase `K`), which bounds drift
  within a boot and is what lets a restart-split campaign be compared at all.

Inside a line the commits run **tip-first**. If the pass is cut short, the
points that survive are the ones nearest the completing end, which are the
informative ones: a curve that stops before reaching `main` still shows the
step, whereas one that stops before reaching the tip shows nothing.

## What the ceiling is for, and what it is not for

`short_sweep.sh` bounds every run at 900 s. That is worth paying on a **first** pass
over a line whose shape is unknown: one point that never finishes would otherwise
consume the campaign. It is worth nothing on a point whose ceiling reading is already
in the CSV -- re-running it at the same ceiling before escalating costs 900 s to learn
what the longer run says anyway, and this campaign paid that bill once before noticing.

So choose the clock from what the CSV holds, not from the script's defaults: a point
already stopped at the ceiling starts at the long clock, and so does every point below
it on the same line, since a slower commit cannot be a quicker one. Only a point with
no history pays the cheap pass first.

## The extended clock

`short_longtail.sh` re-runs, on an hour, the stopped runs of one corpus, and it
decides which ones are worth it rather than running them all. Two estimates are
formed for each stopped run -- when it would finish, from the ratio between this
commit and the same commit on the public 1 800-obligation corpus where nothing
fails; and when it would abort, from extrapolating its own resident set to the
12 GB cap -- and the run is launched only if the sooner of the two lands inside
90 % of `LONG_T`. Rows land in phase `L` and the reader prefers them over the
ceiling row they replace. Memory aborts are never re-run: more time cannot help
a run that ran out of address space.

The estimator is a scheduler, not a measurement. On the one point of this
campaign where it said yes and the answer came back it predicted 1 937 s against
1 035 s measured -- it overestimates by about a factor of two, which is the safe
direction for a gate meant to avoid hopeless hours and the reason the threshold
is 90 % rather than 100 %.

## Where the ceilings are

`short_sweep.sh`: 600 s generation, 900 s preparation, 12 GB of address space
(`ulimit -v`), so a run that would take the machine down aborts and is recorded
as an abort. `short_iterlat.sh`: 900 s. Raise them with `GEN_T`, `PREP_T`,
`CAP`.

## The LSP client

`lsp_keystroke_client.py <server> <spec> <line> <n>` speaks the protocol
directly: `initialize`, `didOpen`, wait for `publishDiagnostics`, then *n*
`didChange` edits that insert and remove one space inside a proof body, each
timed to the `publishDiagnostics` that answers it. Nothing inside the server is
instrumented, which is the point — the figure is what an editor waits. Server
logs go to `$LSP_LOG_DIR`, or a fresh temporary directory.
