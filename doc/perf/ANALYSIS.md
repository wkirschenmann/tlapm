# tlapm performance analysis — observations, expected effects, and an experiment plan

Status: working document. Companion to upstream issue
[tlaplus/tlapm#286](https://github.com/tlaplus/tlapm/issues/286)
("tlapm scales poorly on INSTANCE/refinement-heavy specs").
All file/line anchors refer to commit `4600b24` of this repository.

## 1. Problem statement

Two distinct pain points, one root family (per-obligation context size and
whole-file reprocessing):

**P1 — Interactive latency (LSP / toolbox).** In the VSCode extension every
interaction (cursor move, diagnostics pull, "prove step at cursor") re-parses
and re-elaborates the whole file *and all its `EXTENDS` dependencies*, twice:
once in the LSP server process, then again in the `tlapm` child it spawns.
On a ~30k-line module the per-interaction latency makes editing unusable.

**P2 — Full-run wall time and memory.** A reference workload proves in
~5×2 min when verified in 2k-line chunks (separate tlapm invocations), but a
single-pass run of the same file is still unfinished after 110 min. Prior
instrumented experiments on a ~30k-obligation module show resident memory
growing roughly linearly with emitted verdicts (~200–450 KB live per
obligation), OOM around 26k obligations on a 7.7 GB machine, and GC cost on
the resulting multi-GB heap slowing the run down — memory and speed are
coupled.

### Validity criteria (hard, for every change)

1. The full test suite passes (`make test`, including the cram test
   `src/tlapm.t` which asserts the exact `@!!` obligation stream).
2. Per obligation, the backends receive a **subset** of what they receive
   today: never more material, never a new obligation. "Fewer/less" is only
   allowed for explicitly-flagged pruning changes, and must still pass all
   proofs.
3. Every change is justified by a measurement, and its effect is measured.
4. Changes must be adoptable by upstream maintainers: one topic per commit,
   smallest possible diff, the invariant stated in the commit message.

## 2. Pipeline map and where time is charged

```
.tla file
  │ parse (alexer.mll + src/pars combinators)          clock: parsing
  ▼
Module.Save.complete_load  — EXTENDS/INSTANCE closure   clock: parsing
Module.Dep.schedule        — topo order + flatten
  │
  ▼
Module.Elab.normalize (src/module/m_elab.ml)            clock: analysis
  — anonymization, simplification, ENABLED scan,
    M_gen.generate → final_obs array (eager)
  │
  ▼
add_id / toolbox_clean range filter (tlapm_lib.ml:405)  clock: simplification
  │
  ▼
process_obs (tlapm_lib.ml:165)                          clock: interaction
  — Prep.make_task for ALL obligations (eager array)
  — per obligation: find_meth, add_constness,
    fingerprint, expand_defs + normalize, backend
  — Schedule.run: up to max_threads prover processes
```

Instrumentation gaps that must be fixed before optimizing (§6.1):

* `Clocks.gen`, `Clocks.fp_saving`, `Clocks.fp_compute` are declared but
  never started (`src/tlapm_lib.ml:25-63`): obligation *generation* is
  charged to `analysis`, and the real per-obligation preparation
  (expansion, fingerprinting) is charged to `interaction`, so today's
  `--timing` output cannot separate "prover time" from "tlapm prep time".
* `Timing` has no clock stack — `stop ()` resets to the ambient clock
  (`src/util/timing.ml:33-40`), so nested regions are misattributed.
* The LSP entry point `modctx_of_string` (`src/tlapm_lib.ml:670-693`) is
  not clocked at all: LSP-side elaboration time is invisible.

## 3. Observations (verified in code)

Notation: N = obligations in the file, D = context hypotheses per obligation
(observed: mean ~815, max ~1440 on a 30k-line module; ~2200–3400 on
INSTANCE-heavy refinement specs per issue #286), T = named theorems in scope,
k = visible definitions expanded per obligation.

### 3.1 Frontend / elaboration (dominates P1)

| id | observation | anchor | complexity |
|----|-------------|--------|------------|
| F1 | `check_enabled_axioms_usage#check_usable` rescans the whole context, with an O(N) `cx_front` slice per `Fact (Ix n)` hypothesis — and every named theorem contributes one such Fact — for every BY/OBVIOUS proof | `src/module/m_elab.ml:1035-1057`, called at `:1150`; Fact source `src/module/m_t.ml:161-164` | O(B·T·D) per module |
| F2 | The expression grammar is rebuilt at every token position: `expr_or_op` and the whole mutually-recursive combinator family are plain functions re-invoked by `resolve`, re-allocating ~10-way `choice` lists and fresh `Lazy.t`s per position. The `b` parameter has exactly 2 values and is inert (only used at `e_parser.ml:852`) | `src/expr/e_parser.ml:320-858` | large constant factor on parsing |
| F3 | Name resolution is a linear `Deque.find ~backwards` over the context per identifier occurrence | `src/expr/e_anon.ml:81,189,263` | O(occurrences·D) ≈ O(N²) |
| F4 | The `redundant` check uses a *forward* `Deque.find`; contexts are rear-built, so each call `List.rev`s the entire context | `src/module/m_elab.ml:1100-1104`, also `:196` | O(D) alloc per named statement |
| F5 | `hyps_of_modunit` is computed twice per module unit (once wasted in a debug-print argument), and `Expr.Subst.app_*` has no identity fast path for `Shift 0`, so each computation deep-copies the theorem sequent | `src/module/m_elab.ml:1081` vs `:1095`; `src/expr/e_subst.ml:30,192,196-201` | 2 deep copies per theorem |
| F6 | The `.xtla` serialized-module cache exists (keyed by source digest + tool version) but is dead code: only reachable via the `TLAPM_CACHE` env var, wired nowhere | `src/module/m_save.ml:113-179,328-343`; `src/params.ml:413-426` | every run re-elaborates all dependencies |
| F7 | `INSTANCE` expansion makes 6 whole-body passes, plus one whole-body substitution *per parameter* | `src/module/m_elab.ml:305-327,495-538` (acknowledged in comment `:337-343`) | O(instances·params·body) |
| F8 | Every named `THEOREM`/`LEMMA` becomes a **Visible** `Defn` (its full statement) in the context of *all* subsequent obligations; ordinary definitions are parsed Hidden | `src/module/m_t.ml:153-160` vs `src/module/m_parser.ml:44` | Θ(N²) total context material |

### 3.2 LSP / toolbox path (dominates P1)

| id | observation | anchor |
|----|-------------|--------|
| L1 | The only cross-request cache is one `Lazy.t` per document version; forcing it runs a full `modctx_of_string` (parse + elaborate file **and all deps**) and then fingerprints **every** obligation. The child `tlapm` then repeats the entire pipeline | `lsp/lib/docs/doc_actual.ml:42,54,64`; `lsp/lib/docs/proof_step.ml:558-570`; `lsp/lib/prover/prover.ml:111-150` |
| L2 | Server-side elaboration is never range-restricted (`tb_sl`/`tb_el` stay at defaults in the LSP process) | grep: no `Params` writes under `lsp/lib` |
| L3 | A range gate exists at obligation-generation time (out-of-range proofs produce no obligation), but statement+proof *elaboration* (anonymize, simplify, F1 scan) still runs for every theorem; and the three range predicates disagree (overlap vs containment vs off-by-one) | `src/proof/p_gen.ml:241-243`; `src/tlapm_lib.ml:274-282`; `src/module/m_gen.ml:103-106` |
| L5 | Under `--printallobs` (always set by the LSP), a fingerprint *hit* still pays a duplicate `expand_defs` + normalize just to print the message — `toolbox.ml` contains a verbatim copy of the expansion code | `src/backend/toolbox.ml:100-133` (dup of `src/backend/prep.ml:38-54`), called from `prep.ml:1550,1583` |

### 3.3 Backend / per-obligation preparation (dominates P2)

| id | observation | anchor |
|----|-------------|--------|
| B1 | The full task array is materialized before proving: `Prep.make_task` runs eagerly for all N obligations; `find_meth` rebuilds the whole context deque per obligation (destroying structural sharing); each task closure retains the rebuilt context plus two memoizing lazies (a constness-annotated copy, an expanded/normalized copy). All N coexist → this is the live-memory accumulation behind P2 | `src/tlapm_lib.ml:233-238`; `src/backend/prep.ml:1391,1471-1522` |
| B2 | `expand_defs` rebuilds the remaining sequent once per visible definition | `src/backend/prep.ml:38-54` via `:935` | O(k·D) deep copies per obligation |
| B3 | A fingerprint hit skips the expansion and the prover, but not `find_meth`, `add_constness`, or the fingerprint computation itself — a fully-cached run still pays ~3 full context passes + a full context copy per obligation | `src/backend/prep.ml:1512-1552` |
| B4 | Contexts are rear-built deques; every front traversal `List.rev`s the rear (O(D) + allocation), ~12 times per obligation across the prep passes | `src/util/deque.ml:26-35` |
| B5 | The post-run release of obligations (`Array.fill … dummy_ob`) is likely a no-op: sequents stay reachable via `Props.goal` (never removed) and `Props.obs` on proof *steps* (collection commented out), and the module stays in `mcx` | `src/tlapm_lib.ml:519`; `src/proof/p_gen.ml:232,259,440` |
| B6 | The fingerprint file is flushed and its table re-sorted on every single result | `src/backend/fpfile.ml:484-521` |
| B7 | `Schedule.run` asserts `max_threads < 100` while the default is the core count — latent crash on ≥100-core hosts | `src/backend/schedule.ml:114`; `src/params.ml:274` |

### 3.4 What does *not* exist today

* **No context pruning** anywhere (`grep prune src/ lsp/` is empty on this
  base). Building blocks exist: free-variable collection
  (`src/expr/e_collect.ml:25-38`, currently used only by the SMT encoder)
  and the reference-marking walk inside fingerprinting
  (`src/backend/fingerprints.ml:415-518`).
* **No cross-obligation reuse** in preparation: zero caches in
  `src/backend/prep.ml`.
* **No benchmark suite** and no instant backend reachable from the CLI
  (`Method.Trivial` exists at `src/backend/prep.ml:841-844` but `mk_meth`
  does not accept it; see §6.2 — `--noproving --printallobs` already covers
  the need).

## 4. Reference implementations and priors

The fork `qdelamea-aneo/tlapm`, branch `optimize-instantiation-prep`
(8 commits on top of this very base commit), implements a subset of the
fixes and reports these speedups (issue #286):

| spec (context size) | elaboration | full check |
|---|---|---|
| TaskProcessing2Theorems_proofs (652 hyps) | 1.9× | 5.9× |
| DiGraphTheorems_proofs (988 hyps) | 1.9× | 26× |
| GraphProcessing2Theorems_proofs (2332 hyps) | 7.1× | >46× |
| GraphProcessing3Theorems_proofs (3406 hyps) | 8.5× | >41× |

Mapping fork commits → observations above:

| fork commit | addresses | claimed invariant |
|---|---|---|
| `5c1ae25` expand_defs in one composed-substitution pass | B2 | output identical |
| `e360684` direct De Bruijn level lookup (no context slice) | e_levels cost inside analysis | output identical; analysis ≈ ÷2 |
| `6bb4a0b` linear ENABLED-axioms detection | F1 | output identical |
| `9f9c5cf` batch: smtlib regex memoization, `Ctx.index` map, `Deque.nth/first_n/equal`, `app_ix` counter, flatten shift-0 skip, tempfile-only comments, scheduler reaping | B4 + assorted | output identical |
| `4cc3aea` prune hidden definitions unreachable from the goal | new (pruning) | shipped subset |
| `01d3786` prune unreferenced hidden facts | new (pruning) | shipped subset |
| `edd0129` resume find_meth/add_constness/expand_defs from the previous obligation's physically-shared context prefix | B1 cost (not B1 retention) | output identical |
| `fd2d9ac` TLAPM_TRACE_DEFS context-statistics probe | instrumentation | inert |

Two important negative priors from instrumented runs *of that fork* on a
~30k-obligation module:

* Single-pass still OOMs (~26k obligations / 6.4 GB peak on 7.7 GB) even
  with chunked `Gc.full_major` — the fork's prefix caches reduce *time*,
  not the live accumulation (B1/B5 retention is untouched).
* Parsing+analysis is a ~14 s fixed cost per invocation regardless of the
  requested range — this is what every chunked invocation and every LSP
  interaction re-pays.

These two facts scope Phase 1 (reimplement fork ideas) as *necessary but
not sufficient*: P2 additionally needs B1/B5 (streaming + retention), and
P1 additionally needs F2/F3/L3/F6 (parse/elab cost and range gating).

## 5. Candidate transformations — cost and impact analysis

Grouped by increasing review difficulty. "Invariant" is what the golden-dump
checker must verify (§6.3): **strict** = byte-identical obligation stream and
shipped content; **subset** = shipped hypotheses per obligation are a subset,
goal identical, no new obligations.

### Tier 1 — local, output-preserving micro-fixes (each ≤ ~40 lines, one file)

| candidate | ref | invariant | expected effect | risk |
|---|---|---|---|---|
| `Deque.nth` without allocation; `first_n` sharing; `equal` physical short-circuit | 9f9c5cf split | strict | shaves O(D) allocs from every context lookup | very low |
| `Ctx.index` positional map | 9f9c5cf split | strict | log lookup in printing contexts | very low |
| smtlib: compile escaping regexes once | 9f9c5cf split | strict | removes 22 regex compilations per identifier | very low |
| `app_ix` spine walk with an int counter | 9f9c5cf split | strict | removes an alloc per Cons step in every substitution | very low |
| flatten: skip shift-0 whole-sequent rebuild | 9f9c5cf split | strict | one full copy less per obligation when nothing extracted | low |
| obligation comment in solver files only under `--debug tempfiles` | 9f9c5cf split | strict (solver input changes cosmetically — verify) | serial pretty-print removed per obligation | low |
| schedule: reap finished provers before task construction; refresh clock after select | 9f9c5cf split | strict | removes spurious timeouts under load (correctness of *measurement*) | low |
| F4: backwards `Deque.find` in `redundant` | new | strict | O(D) alloc per named statement removed | very low |
| F5: drop duplicate `hyps_of_modunit`; `Shift 0` identity fast path | new | strict | 2 deep copies per theorem removed; preserves sharing (prereq for prefix reuse) | low |
| B7: lift the `max_threads < 100` assert | new | strict | latent crash removed | very low |

### Tier 2 — targeted algorithmic fixes (50–150 lines, one subsystem each)

| candidate | ref | invariant | expected effect | risk / review notes |
|---|---|---|---|---|
| F1: two linear passes for ENABLED-axioms detection | 6bb4a0b | strict | removes the dominant O(B·T·D) elaboration term | result must be provably identical; the fork version is a direct model |
| De Bruijn level fast path | e360684 | strict | analysis ÷2 on INSTANCE-heavy specs (fork measurement) | fallback path must remain for non-annotated hyps |
| B2: expand_defs as one composed substitution | 5c1ae25 | strict | interaction −50 % on the fork's benchmark | the De Bruijn bookkeeping is the whole review; keep the fork's `bump`/`scons` formulation which mirrors `app_hyps` |
| F3: name→index sidecar for anon resolution | new | strict | removes O(N²) name resolution | sidecar must mirror every push; medium |
| F2: hoist the two parser-grammar instances | new | strict | large constant-factor cut on parsing | mechanical but wide diff in e_parser.ml; medium |
| B3: fingerprint-hit short-circuit (skip find_meth/constness on hit) | new | strict | warm runs ≈ free per cached obligation | needs fp computable before find_meth; medium |
| L5: single normal form for printing on fp hit | new | strict | removes duplicate expansion per LSP-displayed hit | low-medium |

### Tier 3 — behavior-preserving architecture changes (each needs a design note)

| candidate | ref | invariant | expected effect | risk |
|---|---|---|---|---|
| B1: stream tasks instead of materializing N closures (Schedule pulls) | new | strict (ordering of toolbox messages must stay stable) | removes the live-accumulation floor; P2 primary fix | medium |
| B5: drop `Props.goal`/`Props.obs` after reporting; keep only (id, loc, status, fp) for summaries | new | strict | makes memory release real; flat RSS | medium (must not break `--summary`/unproved reprint) |
| prefix-resume caches for find_meth/constness/expand_defs | edd0129 | strict | cold-run prep cost ÷ large factor (median >99 % shared prefix measured on the fork) | **hardest review** of the fork set; consider only after B1/B3 land, re-measure need |
| L3: unify range predicates; gate proof elaboration on range | new | fingertip dump = strict subset of full dump; full dump unchanged | fingertip stops paying O(file) elaboration | boundary semantics; keep old path behind a flag during bring-up |
| F6: in-memory (LSP) + `.xtla` (CLI) dependency cache | new | strict (cached vs cold compared explicitly) | removes per-interaction re-elaboration of dependencies | stale-cache bugs; digest keying |
| B6: buffered fingerprint writes | new | strict | removes per-result fsync+sort | crash-safety of the fp file on kill |

### Tier 4 — semantics-visible (flagged, subset mode)

| candidate | ref | invariant | expected effect | risk |
|---|---|---|---|---|
| prune hidden definitions unreachable from the goal | 4cc3aea | subset | smaller shipped sequents; encoder passes shrink | pruning is sound (a goal provable with fewer hypotheses is stronger) but can lose *provability*; `__pruned__` placeholder makes reachability bugs fail loudly |
| prune unreferenced hidden facts | 01d3786 | subset | on INSTANCE-heavy specs the dead theorem statements are the bulk of the context | same; must run post-expansion (the fork learned this: earlier placement broke ENABLED tests) |
| prune unreferenced **visible** definitions (extension; F8 mitigation) | new | subset | removes the Θ(N²) shipped material from named-theorem statements; measured elsewhere to move WF_-tainted obligations from Isabelle to SMT | needs BY DEF transitive closure; flag `--prune-visible`, off by default; full-context retry is an option |

Interactions to keep in mind:

* Prefix-resume caches (Tier 3) and task streaming (B1) are compatible —
  both follow document order — but the caches hold references to the
  *previous* obligation's context: with streaming, that is exactly one
  in-flight window, which is fine; with pruning enabled the prefixes still
  physically match because pruning happens later in the pipe.
* `Shift 0` fast path (Tier 1) preserves the physical sharing that both the
  level fast path and the prefix caches rely on. Land it first.
* Pruning changes the *shipped* content but not the fingerprint or the
  "to be proved" dump (fingerprints are computed pre-expansion,
  `src/backend/prep.ml:1503-1514`; pruning runs at the end of
  `normalize_expand`). The checker must therefore compare the **shipped**
  dump, not only the fingerprint dump — verify this property when
  implementing.

## 6. Experiment plan — decision guided by cheap measurements

Long solver runs are expensive (tens of minutes to hours) and noisy
(observed ±20 % wall-clock noise floor). The plan therefore uses a strict
measurement hierarchy: each level is only escalated when the cheaper level
justifies it, and full-solver runs are reserved for milestones.

### 6.1 Instrumentation to fix first (prerequisite)

1. Start `Clocks.gen` around obligation generation; add `fp_compute` /
   `fp_saving` starts; give `Timing` a stack; clock `modctx_of_string`.
   Gate: golden dumps byte-identical before/after (clock code must not
   change behavior).
2. Adopt the fork's `TLAPM_TRACE_DEFS` context-statistics probe (env-gated,
   inert by default): per module, obligation count, total/max context size,
   Defn visibility breakdown. This is the cheap predictor for
   context-dependent candidates.

### 6.2 Measurement levels

| level | tool | cost | what it answers |
|---|---|---|---|
| M0 static | `--toolbox 0 0 -N` counts; `TLAPM_TRACE_DEFS` stats | seconds | obligation set unchanged? context sizes? which specs are context-bound? |
| M1 no-solver | `--noproving --printallobs --toolbox 0 0 [--fpp]` | seconds–minutes | full prep pipeline cost (find_meth, constness, fingerprint, expansion — all forced, no prover). **This is the "instant solver" benchmark**; verified: `really_ship` returns before forcing the expansion unless `--printallobs` forces it for printing (`src/backend/prep.ml:1418-1431`). A `--method none` (`Schedule.Immediate true`) is only needed if the success/record path must be exercised. |
| M2 fingertip | N sampled `--toolbox L L` invocations at representative lines | tens of seconds | interactive latency; fixed-cost share (parse+elab) vs per-obligation share |
| M3 memory | M1 run with RSS sampling (`/usr/bin/time -v`, or 10 s `ps` sampling for curves) | = M1 | live accumulation slope (KB/obligation); flatness after B1/B5 |
| M4 full solver | real provers, whole file; chunked vs single-pass | 10 min–hours | end-to-end verdicts + wall time. **Milestones only**: baseline, after Tier-1+2, after B1/B5, after each pruning step. One interleaved A/B pair per milestone; compare verdict-indexed curves, not raw wall clock. |

Corpus: (a) synthetic generator (parameterized N lemmas × M steps × D
definitions × INSTANCE depth) for scaling *curves* at near-zero cost;
(b) one calibration campaign against real specs (armonik.spec modules and
the user's private monolith) to validate that the synthetic curves have the
same shape — after that, day-to-day decisions run on synthetics and M0–M2
only.

### 6.3 Mechanical validity: golden dumps + subset checker

Two dumps per run, keyed by obligation location:

* **Generated dump** ("to be proved" messages + `--fpp` fingerprints,
  emitted before any proving, `src/tlapm_lib.ml:426-442`): detects any
  change to the obligation *set* or statement.
* **Shipped dump** (the `normalized` message from `really_ship`,
  `src/backend/prep.ml:1418-1424`): the exact material sent to backends;
  this is where the subset criterion is checked.

Checker modes: `strict` (default; both dumps byte-identical) and `subset`
(generated dump identical; shipped hypotheses per obligation ⊆ baseline,
goal identical). Runs on: the repo test corpus (`test/fast`, `examples/`),
the synthetic corpus, and the calibration specs.

### 6.4 Decision tree (per candidate, before any M4 run)

1. **Is the candidate's cost term visible?** Check the fixed clocks (M1) and
   `TLAPM_TRACE_DEFS` stats (M0) on the target spec class. If the phase it
   targets is <10 % of the relevant budget, park it (this is how we avoid
   speculative Tier-3 work).
2. **Implement smallest version, checker in strict/subset mode on M0.**
   Any dump difference not explicitly intended → stop, understand, fix.
3. **M1/M2 before/after on synthetics** (3 sizes): require the predicted
   asymptotic change (e.g. F1: analysis becomes ~linear in file size;
   B2: prep time per obligation stops growing with D). A candidate that
   does not move its own predicted curve is reverted, whatever the
   wall-clock says.
4. **M3 for memory-targeting candidates** (B1/B5): slope must drop to ~0.
5. **M4 only at milestones**, interleaved A/B, verdicts identical required;
   report speedup with the noise floor stated.

Decision thresholds (go/no-go): a Tier-1/2 candidate ships if strict-clean
and non-regressing; a Tier-3 candidate needs ≥20 % on its target metric at
M1–M3 on the calibration class; a Tier-4 (pruning) candidate additionally
needs all M4 milestone proofs green with the flag on.

### 6.5 Planned experiment sequence (minimizing M4 runs)

| milestone | contents | M4 runs |
|---|---|---|
| E0 baseline | instrumentation + harness; record M0–M3 on synthetics + calibration specs; single M4 pair (chunked vs single-pass) on the reference workload | 2 |
| E1 output-preserving set | Tier 1 + Tier 2 landed (each gated at M0–M2) | 2 (one A/B pair) |
| E2 memory set | B1 + B5 (+ B6); M3 slope ≈ 0 required first | 2 — this is the "does single-pass now finish?" run |
| E3 pruning | 4cc3aea-style, then 01d3786-style, then visible-defs extension, each behind its flag | 2 per step, on the pruning-sensitive class only |
| E4 LSP/interactive | L3/L5/F6 — measured at M2 plus editor-level latency, no M4 needed | 0 |

Total planned full-solver budget: ~10–12 runs across the whole program,
instead of per-tweak trial and error.

## 7. Current status

* Phase 0 (this document, the instrumentation fixes, the harness, the
  review checklist) — in progress on branch
  `claude/tlapm-performance-optimization-ejlzq7`.
* Companion file: `doc/perf/REVIEW_CHECKLIST.md` (internal review gate
  derived from upstream review history).
