# The harness that produced the campaign

Three scripts and one LSP client. Each is resumable, stamps every row with
`/proc/stat btime`, and reports a run that did not complete as a return code
rather than as a number.

```sh
WORK=/scratch/campaign CORPUS=/path/to/corpora ./short_sweep.sh      # gen, prep, peak
WORK=/scratch/campaign                        ./short_iterlat.sh    # iteration latency
WORK=/scratch/campaign NRUN=10                ./short_keystroke.sh  # keystroke -> diagnostics
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

The warm-cache fixtures are the one part that cannot simply be re-run: each is a
`.tlacache` directory produced by proving the specification once to completion,
plus a copy of the spec with a single proof step edited. Building one for a
public corpus is a matter of running tlapm once and then touching one step;
building one for either private specification is not possible outside the
customer's tree, and those fixtures are not in this repository.

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
