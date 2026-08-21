# Adoption plan: what to take from this branch, in what order

This file answers one question: **starting from `main`, which changes
give the most performance per line of diff, and in what order should
they land.**  The branch's own history is chronological — it follows
what we were investigating — and that is *not* the order to adopt.
This is the reordered path, ranked by gain over modification size, with
the test and measurement protocol for each item.

Nothing here is a new claim: every number is one already recorded in
`NEXT.md`, `BASELINE.md`, `PARALLEL_PREP.md` or the per-commit sweep
(`_perf/sweep.csv`, `_perf/sweep_ffi.csv`).  What is new is the
ordering, the diff sizes, and the per-item protocol.

## How to read the numbers

**Metrics** (defined in `BASELINE.md`, all reproducible with
`test/perf/bench.sh`):

| | what it measures | why it matters |
|---|---|---|
| **M0** | parse + elaboration + generation (`-N`) | the floor of every interactive action, and the per-worker fixed cost of chunked runs |
| **M1** | full preparation, no prover (`--noproving`) | CLI throughput; the term that made large specs unusable |
| **M2** | fingertip (`--toolbox L L`) | "prove this one step" latency |
| **M3** | peak RSS during M1 | the OOM axis |
| **M4** | full run, real provers | the number a user feels |
| **LSP** | keystroke → diagnostics, scripted client (`test/perf/lsp_c0.py`) | the editor axis |

**Corpora**: `Synth_L300_S5_D50_C3` (1 800 obligations, public,
`test/perf/gen_synth.py`); an INSTANCE-heavy private spec (9 967
obligations, "Ffi" below); a 30k-line single-module private spec
(29 965 obligations, "monolith").  Only the synthetic one is
publishable; the others are calibration.

**Two measurement hosts** appear in the record: host A (16 cores, the
phase-0/1 sweep) and host B (4 cores, everything from the re-baseline
on).  Absolute values are only ever compared inside one host and one
boot.  Ratios inside a series are what carry over.

## The recommended path

Six steps.  Each is independently shippable and independently
measurable; each ends at a state where the test suite passes and the
dumps are clean.  Steps 1-3 are the ones with the extreme ratios: **293 added lines in six files** for most of the CLI and interactive gain.

```
1. latency floor      Deque + ENABLED scan + levels fast path        (+117/-74,  3 files)
2. throughput unlock  single-pass expand + the two prunes            (+133/-29,  1 file)
3. robustness         SIGTERM + early reap                           (+43/-1,    2 files)
4. interactive floor  LSP obligation pool + parser memoization       (+175/-33,  2 files)
5. the caches         prefix-resume for expand and normalize + oracle (+356/-51, 4 files)
6. optional verticals chunked CLI | forked LSP prover | scoped LSP modes
```

Why this order and not the branch's: the branch measured the micro-fixes
first because they were cheap to validate, and only reached the prunes
in phase 1.5.  But the prunes carry the memory unlock (×8.7 on peak
RSS) and half the throughput, so a maintainer evaluating the series
should see them early.  Conversely the prefix caches (step 5) are the
largest single diff on the branch and deliver less than the prunes —
they belong after, not before.

One real dependency constrains the order: **the facts prune extends the
definitions prune** (same function, same marking pass), so they land as
a pair.  Everything else in steps 1-5 is independent; the sweep
measured each in isolation.

## Ranked by gain over modification

Ratio is the headline gain divided by the diff size — a blunt
instrument, deliberately, because it is what decides what to review
first.

