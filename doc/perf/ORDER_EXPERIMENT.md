# Does the memory pair belong earlier in the order?

The proposal branch puts the two memory commits — the streamed task list and the
level-cache lifetime fix — at positions #5 and #17 of eighteen.  That order was
chosen by how the work happened, not by what the numbers say.  This experiment
tests moving them to position #2, immediately after the deque fix.

Three branches, each measured with the same protocol as the main campaign
(`gen` = `tlapm -N --nofp`, `prep` = `tlapm --noproving --nofp`, `peak` = maximum
resident set of the `prep` run, 900 s ceiling, 12 GB address-space cap, same
boot):

| branch | contents | commits |
|---|---|---|
| `perf-order-v1` | bugfixes + #1 deque + **(#5 stream + #17 level cache)** | 8 |
| `perf-order-v2` | v1 + #2 single-pass expansion | 9 |
| `perf-order-v3` | v2 + #4 prefix-resume caches | full branch minus the rest |

`v1` and `v2` are clean cherry-picks off `main`.  `v3` is the full proposal branch
with everything else reverted in one commit — cherry-picking the cache commits
without the pruning commits they were written on top of loses their own code, so
subtracting is the only mechanical way to get exactly that feature set.

## Results

| configuration | prep, 1 800 obl. | peak, 1 800 obl. | prep, chain | peak, chain | prep, 30k |
|---|---:|---:|---:|---:|---:|
| branch order: `main` | 51.0 s | 1.72 GB | > 900 s | — | aborts on memory |
| branch order: bugfixes | 50.9 s | 1.72 GB | > 900 s | — | aborts on memory |
| branch order: #1 deque | 45.0 s | 1.74 GB | > 900 s | — | aborts on memory |
| branch order: #2 expansion | 30.4 s | 1.42 GB | aborts on memory | at the cap | aborts on memory |
| branch order: #3 prunes | 8.95 s | 168 MB | 764.5 s | 4.88 GB | > 900 s |
| branch order: #4 caches | 6.39 s | 167 MB | 177.8 s | 4.17 GB | aborts on memory |
| branch order: #5 stream | 7.14 s | 154 MB | 179.9 s | 4.00 GB | 405.7 s |
| branch order: #17 level cache | 5.97 s | 76 MB | 144.8 s | 400 MB | 288.0 s |
| branch order: tip | 5.57 s | 76 MB | 146.4 s | 407 MB | 283.1 s |
| **v1** = bugfixes + #1 + (#5+#17) | **35.2 s** | **75 MB** | > 900 s | — | > 900 s |
| **v2** = v1 + #2 | **23.1 s** | **74 MB** | > 900 s | — | > 900 s |
| **v3** = v2 + #4 | **19.8 s** | **78 MB** | **418.4 s** | **453 MB** | > 900 s |

## What that says

**The memory result belongs at position #2, and the branch order hides that.**
`v1` reaches 75 MB on the 1 800-obligation corpus — the same figure as the branch
tip, 76 MB, with eight commits instead of twenty-six.  In the branch order that
number does not appear until #17.  Nothing between #2 and #16 contributes to it.

**Moving the pair forward removes the memory failure mode from the whole first
half.**  On the two large specifications, `main` aborts against the 12 GB cap on
the monolith, and #2 aborts on *both*.  `v1` and `v2` never abort: they hit the
time ceiling instead.  That is a strictly better place to be — the remaining
problem becomes "not fast enough", which the prunes and caches then address,
instead of "cannot run", which no amount of throughput work fixes.

**It also makes the next change faster.**  Single-pass expansion is 30.4 s in the
branch order and 23.1 s in `v2`, on the same corpus: it is no longer fighting a
1.4 GB heap.  The gain from a throughput change is larger once the memory change
is already in.

**The prunes are not what makes the refinement chain finish.**  `v3` completes it
in 418.4 s at 453 MB with *no pruning at all*.  The branch order credits the first
completion on that corpus to the prunes, and that is an artefact of the order:
what the chain needed was the memory pair and the caches.

**The 30k monolith does still need the prunes.**  `v3` hits the ceiling there;
only prune-carrying configurations complete it.  So the prunes remain necessary —
for that corpus — and they remain the largest single throughput item anywhere
(`v3` is 19.8 s on the synthetic where the branch's #4, which has them, is
6.39 s).

## Recommended order

1. **#0** the five bugfixes
2. **#1** deque lookups — latency, one file, output-identical
3. **#2** *(new)* the memory pair: streamed task list, then level-cache lifetime — two commits, one pull request
4. **#3** single-pass expansion
5. **#4** the two context prunes
6. **#5** the three prefix-resume caches
7. then the latency items that measure: linear ENABLED scan, memoized grammar
8. then the editor obligation pool, whose measurement is editor-side
9. then, optionally, the micro-fixes that no measurement separates from zero

Each of the first six is justified by a threshold crossed or a ratio well above
the noise floor, and the memory failure mode is gone after step 3 rather than
step 17.

## A note on the "progress" metric

The obvious metric for configurations that never finish is how far they get in a
fixed budget.  The first attempt counted the toolbox protocol's per-obligation
messages inside 300 s — and it was wrong: `@!!status:to be proved` is emitted when
an obligation is *generated*, not when its preparation completes, so the count
saturates in seconds on every configuration and says nothing about preparation.
It is recorded here as a rejected metric.  A count that means something needs a
marker emitted after preparation, which under `--noproving` only trivial
obligations produce; the honest version is a real prover run with a fixed budget,
counting terminal verdicts.

What did work as a progress signal is categorical rather than numeric: **which
failure mode** a configuration is in.  "Aborts against the memory cap" and
"exceeds the time ceiling" were both drawn as "did not complete" before this
experiment, and the difference between them is exactly what it measures.
