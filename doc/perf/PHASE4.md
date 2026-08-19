# Phase 4 design — bounding single-pass memory (task streaming + obligation release)

Status: implemented and measured — see «Results» at the end of this file.
The probe-first bisection overturned the audit's prime suspects: the
accumulation was neither the task list nor the retained obligations but
the **level-memoization cache** (`src/expr/e_levels.ml`) pinning one
preparation context per obligation on long-lived shared syntax nodes. Evidence base: doc/perf/SWEEP.md
(addendum), doc/perf/BASELINE.md, and the user's monolith curves
(380 KB/verdict unpatched; 177 KB/verdict live floor surviving forced
`Gc.compact`; OOM at 17.5k/26k of 30k obligations on 7.7 GB; throughput
÷3 across a run). On this branch, FfiGrpc still retains ~475 KB/obligation
(4.7 GB peak for 9927 obligations) and the pre-pruning binary is
OOM-killed mid-run at 13.9 GB.

## Why the previous attempts could not finish the job

Two experiments (user-run, documented in SINGLEPASS_MEMORY_REPORT):

* *Lightening the `obs` array* (dummying proved slots) changed nothing:
  the sequents are co-referenced from the module's proof tree, so the
  array cell is not the owning reference.
* *Chunked task construction + forced `Gc.full_major`/`Gc.compact` per
  chunk* removed the dead churn (wall pushed 17.5k → 26k) but could not
  touch the live floor: compaction cannot reclaim what is still
  referenced.

Conclusion: the fix is reference surgery, not GC pressure. The success
criterion is a flat live curve **without any forced GC call**.

## Where the references live (audited)

1. `Props.goal`: a full sequent assigned to **every proof node**
   (src/proof/p_gen.ml:232) and **every step** (:285), never removed.
   Only reader: the proof pretty-printer (src/proof/p_fmt.ml:69-90),
   a debug facility.
2. `Props.obs` on `Use` **steps** (p_gen.ml:309): `Proof.Gen.collect`
   removes the property from proof nodes (:421) but the step case is
   commented out (:440) — step obligations stay attached to the tree,
   which stays attached to the module in `mcx` for the whole run.
3. The `obs` array in `process_obs` (src/tlapm_lib.ml): retained until
   the end for the summary collectors (:182-216) and for re-printing
   *unproved* obligations. Proved obligations (the vast majority) only
   need (id, loc, kind) at that point.
4. The task closures: `Array.to_list (Array.map make_task obs)`
   (tlapm_lib.ml:225-229) materializes every task — including
   find_meth's rebuilt context and the two memoizing lazies — before the
   first prover starts; Schedule drops each cell only as it is launched.

## Step 4.0 — locate before cutting (probe first)