| # | change | files | +/− | headline gain | metric |
|---|---|---|---|---|---|
| 1 | `util/Deque`: nth / first_n / equal on rear-heavy deques | 1 | +37/−27 | **×8.2** M0 on Ffi (32.1 s → 3.89 s), ×8.8 M2 | latency |
| 2 | `fix`: kill timed-out provers with SIGTERM, not SIGHUP | 1 | +12/−1 | **×2.57** and −5.3 GB peak, in any run started with SIGHUP ignored | both |
| 3 | `backend/prep`: prune unreachable hidden definitions, then unreferenced hidden facts | 1 | +102/−16 | **×2.7** M1 (30.2 → 11.2 s), **×8.7** M3 (1.50 GB → 173 MB) | throughput |
| 4 | `backend/prep`: expand visible definitions in one pass | 1 | +31/−13 | ×1.45 M1, −17 % M3, and Ffi M1 goes from *timeout* to 458 s | throughput |
| 5 | `lsp`: sorted obligation pool instead of per-step `RangeMap.partition` | 1 | +100/−12 | **×5.2** keystroke on the monolith (59.7 → 11.5 s) | latency |
| 6 | `module/Elab`: linear ENABLED-axioms detection | 1 | +23/−18 | ×1.59 M0 on Ffi (3.74 → 2.35 s) | latency |
| 7 | `expr/parser`: memoize the two instances of each grammar rule | 1 | +75/−21 | ×2.4 keystroke (2.9 → 1.2 s) | latency |
| 8 | `util/property`: monomorphic pid equality, loop-based lookups | 1 | +43/−12 | −5..−6 % of *all* preparation, −8.2 % M4 monolith | throughput |
| 9 | `backend/toolbox`: single-pass expansion in the result printer | 1 | +18/−11 | ×4.3 on the warm (all-fingerprints-present) path | throughput |
| 10 | `expr/Levels`: stop the level cache pinning one context per obligation | 4 | +36/−1 | flat heap instead of monotonic growth | memory |
| 11 | `expr/Subst`: memoized index lookup for deep substitutions | 4 | +37/−3 | ÷2.1 on the expansion tail | throughput |
| 12 | `expr/Levels`: resolve reference levels without slicing the context | 1 | +57/−29 | ×49 on the analysis clock (with #6) | latency |
| 13 | `expr/Constness`: O(1) De Bruijn resolution | 6 | +69/−4 | −73 % of the deque walks in `add_constness` | throughput |
| 14 | `backend/schedule`: reap finished provers before launching | 1 | +31/−0 | removes spurious timeouts under slow preparation | correctness |
| 15 | `backend/prep`: prefix-resume caches (expand, then `Elab.normalize`) + differential oracle | 4 | +356/−51 | ×1.32 M1 synthetic, **×2.15** M1 Ffi (55.1 → 25.7 s) | throughput |
| 16 | `backend/schedule`: pull tasks from a stream | 3 | +57/−9 | removes the eager task array; the single-pass OOM unlock with #10 | memory |
| 17 | `cli`: `--chunks N --spawn P` | 9 | +392/−13 | **×2.24** M4 monolith (284.5 → 127.2 s) | throughput |
| 18 | `lsp`: forked in-process prover | 13 | +360/−36 | step verdict 5.1–7.9 s → **0.4–1.0 s** | latency |
| 19 | `lsp`+`module`: scoped fingerprint carry, scoped generation, scoped re-elaboration | 10 | +889/−128 | keystroke 11.5 s → **2.0 s** after #5 | latency |
| 20 | small independent micro-fixes: `Ctx` log lookup, smtlib regex hoisting, `app_ix` without allocation, identity-rebuild skip, obligation comments only when kept | 5 | +84/−23 | each below the noise floor individually; together they are the tail of the tier-1 ×1.35 | throughput |

Reading of the table: **items 1–9 are 441 added lines (−131) across
eight files** and cover the ×8 latency drop, the ×2.7 throughput and the ×8.7
memory reduction.  Items 15–19 are 2 000+ lines and each buys a
specific, smaller multiple.  If only one thing ships, it is #1; if only
one *day* is available, it is #1–#6.

## Per-item protocol

The same two protocols recur, so they are stated once.

**Test protocol T1 (output-preserving change).**  `dune runtest src` and
`dune runtest lsp` green; the `test/fast` fail-set unchanged (40/48 pass
without Isabelle — any change to that set is a regression, see
`BASELINE.md`); golden dumps **strict-identical** before and after, on
the synthetic family and both real corpora, with
`test/perf/obldump.sh` + `test/perf/oblcheck.py --strict`.  Both dumps
matter and they are different: the *generated* obligations ("to be
proved") and the *shipped* form (what the backends receive).

**Test protocol T2 (subset change).**  As T1, but the shipped dump is
checked with `--subset`: hypotheses may only be removed, the goal must
be identical, and no obligation may appear or disappear.  Plus a
real-prover run with **verdict parity at the locus level** — the same
obligations proved and unproved at the same source positions.  Used by
#3 and #4 only.

**Measurement protocol P1 (cheap, per commit).**  `test/perf/bench.sh`,
median of 3, on `Synth_L{100,300}` and the real corpora: M0, M1, M2, M3.
Solver-free, so it is reproducible and fast.  This is what
`_perf/sweep.csv` is.

**Measurement protocol P2 (per milestone).**  One real-prover run per
arm, `test/perf/monitor_run.sh` (per-verdict timestamps + RSS samples),
interleaved A/B on an otherwise idle machine, machine fingerprint and
boot recorded.  Absolute values compared only inside one campaign.
Reserved for the items whose gain is not visible solver-free (#2, #17).

**Measurement protocol P3 (interactive).**  `test/perf/lsp_c0.py`
scripted client: didOpen, then a keystroke inside a proof body, timing
to the diagnostics notification; plus **byte-identical notification
streams** between the old and new server as the correctness gate (that
gate is what caught two bugs in the LSP track).  Used by #5, #7, #18,
#19.

Per item, then, only what differs from the above:

* **#1 Deque** — `src/util/deque.ml`. T1, P1.  The gain is concentrated
  in M0/M2, so measure the *parse+elab* metric, not M1: on M1 it looks
  like ×1.14 and would be dismissed.
* **#2 SIGTERM** — `src/system.ml`.  T1 (no output change), and a
  dedicated gate: run the same spec **under `nohup`** before and after,
  counting live prover processes (`ps`) and peak RSS.  Before: 725 s,
  4.60 provers mean against a limit of 4, 6.86 GB.  After: 282 s, 0.43
  mean, 1.54 GB.  P2.
* **#3 prunes** — `src/backend/prep.ml`.  T2.  The `Opaque "__pruned__"`
  self-check is part of the change: a reachability bug surfaces as that
  opaque leaking into a shipped obligation, i.e. a failing proof, never
  as a silent miscompilation.  Note the Ffi anomaly in the record: on
  that corpus M1 got *worse* at this commit (458 → 842 s) while M3
  dropped 13.9 → 5.1 GB — the prune pays for itself only once the
  caches (#15) are in.  Do not adopt #3 without #15 if that corpus
  shape matters to you.
* **#4 single-pass expand** — `src/backend/prep.ml`.  T1 (the result is
  identical, only the number of rebuilds changes).  P1, and record that
  Ffi M1 completes at all: a timeout becoming a number is the real
  result.
* **#5 LSP pool** — `lsp/lib/docs/proof_step.ml`.  T1 + P3.  Claiming
  semantics must be preserved exactly (first claimer wins, claim =
  range intersection, duplicate ranges collapse); the notification
  stream gate is what proves it.
* **#6/#12 elaboration** — `src/module/m_elab.ml`, `src/expr/e_levels.ml`.
  T1, P1 on M0.
* **#7 parser** — `src/expr/e_parser.ml`.  T1 + P3.  Watch memory: the
  memo table is per-parse and must not outlive it.
* **#8 Property** — `src/util/property.ml`.  T1, P1 *and* P2: −5 % does
  not show above P1's noise on small corpora.
* **#9 printer** — `src/backend/toolbox.ml`.  T1, and the measurement
  must be a **warm** run (all fingerprints present) — on a cold run this
  change is invisible.
* **#10/#16 memory** — `src/expr/e_levels.ml`, `src/backend/schedule.ml`.
  T1, and the metric is the *shape* of the RSS curve over the run, not
  its peak: sample RSS with `monitor_run.sh` and check it is flat.
* **#11/#13 substitution and constness** — T1, P1, with
  `TLAPM_PREP_TIMES` to attribute the gain to the intended stage; a
  stage-level probe is what keeps these from being noise-fitting.
* **#14 early reap** — `src/backend/schedule.ml`.  T1; the gate is that
  no obligation is reported timed-out that was not before.
* **#17 chunks** — T1 for the sequential path (the flag off changes
  nothing), plus two dedicated gates: `CHUNK_PARTITION_EXACT` (the union
  of the ranges generates exactly the whole-file obligation set, at the
  same loci) and `CHUNK_VERDICT_PARITY_EXACT` (same failing loci).  P2.
  Note the correctness trap this replaces: hand-chunking with
  `--toolbox` silently drops obligations, because a proof's locus is its
  keyword while its obligations sit at the positions of the facts it
  cites (measured: 4 obligations whole, 2 in lines 1–6, **0** in 7–9).
* **#18 forked prover** — Unix only, and the fork hygiene is the
  substance of the change: reset signal dispositions, `clear_nonblock`
  after `dup2` (tlapm's printers die on `EAGAIN`), leave only through
  `Unix._exit`, parent reaps with `WNOHANG` and no systhreads.  P3, and
  the byte-identical stream gate is not optional here — an earlier
  version corrupted the parent's LSP stream mid-frame.
* **#19 scoped modes** — the gates are `GEN3_STREAM_IDENTICAL`,
  `GEN3_INSERT_STREAM_IDENTICAL`, `GEN3_GAP_STREAM_IDENTICAL`: the
  client-visible notification stream must be byte-identical to full
  recomputation, for a keystroke, an insertion and an edit spanning a
  gap.  Known limitation to carry: inner expression locations of reused
  units are stale by design (fingerprints are position-independent, and
  everything the client sees positionally is shifted) — the
  step-decomposition code actions need the same shifting before these
  modes become defaults.

## What not to port — measured negative results

Five things were tried and should not be re-attempted from this record.
They are here so the effort is not spent twice.

1. **Pruning before expanding** (`TLAPM_PRUNE_EARLY`, on the branch,
   default off).  85 % of every obligation's context is dead weight
   dropped by `prune_context` — but dropping it *early* rebuilds the
   context per obligation and destroys the physical prefix sharing the
   caches live on.  Monolith M1 **286 s → 911 s (×3.2 slower)**, with
   `expand_defs` 49 → 294 s.  The dead weight is free precisely
   *because* it is shared.
2. **Name-blind fingerprints.**  Merges 369 classes / 466 obligations on
   the monolith, and **3 of those classes have differing shipped
   forms** — one obligation's result would answer for a different
   problem.  Three counter-examples end it.
3. **Caching elaborated dependencies across versions** (LSP).  Worked
   mechanically, made the keystroke *slower* (6.1 → 10 s), the extra
   time inside the INSTANCE substitution.
4. **De-materialising the obligation array** (lazy generation, shipped
   as `TLAPM_STREAM_GEN`).  Correctness parity everywhere, **no
   performance or memory change**: contexts share their prefixes
   structurally, so retaining 30 k sequents was already nearly free.
   Keep it for what it is — the platform for range-scoped generation —
   not as a perf item.
5. **Overlapping preparation with prover waiting.**  `wait = 0.1 s` over
   259 blocking selects in a 273 s run: the provers are subprocesses and
   already overlap.  There is nothing to overlap.

And one design decision recorded rather than implemented:
**INSTANCE×EXTENDS deduplication** (20.5 % of context definitions on the
INSTANCE-heavy corpus).  The flat-world form — usage-filtered hoisting
with aliases — is fully designed in `INSTANCE_STUDY.md` and was
deliberately not implemented: elaboration is 1.99 s of a 190 s run on
that corpus (1.0 %), so the ceiling is 1 %, and the material it would
remove is in the shared prefix the caches already amortise.  It belongs
to the lazy-tree node design, where it is structural.
