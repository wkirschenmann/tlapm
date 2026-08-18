# Phase 4 design — bounding single-pass memory (task streaming + obligation release)

Status: design note, pre-implementation. Evidence base: doc/perf/SWEEP.md
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