The 177-500 KB/obligation live figure has never been attributed
precisely (the user's report flags memtrace as the missing step). Before
any surgery: an env-gated live probe (`Gc.stat`-based live words printed
every N verdicts through the existing record callback), plus memtrace if
it builds on this switch, on a short FfiGrpc run. Deliverable: a table
attributing live bytes to holders (obs array / Props.goal / step obs /
task closures / forced lazies). The 4a cut list is whatever this table
designates — not the audit's guess.

## Step 4a — release what the probe designates

Candidate cuts, pending 4.0 confirmation:
* strip `Props.goal` after generation (keep the p_fmt reader working by
  making the strip conditional on the debug flag that reader serves);
* reactivate step-obs collection (the commented p_gen.ml:440), keeping
  the LSP-relevant omitted-obs behavior of proof nodes intact;
* on a successful verdict, replace `obs.(id-1)` by a lightened
  obligation (id/loc/kind kept, sequent dummied) inside the `record`
  callback — unproved obligations keep their sequent for re-printing.

Gate: live-words curve flat at the probe; golden dumps strict-identical;
test suite unchanged.

## Step 4b — stream the task list

Add `Schedule.run_stream : int -> (unit -> task option) -> unit` — same
spin loop, the list pattern-match replaced by a pull — and feed it a
generator that builds `make_task obs.(i)` on demand, in document order
(the prefix-resume caches of the preparation stages assume sequence,
not co-residence, so they keep hitting). The existing
`try ... with Exit -> []` moves into the generator. Launch order — hence
the toolbox message stream — is unchanged.

Gate: RSS flat (≈ in-flight window) on monitor_run with **no forced GC
anywhere**; strict dumps; throughput independent of verdict index.

## Step 4c — fingerprint-hit short-circuit

With 4b, task construction is already lazy; reorder inside `ship` so the
fingerprint (still computed on the const-annotated obligation — the
digest definition must not change, existing .tlacache files must remain
valid) is consulted before find_meth runs; on a full hit, return the
cached verdicts without rebuilding the context. Gate: warm re-run of a
fully-cached module ≈ parse+elab time; dumps strict; fp files unchanged
byte-for-byte.

## Step 4d — buffered fingerprint writes

`fp_writes` flushes the channel and re-sorts the in-memory table on
every single result (src/backend/fpfile.ml:491-521). Buffer results and
flush every K verdicts / on the scheduler timer / on interruption paths;
sort once at consolidation. Gate: fp file byte-identical after a clean
run; crash paths still persist processed results.

## Phase gate (from SWEEP.md addendum)

Measured by test/perf/monitor_run.sh on the synthetic corpus, FfiGrpc,
and finally the user's monolith on the user's machine:
(a) RSS flat for the whole run, bounded by the in-flight window;
(b) throughput independent of the verdict index, lower-bounded by
today's small-chunk throughput. Plus the standing invariants: strict
golden dumps, unchanged test fail-set, full real-solver proof of the
synthetic corpus.

---

# Results

## 4.0 — attribution by differential bisection

The probe is `TLAPM_LIVE_STATS=<N>` (commit «tlapm_lib: env-gated
live-heap probe»): on every Nth verdict the record callback prints
`Gc.stat` live words and heap words. Cost: one `Gc.stat` per N verdicts,
inert without the env var. All runs below are M1
(`--noproving --printallobs --nofp --threads 1`) unless noted.

| exp | corpus | variable removed | live @900 (Abs) / @7000 (Ffi) | verdict |
|---|---|---|---|---|
| E2 (ref) | Abs | — | 142 MB, linear | baseline slope |
| E3 | Ffi | `--printallobs` (display retention) | 1546 MB, linear | exonerated |
| E1 | Ffi | prefix caches (`--debug noprepcache`) | 1598 MB, linear | exonerated |
| E5 | Abs | prefix caches | 145 MB, linear | exonerated |
| E4 | Abs | display retention | 142 MB, linear | exonerated |
| E6 | Abs | constness annotation + fingerprint computation | 136 MB, linear | exonerated |
| E7 | Abs | the whole `ship` body (no-op tasks) | **24.8 MB, flat** | growth is inside per-obligation preparation |
| E8 | Abs | level-cache **writes** (`e_levels`) | **27 MB, flat** | **culprit** |

E7 bounds the search: the obligation array, the proof tree
(`Props.goal`, step obs), the scheduler and the toolbox stream together
hold a *constant* ~25 MB on AbstractGrpc — none of them is the leak, so
the 4a cut list (release Props.goal / step obs / proved slots) is
**unnecessary and is parked**. E8 names the mechanism:

`E_levels.compute_level` memoizes each node's level in a mutable cell
(`exprlevel_cache` property) as `ELCache_full (cx, e.core, level)` — it
stores the **query context** `cx` for the hit-check. The cells live on
syntax nodes shared by the whole module, so they survive the obligation;
each prepared obligation re-fills thousands of cells with *its* context,
and those contexts (hundreds of KB each, chained through the module
graph) can never be collected. That is the ~150-500 KB/verdict live
slope, and it explains why the user's forced-`Gc.compact` experiment
could not reclaim it: the pins are reachable.

## The fix (commit «expr/Levels: stop the level cache pinning …»)

A registry of filled cells + `reset_caches ()` called at the top of
`Prep.ship`: within one obligation the memoization still hits (that is
where the sharing pays); between obligations the cells are emptied so no
context outlives its obligation. ~20 lines, no interface change beyond
the new `reset_caches` entry.

Bonus datum: on Abs M1, disabling the cache writes entirely (E8 binary)
is *faster* than the resetting cache (19.3 s vs 23.0 s) — the
memoization is a net loss in batch mode at today's hit pattern. The
conservative reset is what upstream should take first (strictly safer);
whether the cache pays anywhere (LSP?) is a separate question left open.

## 4b — streaming (commit «backend/schedule: pull tasks from a stream»)

`Schedule.run_stream` + a generator in `process_obs` replacing the eager
`Array.to_list (Array.map make_task obs)`. After the e_levels fix this
is a second-order saving (task closures were E7-exonerated as a *live*
holder), but it removes the up-front materialization latency before the
first launch and keeps at most one prepared task of lookahead.

## Gate measurements (FfiGrpc, real solvers, monitor_run.sh)

10 031 verdicts both sides; verdict stream parity checked by loc+status.

| | before (branch @ sweep-24) | after (phase 4) |
|---|---|---|
| wall | 204 s | 209 s (±noise) |
| RSS max | 4 903 MB | **439 MB (×11 lower)** |
| RSS at 25/50/75/100 % of run | 1738 / 2774 / 3847 / 4903 MB | 407 / 438 / 438 / 439 MB — **flat** |
| throughput Q1→Q4 (v/s) | 67.7 / 52.2 / 48.2 / 37.4 | 62.6 / 49.1 / 48.2 / 38.0 |

M1 live curves: FfiGrpc 195→1546 MB before, **97→100 MB flat** after;
AbstractGrpc 142 MB@900 before, **27 MB flat** after.

Two readings for upstream:
* Gate (a) is met with **no forced GC anywhere** — the fix is reference
  surgery, exactly what the chunk+compact experiment could not achieve.
  The user's 30k-obligation monolith OOM (7.7 GB) is projected to fit in
  well under 1 GB.
* The Q1→Q4 throughput decline is **unchanged** by a ×11 smaller heap,
  so on *this* corpus it is obligation-weight-driven (later obligations
  are heavier), not GC-driven. The GC-coupling story (rate ÷3) from the
  user's monolith should be re-measured there; the heap that caused it
  is gone.

Validation: strict golden dumps identical (smoke + Synth_L100), fast
suite same fail-set (40/48, all environmental), cram OK, real-solver
verdict sets loc+status-identical on FfiGrpc and AbstractGrpc.

## 4c/4d — measured, and mostly redefined by the warm-run profile

Steps 4c and 4d were designed against the audit's model of the warm
path. Measuring first (same discipline as 4.0) changed the picture.

**The warm run was slower than the cold run.** With every fingerprint
cached, FfiGrpc took **13 min 29 s** — versus 3 min 29 s for the cold
run with real solvers. Per-stage attribution (`TLAPM_PREP_TIMES`, plus
a new `find_meth` timer): all probed stages together account for 158 s;
`--timing` charges 880 s to the backend region. GDB stack sampling of
the live process attributed the missing ~700 s to
**`Toolbox.expand_defs`** (src/backend/toolbox.ml:100, comment:
«duplicates prep.ml»): the printer's private copy of definition
expansion still used the **quadratic** one-definition-at-a-time
algorithm that the phase-1 commit removed from `Prep.expand_defs`.
`print_old_res` calls it on **every cached-failure verdict** to
re-derive the obligation text for the toolbox message — 758 × a full
quadratic expansion of an INSTANCE-heavy context.

Fix: the same single-front-to-back-pass rewrite as `Prep.expand_defs`,
restricted to the printer's historical filter (visible `Operator`
definitions only) so the printed obligation is identical.
Controlled A/B (both binaries started from a byte-identical fingerprint
table): warm FfiGrpc **14 min 46 s → 3 min 25 s (×4.3)**, RSS 445 →
423 MB, and the toolbox block streams — obligation bodies included —
are **byte-identical**. This is also the L5 path from
ANALYSIS.md — under `--printallobs` the same quadratic expansion ran
for *successful* cached verdicts too, so interactive warm re-checks pay
it on every obligation.

**4c as designed (consult the table before find_meth) is parked.** The
probe bounds its whole headroom at ~40 s/run on this corpus (find_meth
7.1 s + add_constness 23.9 s + fingerprint 8.7 s), against a real
soundness risk: the digest is computed after `find_meth` annotates the
methods, so hoisting the lookup changes the digest's input — exactly
the invalidation the gate forbids. Not worth it at this ratio; the
remaining warm cost is now expansion for the cached-failure trivial
checks (~116 s), a candidate for a later, separately-gated skip.

**4d (buffered fingerprint writes) is parked as measured-unnecessary:**
`fp_saving` totals **0.265 s** for 10 031 verdicts — the audit's
"flush + re-sort per result" reading overstated the mechanism (the sort
is per-fingerprint on a tiny list, not the whole table).

## The residual within-run slope, attributed (monolith, 2026-08-19)

Every completed monolith run — phase 4 included, heap flat — declines
÷4 in throughput from Q1 to Q4 (163 → 41 v/s). Since the shape is
identical at 1.4 GB and at 12.8 GB of heap, GC was already excluded;
the remaining candidates were preparation cost (the context prefix
grows with document position) versus solver difficulty (later
obligations harder). The discriminating measurement: a solver-free M1
(`--noproving --printallobs --nofp --threads 1`) with per-block
timestamps.

**Verdict: preparation.** The prep-only pipeline reproduces and exceeds
the slope — **500 → 62 blocks/s (÷8)** across the document, wall
9 min 39 s single-threaded, RSS flat at 1.17 GB. Stage totals
(`TLAPM_PREP_TIMES`): elab_normalize 155.6 s, expand_defs 80.1 s,
action_frontend 72.9 s, add_constness 60.5 s, trivial_check 35.8 s,
fingerprint 17.3 s, find_meth 14.8 s, prune_context 14.4 s — 457 s of
579 s attributed. Note where the money is: **pruning itself costs
14 s; everything upstream of it walks the un-pruned context** (~815
hypotheses per obligation on this corpus, the statements of all prior
lemmas included, cited or not — see the user's lazy-obligation-tree
design note for the `hyps_of_modunit` mechanism that puts every named
theorem's statement in every later context as a Visible Defn).

Levers for the next phase, in measured order of promise: prune (or
select) the context **before** the expensive stages instead of after;
extend the prefix-resume idea to the stages that don't have it
(elab_normalize and action_frontend are the two biggest and neither
resumes); prune uncited visible definitions (phase 5); and the
structural fix — the depth-indexed cache stack from the
lazy-obligation-tree note (its step 1, isolable and
semantics-preserving).
