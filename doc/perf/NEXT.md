# Next phases — the prep slope, context selection, and the lazy tree

Status: agreed direction, pre-implementation. Evidence base: PHASE4.md
(«Results» and «The residual within-run slope, attributed») and SWEEP.md
addenda 3–4. This page fixes the *shape* of the next work items so that
the short term does not have to be rewritten by the long term.

## Where the branch leaves the problem

Single-pass on the 30k-obligation monolith: finishes in 7.5 min at
1.39 GB flat (was: unfinishable). Two measured facts define what is
left:

1. **The within-run slope is preparation, not GC and not solvers**: the
   solver-free pipeline declines 500 → 62 blocks/s (÷8) across the
   document at flat heap. Stage totals put `elab_normalize` (155.6 s),
   `expand_defs` (80.1 s), `action_frontend` (72.9 s) and
   `add_constness` (60.5 s) first; `prune_context` itself costs 14.4 s
   — everything upstream of it walks the un-pruned ~815-hypothesis
   context, cited or not.
2. **The flattening itself is not a measured bottleneck**: generation
   is ~6 s once per run, and the materialized obligations are part of a
   *constant* ~1.1 GB. Removing the flattening buys structure (range-
   limited generation, exact caches), not batch speed.

## The three work items and how they couple

### B0 — attribution by document position (probe, first)

Extend `TLAPM_PREP_TIMES` to bucket each stage's time by obligation-
index tranche. One question: which of the four big stages carries the
positional growth? Everything below is shaped by this answer.

### B1 — kill the Θ(N·D) rediscovery. Two routes, chosen by C3's fate

* *Opportunistic route*: generalize today's prefix-resume caches
  (pointer-equality rediscovery of the shared prefix) to
  `elab_normalize` and `action_frontend`. Smaller diff — but this code
  is **discarded** the day the lazy tree lands: in the tree walk there
  is nothing to rediscover, the descent stack *is* the prefix.
* *Structural route*: the depth-indexed cache stack (step 1 of the
  lazy-obligation-tree design note). Introduces path/depth information
  into preparation without touching generation; the lazy tree consumes
  it unchanged. Slightly larger diff, **zero throwaway**.

Decision rule: if the upstream conversation commits to the lazy tree
(C3), take the structural route even where the opportunistic one would
suffice. The opportunistic route is only justified if C3 is abandoned
or indefinitely remote.

### B2 — select the context before the expensive stages

Move the selection that `prune_context` already performs (the
citations are *applied at generation time* — cited facts are `Visible`,
the rest `Hidden` — so the criterion exists) **upstream of the
expensive stages**, so `elab_normalize`/`add_constness`/`expand_defs`
walk only the kept set. Hard constraint: the fingerprint is still
computed on the *unselected* obligation (digest invariance — existing
.tlacache files must stay valid).

Scope correction (review discussion, 2026-08-19): an earlier draft
claimed the `BY`-closure computation was representation-independent
and would survive the lazy tree. **That was wrong.** In the tree,
citation resolution is *addressing*, not closure-over-a-candidate-set:
module-level names are predecessor siblings at level 1 (an
incrementally-maintained name→node table cached in the current level-1
node); step references `x.<y>` are direct tree coordinates; the `USE`s
in force at each level are that level's predecessor siblings, in the
same per-level cache. The «build the superset, then filter» shape —
the bulk of a flat-world selection implementation — has no equivalent
in the tree and is throwaway.

What genuinely exists in both representations is the **assembly
contract**, three pieces: (1) De Bruijn renumbering of a sparse
sequent (today's `__pruned__` slots solve this); (2) the transitive
pull of *declarations* by occurrence — a fetched or expanded body
exposes free symbols whose declarations must ship, to a fixed point;
(3) the auto-methods (AutoUSE, sound-ENABLED) that discover
definitions beyond the citations. Plus the validation battery (subset
dumps, verdict parity), which carries over as C3's acceptance suite.

Consequence: B2's flat-world form is deliberately **minimal** — move
the existing prune earlier, harvest the ÷8-slope gain, and stop there.
Any effort beyond that goes into C3's assembly design directly, where
the per-level cache + direct addressing model is the specification.

### C3 — remove the flattening (the lazy tree, step 3 of the design note)

Deliberately last among the structural items:

* its memory motivation is gone (phase 4: flat heap without it);
* its batch-speed motivation was never measured (see fact 2 above);
* its unique remaining payoff is **interactive**: generate only what
  the requested range needs, with the context defined by construction;
* it is the only item that requires maintainer agreement *before* the
  code — it reshapes `m_elab`/`p_gen`, and the upstream review history
  is unambiguous about unagreed rewrites.

Known sub-problems, identified now: (1) the toolbox protocol announces
the total obligation count before proving — needs a cheap tree-counting
pass or a protocol evolution; (2) id/fingerprint stability — DFS
preorder is today's document order, lock it with a test; (3) re-printing
unproved obligations at end of run — regenerate on demand or retain
selectively; (4) the parallel launch window must keep document order so
the per-depth caches keep hitting.

What arrives at C3 already paid for, if B took the structural forms:
the depth-indexed caches (B1), the selection criterion and its
acceptance suite (B2), the streaming scheduler and light reporting
records (phase 4). C3 then reduces to: a lazy DFS generator over the
proof tree + the four sub-problems above.

## Phase B — what actually happened (2026-08-19)

The probe-first discipline rewrote this plan twice in one day. Results
on the 30k-obligation monolith, solver-free M1, per-3000-obligation
tranches (`TLAPM_PREP_BUCKETS`):

* **B0** (two probe commits) — findings: the O(D) *rediscovery* inside
  the existing prefix caches is negligible (8.6 s total), so **B1.0 and
  B1.1 as designed were dropped without writing them**; all the growth
  is semantic work on the divergent suffix (×15–29 per stage), whose
  average length itself grows ×4 (33 → 143 hypotheses, `TLAPM_PREP_SHARE`
  distribution); the fingerprint is position-flat (earlier suspicion
  withdrawn); `elab_normalize` had **no cache at all** and dominated.
* **B1.2** — prefix-resume cache for `Elab.normalize` (both passes
  exposed per hypothesis from `Expr.Elab`, folded in prep with the
  expand-cache pattern, separate slots for temporal/non-temporal):
  normalize 157 → 31.6 s (×5); the physically-shared normalized prefix
  also drops trivial_check 36 → 13 s and find_meth 15 → 7 s. Wall
  9:45 → 7:08.
* **Memo substitutions** — `app_ix` walks the Cons/Bump spine linearly,
  so the ~400-deep expansion substitution cost O(spine) per variable
  occurrence (GDB-sampled at e_subst's `go`). A `Memo` constructor
  (index→core cache on the substitution *value*, shared across
  obligations through the prefix cache) takes exp:tail 80 → 37 s and
  the wall to **6:26 (−34 % from the phase-B baseline)**.
* **Parked with mechanisms identified**: `const:tail` (59 s, grows ×18 —
  the constness visitor re-annotates genuinely-new suffix hypotheses
  with `Deque.nth` O(distance) `Ix` lookups; needs its own micro-probe
  before surgery); `action_frontend` (73 s, position-flat — runs on the
  *pruned* obligation whose nodes are rebuilt per obligation, so no
  cross-obligation sharing is available; ~2.4 ms/obligation of
  apparently intrinsic work).
* Standing gates passed at each commit: strict golden dumps (synthetic
  + AbstractGrpc, old binary vs new), fast-suite fail-set unchanged,
  real-solver verdicts loc+status-identical on FfiGrpc (9927/9927).
* **Functional equivalence of the normalize cache, validated three
  ways**: beyond the dumps (printed form) and the solver verdicts, a
  differential oracle (`TLAPM_CHECK_ELABCACHE=1`) runs every obligation
  through BOTH the cached fold and the original whole-sequent
  `Elab.normalize` and compares the resulting sequents with `Expr.Eq`
  (structural alpha-equivalence): **zero divergences over 31 597
  obligations** (the 30k monolith + AbstractGrpc). Known scope limit:
  `Expr.Eq` ignores node *properties*; the argument there is structural
  (both paths execute the same visitor code on the same nodes — only
  the inter-pass interleaving changes, and neither visitor's output
  properties depend on visit order; the one global (`current_at`) is
  saved/restored per `Except` node). A property-sensitive divergence
  would still be caught downstream by the byte-level dumps.

**B2-minimal is blocked as scoped, by the triviality check.** The plan
said «move the existing prune upstream of the expensive stages». The
code says no, twice: pruning runs on the backend path only because the
triviality check discharges support obligations by finding a fact —
*hidden ones included* — equal to the goal (comment at the prune call
site), and «the triviality check must be done after expanding
definitions» (comment at the trivial_ob site). Early selection would
flip some of today's `trivial` verdicts into solver runs: verdict
parity breaks and the solvers *receive obligations they do not receive
today* — against the hard subset criterion. A viable B2 needs a
pre-expansion, selection-compatible replacement for the triviality
scan; that is a design item for the C3 discussion, not a quick move.

## Phase C — first measurements (2026-08-19)

Instrument: `test/perf/lsp_c0.py`, a scripted LSP client driving the
real `tlapm_lsp` server (initialize → didOpen → timed didChange +
diagnostic-pull rounds, completion signalled by the pushed
`proofStepMarkers`/`publishDiagnostics` notifications, matched on the
document version).

* **F2 (parser grammar) — done.** The keystroke loop on a
  30 294-line module was ≈ pure parse; memoizing the two instances of
  each grammar rule (21 rules, bodies unchanged) cuts the parsing clock
  3.02 → 1.18 s (×2.6) and the measured keystroke loop 2.9 → 1.2 s.
  (Caveat recorded: those two loop numbers were taken with dependency
  resolution failing, which the harness now handles by making the
  stdlib visible; the CLI parsing-clock numbers are unaffected.)
* **The true keystroke cost, dependencies resolved** (FfiGrpc + its
  AbstractGrpc/stdlib chain): **~6.1 s per keystroke**, GDB-sampled at
  ~85-90 % inside per-obligation **fingerprinting** — the LSP
  re-fingerprints every obligation of the document at every version
  (ANALYSIS observation L1). That is the next interactive lever, ahead
  of everything else. Two designs, complementary:
  - **Fingerprint prefix cache — INVALIDATED by code reading
    (2026-08-19), do not attempt.** The serialization is not
    prefix-compositional, by the digest's own definition: hypothesis
    numbers are assigned at *first use* during the traversal (goal
    emitted first, `counthyp` mutating the stack entries), and only
    *used* hypotheses print their bodies — so the prefix's segment of
    the string is a function of the whole obligation (goal + tail
    included), not of the physical prefix. Caching it per prefix would
    change digests, which the .tlacache-compatibility gate forbids.
    Also checked: the printer's stack is already array-backed O(1) —
    no mechanical pathology to fix. The per-obligation cost (O(D) walk
    + used bodies, ~0.6 ms) is intrinsic to the digest definition.
  - **Version-diff gating** (LSP only): after an edit strictly inside
    a proof body, only that proof's obligations can change their
    fingerprints; everything else can carry the previous version's
    identity without recomputation. Needs the edit range (the server
    already receives it) mapped to the proof-step tree, and a careful
    staleness story for the proof-state carry-over. C2/L3 (gating
    generation itself to the range) then falls out of the same
    machinery.
* **C1 (elaborated-dependency cache): negative result, withdrawn.**
  The cache worked mechanically (15 dependencies seeded per keystroke,
  digest-validated) but made the loop *slower*: 10 s vs 6.1 s per
  keystroke, the extra time GDB-sampled in the INSTANCE substitution
  (`m_subst.app_modunits`) during the main module's elaboration. The
  mechanism of that slowdown is not understood (suspects: property or
  cache state carried by nodes shared across versions; heap locality),
  so the change was not kept. Data point for the C3 design: reusing
  elaborated dependency *values* across versions interacts badly with
  today's per-node mutable state — a fresh argument for the
  tree-with-addressing model over value-sharing caches.

## Ahead-of-phase decision probes (2026-08-19)

Optimization tracks are paused pending the team/maintainer discussion;
these two probes were run to put numbers on the table for that
discussion. Both are env-gated and inert by default; strict golden
dumps pass with the probes in the tree.

### Probe 1 — pre-expansion triviality recall (TLAPM_TRIVIAL_SPIKE)

B2 (context selection before expansion) is blocked by the triviality
check: today an `Ob_support` obligation is discharged as trivial by
`find_fact`, which matches the goal against *expanded* hidden facts.
Any pre-expansion selection must reproduce that check or lose it. The
probe evaluates the same triviality candidate (goal is TRUE, or
`find_fact` on the *unexpanded* const-annotated sequent) against the
ground truth (the real `Immediate true` result), per support
obligation, M1 mode:

| corpus | supports | pre∧real | missed pre | false pos | recall |
|---|---|---|---|---|---|
| monolith (timer_wheel) | 19 442 | 17 381 | 2 061 | 0 | 89.4 % |
| AbstractGrpc | 1 172 | 888 | 284 | 0 | 75.8 % |
| FfiGrpc | 7 263 | 5 225 | 2 038 | 0 | 71.9 % |

Two facts for the B2 discussion: (i) the pre-expansion check has
**perfect precision** — it never claims trivial what is not — so it can
safely *short-circuit* (discharge early, skip expansion entirely) with
no correctness risk; (ii) its recall is 72–89 %, so a B2 that replaces
the post-expansion check with it would send the 10–28 % remainder to
the solvers — a subset-criterion violation unless the post-expansion
check is kept as a second chance on the selected context. Also
noteworthy: on all three corpora **every** `Ob_support` obligation is
really trivial (zero non-trivial supports), i.e. the entire support
population is today pure preparation overhead with no solver work.

### Probe 2 — proof-tree shape (TLAPM_TREE_STATS)

The lazy-DFS design note's step-1 premise is that per-obligation
context cost N×D dwarfs the tree's incremental growth Σ Δ. The probe
logs, at generation time (`-N`, seconds per corpus), each obligation's
tree depth and context size, and each step list's entry size and added
hypotheses. `test/perf/treestats.py` summarizes:

| corpus | obligations | max depth | mean ctx | mean Δ/node | flat = Σ ctx | dfs = Σ Δ + base | ratio |
|---|---|---|---|---|---|---|---|
| monolith | 30 872 | 11 | 814 | 3.4 | 25 141 494 | 47 473 | **530×** |
| AbstractGrpc | 1 635 | 6 | 758 | 3.2 | 1 239 280 | 2 802 | **442×** |
| FfiGrpc | 9 967 | 7 | 1 288 | 3.5 | 12 832 657 | 13 931 | **921×** |

Reading: a proof step adds on average ~3.4 hypotheses to a context of
~800–1300 — the flattened pipeline re-traverses the whole context per
obligation while the tree only ever grows by Δ. The ratio is a bound
on the *redundancy in context traversal*, not a promised speedup: the
phase-B prefix caches already recover the sequential share of it (that
is exactly why they pay), and per-hypothesis costs are not uniform.
What the numbers establish for the DFS decision: the tree is shallow
(≤ 11), Δ is tiny and flat across corpora, and the depth-indexed cache
stack of the design note's step 1 would need at most ~11 slots — its
premise is validated on all three corpora.

### B2-lite: implemented, measured ≈ 0, withdrawn (2026-08-19)

Following the recall numbers above, the safe form of B2 was implemented
and measured: call the *unchanged* `trying_to_prove_true`/`find_fact`
predicates on `const_fp_ob` (the pre-expansion sequent that already
exists for fingerprinting) before forcing `normalize_expand`; on a hit,
`save_result` + `Immediate true` without ever expanding; on a miss,
fall through to the unchanged post-expansion check. Bypassed under
`--printallobs` (the printed body must keep its expanded form). The
short-circuit demonstrably fired (~17 k obligations on the monolith:
`exp:discover` 6.15 → 2.35 s, `trivial_check` 0.97 → 0.54 s) with
perfect verdict parity (49 408 toolbox result lines identical at loc
level). **Wall clock: 5:13 → 5:09 — no gain.** Every heavy stage was
unchanged: `exp:tail` ~44 s, `const:tail` ~58 s, `elab_normalize`
~43 s, `action_frontend` ~93 s.

The mechanism is instructive and now measured: with the phase-B prefix
caches, a support obligation's preparation cost is *marginal* — only
its Δ (~3 hypotheses) beyond the shared prefix. Skipping it does not
save the prefix work, because the next prepared obligation (the main,
whose context extends the supports') resumes from an older cache entry
and absorbs exactly the tail the skipped supports would have paid. The
work is conserved; only its attribution moves. In other words: **the
prefix caches already capture what B2-lite was after.** The code was
withdrawn (C1 precedent — negative results don't stay in the tree),
and the conclusion recorded here: skipping *preparation* of obligations
whose context is a prefix of a later obligation's context saves nothing
in a prefix-cached pipeline; per-obligation savings only exist for
work done *before* the caches (constness + fingerprint, ~86 s on the
monolith — the L1 lever) or in a world where the skipped subtree is
never *generated* (the lazy-DFS étape 3). B2's residual value is
therefore entirely inside the C3/DFS design, not on the current
pipeline.

### DFS prerequisite landed: obligation ids in document order

`P_gen.collect` used to visit a step list's QED subtree *before* the
steps, so obligation ids (positional in `final_obs`) were not in
document order — contradicting the lazy-DFS design note's premise that
"DFS pre-order = current numbering order". No lazy generator can
produce the QED first (its sequent is built from the context the steps
accumulate), so the collection order was aligned with generation order
instead: steps before QED. Verified: creation order (TREE probe, now
logging locs) equals id order position-by-position; strict golden
dumps byte-identical (`oblcheck` keys by loc); fast suite green.
Per-run obligation ids are renumbered by this change; fingerprints are
content-keyed and unaffected.

## Lazy DFS, étape 3 — concrete design (2026-08-19)

State of the note's plan after this session's measurements: étape 1
(depth-indexed cache stack) is subsumed — the single-slot prefix caches
already resume from the common ancestor prefix (consecutive DFS
contexts nest), and B0 measured the rediscovery they'd remove at 8.6 s.
Étape 2 (refcount release) is obsolete — phase 4's streaming scheduler
and light reporting records already hold RSS flat at 1.39 GB. What
étape 3 (lazy generation) still buys, stated honestly after the B2-lite
lesson: (i) the ~30 k retained sequents in `final_obs` (the bulk of the
remaining 1.39 GB), (ii) proving starts after the first theorem instead
of after full elaboration (~6 s on the monolith, more on bigger specs),
and (iii) the structural prerequisite for C3 (incremental LSP) and
étape 4 (tree-addressed context selection) — NOT single-pass wall time,
which is now dominated by main obligations' intrinsic tail work.

Where everything flows today: `M_gen.generate` visits module units;
per theorem it runs `P_gen.generate` (attaches obs to the proof tree)
then `P_gen.collect` (detaches them, now in document order), and
appends to a module-level list that `m_elab.normalize` freezes into
`final_obs`; `tlapm_lib` numbers it and feeds the phase-4 stream. Two
prerequisites are now in place: ids = document order (see above), and
the single choke point (`M_gen`'s accumulator) through which every
`final_obs` obligation passes — including the module-level `USE`
obligations from `mutate`, which never go through `collect` (so the
in-proof suppression filter (`Props.supp`) stays where it is; emission
at this boundary inherits it for free).

**Shape A (recommended): resumable generation at theorem granularity.**
Rewrite `M_gen.visit` as an explicit stepper: state = remaining units ×
accumulated context × partial body × summary; `step` processes units
until one yields obligations (a theorem or a mutate) and returns them.
The scheduler's `next()` pulls: when its buffer is empty, it advances
the stepper. No effects, no threads, no refcounts — the in-flight set
is bounded by one theorem's obligations plus the scheduler window
(monolith: ~72 obs/theorem mean). The `Final` module stage is assembled
when the stepper is exhausted, which happens before the last verdicts
return; the proof-tree DFS below a theorem stays eager. The LSP path
keeps a trivial accumulate-everything driver and is unaffected.

**Shape B (fallback): push-driven.** Generation keeps its current shape
and pushes into the scheduler through a bounded window. More invasive
in `schedule.ml` (a second entry discipline) and couples elaboration to
prover lifecycle; only worth it if Shape A's stepper rewrite of
`M_gen.visit` proves too disruptive.

Open decision points for the team/maintainer discussion:
1. `module.mli`: `final_obs` becomes empty (or optional) on the CLI
   proving path — type/API choice.
2. ~~The toolbox protocol announces the obligation count up front~~
   **RESOLVED (measured 2026-08-19):** a purely syntactic counting
   pre-pass — a proof-tree walk mirroring `generate`'s gating and
   `collect`'s suppression rules, building no sequent
   (`M_gen.count_obligations` / `P_gen.count_proof`) — reproduces the
   generated count *exactly* on all four corpora and costs **33 ms on
   the monolith** against 2.0 s for real generation (the earlier
   "~6 s" figure was the whole elaboration, not generation). The
   up-front total is therefore essentially free; the
   `TLAPM_COUNT_CHECK` probe in `Module.Elab.normalize` keeps the
   counter in lockstep with the generator.
3. Per-theorem granularity is proposed as final — going per-obligation
   inside a theorem would require re-splitting `generate`/`collect`
   (the supp filter and the Steps/QED dependency make creation-time
   emission subtle) for no measured benefit.

## Étape 3 implemented and measured (2026-08-19, TLAPM_STREAM_GEN)

The scheduler now pulls obligations straight from the generation
stepper (`TLAPM_STREAM_GEN=1`): ids assigned at emission in document
order, eager filters applied per emission, "to be proved" printed at
emission, the announced total from the counting pre-pass, sequents of
proved obligations dropped at verdict time, the module summary patched
at drain, and the `--strict` checks running after the drain with
identical messages and exit codes (verified, exit 11 both paths).
Eager fallback for `--summary`, `--check`, `--stats`, `--suppress`
and explicit targets. Default path byte-identical (golden dumps on
four corpora, fast suite).

Measured, eager vs stream on the same binary, real solvers:

| corpus | verdicts | wall e/s | max RSS e/s |
|---|---|---|---|
| monolith | 30 035 = 30 035 (loc parity) | 4:15.8 / 4:13.5 | 1.53 GB / 1.62 GB |
| FfiGrpc | 10 031 = 10 031 (loc parity) | 2:50.5 / 2:51.7 | 0.69 GB / 0.81 GB |

**Honest verdict: streaming delivers correctness parity and no
performance change — and the expected memory gain did not
materialize.** The premise that the materialized `final_obs` sequents
were the bulk of the remaining footprint is wrong on these corpora:
generated contexts share their prefixes structurally (one deque spine,
Δ≈3.4 hyps per node — the TREE probe numbers), so retaining 30 k
sequents is nearly free, and the streamed run's small RSS excess
(+5–15 %) is in GC-dynamics territory (interleaving generation with
prover forks). What étape 3 actually is, post-measurement: the
**architectural platform** for C3 — proving starts before generation
ends, nothing depends on a materialized obligation array anymore, and
the tree walk is now owned by a resumable stepper that an incremental
LSP can drive — not a CLI performance lever. This mirrors the B2-lite
lesson: on a structurally-shared pipeline, removing a *materialization*
saves only its marginal footprint, which sharing already made small.

## Strategic reviews with measurements (2026-08-19, tracks 1/2/4/5)

### Track 2 — context selection for the solvers: LOW CEILING here,
### needs user-infra data

Two measurements close this locally. (i) Sensitivity exists: joining
per-obligation solver `time-used` with shipped sizes on FfiGrpc (2 010
solver-proved obligations), mean time rises monotonically from 0.044 s
(smallest decile, 60 % instantaneous) to 0.190 s (largest decile,
11 % instantaneous) — ×4.3. (ii) But the total is small: 152.7 s of
solver CPU spread over 16 workers inside a 170 s wall = **~5 % of the
budget**; the critical path is the (sequential) preparation.
Composition check: a large shipped obligation is 39 top-level items —
34 `NEW` declarations (3 % of the characters) and 5 facts carrying
97 % — i.e. `prune_context` already cut hard, and what remains is the
proof's working assumptions, not deadwood. Étape 4 therefore buys
approximately nothing on this infrastructure. It can still matter on
a solver-heavy environment (Isabelle in the loop, harder obligations):
the decision measure to run there is the same time-used×size join on
a production run — cost ≈ zero, it reads existing toolbox output.

### Track 1 — incremental LSP: the pain quantified, the plan

Measured with the scripted LSP client on the 30 k-line monolith
(stdlib resolved, full-text sync): **didOpen → proof-step markers =
50.4 s; keystroke → diagnostics = 65.4 s then 57.2 s.** Unusable, as
reported — this is the axis where everything we built this phase pays.
Attribution carries over from the AbstractGrpc measurement (85–90 % of
the keystroke is fingerprinting every obligation of every version) and
scales with N, which is why the monolith is 10× worse than the 6.1 s
corpus. The plan, on the étape-3 platform: (1) drive the generation
stepper over the subtree touched by the edit instead of regenerating
everything — the stepper, document-order ids and the counting pre-pass
were built for exactly this; (2) fingerprint only the emitted-in-range
obligations; (3) carry proof state over for the rest — the optimistic-
display product decision that is already on the team/maintainer
agenda. Expected: keystroke bounded by parse+elab of the file
(~8–10 s in-process on the monolith today) once fingerprinting is
scoped, and by the touched subtree (~1–2 s) once generation is scoped:
**÷6 to ÷30**. Parsing then becomes the next wall (2.2 s on the
monolith even after the ×2.6 grammar fix).

### Track 1, first result (same evening): the monolith keystroke was
### not fingerprint-bound — it was a quadratic step/obligation
### association, now fixed: 59.7 s → 11.5 s (×5.2)

The TLAPM_LSP_PHASES probe corrected the attribution on the large
file: of a 59.3 s keystroke, parse+elab+generation was 4.2 s,
fingerprinting 9.9 s — and **~45 s was the proof-step tree build**:
`Proof_step.with_obs` ran `RangeMap.partition` over the whole
remaining obligation map for every step, O(steps × obligations) =
13 563 × 30 872 on the monolith. (On the smaller corpus this term is
negligible, which is why the earlier "85–90 % fingerprinting"
attribution — true there — did not transfer.) Replaced by a sorted
obligation pool with identical claiming semantics (first claimer wins,
claim = range intersection; binary search + bounded backward scan by
the longest obligation span; duplicate ranges collapse exactly as
RangeMap.of_list did). Gates: LSP unit tests green; full notification
streams (including the proofStepMarkers payloads) byte-identical
between the old and new server on the corpora. Keystroke now 11.5 s =
elab ~4 s + fingerprints ~7 s + tree ~0.2 s; the scoped-fingerprint
step of the track now targets the ~7 s, and incremental elaboration
(C3) the rest.

### Track 1, second result: scoped fingerprint carry-over — keystroke
### 4.2 s on the monolith (×14 overall), and the carry is EXACT

With `TLAPM_LSP_SCOPED=1`, an edit confined to one proof body carries
the previous version's fingerprints positionally for everything
outside the edited top-level step (30 851 of 30 872 on the monolith;
21 recomputed), because statements — the only thing later material
sees — are untouched and fingerprints are position-independent. The
keystroke drops 11.5 s → **4.2 s**, and the entire notification stream
is **byte-identical** to the full recomputation: for proof-body edits
the "optimistic display" question dissolves — the carry is sound, not
optimistic. Statement edits and module-level edits fall back to the
full computation (correct, still 11.5 s). What remains of the
keystroke is parse+elab+generation (~3.8 s) — exactly the C3
incremental-elaboration target; and the next cheap win is the
child-prover side (the on-demand prove request re-elaborates in the
child too).

### Track 1, third result: scoped generation — keystroke 3.3 s on the
### monolith (×18 overall), still byte-identical

`TLAPM_LSP_SCOPED=2` closes the loop the second result opened: when
the edit-scope analysis proves the edit is confined to one proof body,
the LSP now also *generates* only that step's obligations. The module
generator (`M_gen`) gained an optional per-unit filter
(`generate ?only` / `gen_stepper ?only`): a theorem whose locus falls
outside the edited window contributes its statement to the running
context — the only thing later material sees — but its proof is
neither elaborated nor collected. The LSP supplies the skipped
obligations itself, by carrying the previous version's obligations
whole (sequents included) at line-shifted ranges into the step-tree
pool. On the monolith: **21 obligations generated, 30 850 carried**,
elab_main(+gen) 2.5 → 1.6 s, keystroke 4.2 → **3.3 s** — ×18 from the
59.7 s starting point. Gate: the full 2-edit notification stream is
**byte-identical** to the mode-0 full recomputation
(`GEN2_STREAM_IDENTICAL`), and the 23 LSP inline tests (including a
new carry-over regression test) pass. (A one-obligation difference in
the carried/recomputed split vs mode 1 — 30 850+21 vs 30 851+21 — is a
boundary-counting artifact of which side claims the host step's edge;
stream identity makes it observably irrelevant.)

Keystroke attribution after mode 2: parse_main ~1.35 s, deps
~0.04 s, elab_main(+gen) ~1.6 s, tree+fp ~0.3 s. The floor is now the
*parse and context elaboration of the whole file*, which C3 proper
(incremental module contexts) would attack. The other measured target
is the child prover: one on-demand prove request costs **3.5 s**
launch-to-first-result, because the child re-parses and re-elaborates
the file from scratch — an in-process prove path (or a warm child)
is the next cheap multiple.

### Track 1, fourth result: forked in-process prover — step verdict
### 5.1–7.9 s → 0.4–0.6 s

Measured first: the spawned prove child costs **5.8–6.4 s wall on the
monolith before its first toolbox message** (parsing 2.4 s + analysis
3.8 s by `--timing`; the earlier 3.5 s figure was another corpus), and
scoped generation would win nothing there — `P_gen.generate` already
skips proofs outside the `--toolbox` range, so the child's cost *is*
the parse and context elaboration.  So the child model has a ~6 s
floor, and the fix is to not re-elaborate at all: with
`TLAPM_LSP_FORK=1` the server forks itself and the child proves the
already-elaborated obligations (`Tlapm_lib.lsp_prove`, copy-on-write
reuse), writing the exact toolbox protocol to the same pipe a spawned
child would.  Everything downstream — parser, events, SIGINT
cancellation, progress UI — is shared; the spawned path stays the
default and the fallback, and the socket transport (remote proof
server) is unaffected: the remote server forks on its own machine.
Measured at a scripted LSP client on the monolith: step verdict
**5.1–7.9 s → 0.4–0.6 s**; combined with mode 2, edit → verdict of a
carried, line-shifted step = 4.7 s + 0.44 s.

The hard part was keeping the forked child out of the inherited Eio
runtime: Eio's SIGCHLD handler runs Eio code when a solver exits, the
Eio-created pipe is O_NONBLOCK (tlapm's printers die on EAGAIN with
`Sys_blocked_io`), and an unwind into the runtime can do I/O through
inherited state — under the io_uring backend even into the parent's
own stdout, the rings being shared mappings (observed as foreign bytes
interleaved mid-frame in the LSP stream).  The child resets signal
dispositions, clears O_NONBLOCK after the dup2, and exits only through
`Unix._exit`; the parent reaps via WNOHANG in the read fiber and uses
no systhreads.  Gates: final markers and diagnostics byte-identical to
the spawned child, chained prove/cancel stable, 23 LSP tests + src
cram suite green.  A prerequisite fix landed separately: obligations
carried whole under mode 2 kept their previous version's inner
locations — stale coordinates for failure diagnostics, the details
panel and the prover-result match; they are now line-shifted at carry
time (regression-tested).

### Track 1, fifth result: scoped re-elaboration — keystroke 2.0 s
### (×30 overall), the parse is now 95 % of it

`TLAPM_LSP_SCOPED=3` removes the last elaboration cost: when the edit
is confined to one theorem, the previous version's **elaborated body**
is reused as-is and only that theorem is re-elaborated — by running
the ordinary `normalize` on a one-unit module against the two prefix
contexts the full pass would have built (elaboration context from
`hyps_of_modunit`, generation context replayed with the generation
semantics by the new `M_gen.context_after`; `normalize ?gencx` keeps
them apart).  The proof tree is patched the same way: previous
top-level steps reused with line-shifted ranges and obligations —
prover results included, so no fingerprint is recomputed for them —
and only the edited theorem's subtree rebuilt.

Monolith numbers (quiet machine): keystroke→diagnostics **1.8–2.2 s**
(was 3.3 s in mode 2, 11.5 s unscoped, 59.7 s at the start of the
track): parse_main 1.85 s + deps 0.04 s + elab_main **0.00 s** + tree
and host fingerprints 0.06 s.  Only the edited theorem's obligations
(~66 here) are generated and fingerprinted.  Combined with the forked
prover, edit → step verdict is **~3.2 s** end to end.

Coverage widening shipped with it: the carry baseline (tree + text +
elaborated module) survives versions that never parsed (rapid typing)
or failed to parse — the next good parse carries against the last good
version (measured 20.1 s → 2.0 s on an edit following a syntax-error
version); and, under mode 3 only, the host theorem owns the gap after
its proof, so appending a proof step or editing a trailing comment
stays scoped (33.7 s → 2.1 s) — sound because the reuse machinery's
shape checks reject any edit that actually introduces top-level
material there (verified: a new lemma in the gap falls back with a
byte-identical stream).

Gates, all on the 30k monolith: full notification streams
byte-identical to the mode-0 recomputation for same-length edits, line
insertion, line removal, chained patches, gap edits and the fallback
case (`GEN3_STREAM_IDENTICAL`, `GEN3_INSERT_STREAM_IDENTICAL`,
`GEN3_GAP_STREAM_IDENTICAL`); the carry regression test gains a mode-3
case (line-inserting edit, (loc, fp) parity against full recompute);
23 LSP tests and the src cram suite pass.  Known limitation (inherited
from carrying whole obligations, documented for the maintainer
discussion): expressions *inside* reused elaborated units keep the
line coordinates of the version they were elaborated in — everything
positional the client sees comes from tree ranges and obligation
wrappers, which are shifted, but the step-decomposition code actions
would need the same treatment before mode 3 becomes a default.

What remains of the keystroke is the whole-file **parse** (1.85 s of
the 2.0): the next multiple needs an incremental parser, a much bigger
lift.  The interactive loop is no longer preparation-bound.

### Re-baseline of the whole throughput campaign on a second machine

The measurement host changed under us (container restart): **4 cores
(Xeon 2.80 GHz), 16 GB**, where the earlier campaign had 16 cores.
Since `max_threads` defaults to `nproc`, that alone moved every
absolute number by 25-45 % — a fresh HEAD run read 301 s on the
monolith against the 235 s on record, which would have looked like a
regression.  Rule adopted: **absolutes only ever compare inside one
campaign, on one machine, on one boot**; the machine fingerprint is
now recorded with the campaign (`_perf/rb_machine.txt`).

The whole set of terminating runs was therefore re-measured in one
interleaved campaign on the new host (the runs that died of the
OOM-killer on the old host are not replayed — their outcome is taken
as reproducible and reported as such):

| binary | monolith (30 035 verdicts) | FfiGrpc (10 031) |
|---|---|---|
| base → #16 | (OOM on the old host) | 854 s, 1 175 verdicts, capped |
| #20 prune facts | (OOM) | 910 s, 5.2 GB |
| #21 prefix caches | 798 s, 12.6 GB | 293 s, 4.8 GB |
| #24 final | 724 s, 12.7 GB | 300 s, 4.9 GB |
| phase 4 | 544 s, **1.46 GB flat** | 271 s, 547 MB |
| phase B (prep caches) | 333 s | 236 s |
| étape 3 (pre-Property) | 317 s | 226 s |
| **HEAD** | **291 s, 1.36 GB** | 227 s |

Three things this campaign settles.  (1) The **Property commit** is
worth **−8.2 % on the monolith** (317 → 291 s) and **neutral on
FfiGrpc** (226 → 227 s) — consistent with the −5..−6 % A/B on
preparation alone, amplified on the monolith because that run is
preparation-bound.  (2) That bound is now measured directly: monolith
HEAD only loses **×1.24** going from 16 to 4 cores, so the single-pass
run is dominated by single-threaded preparation, not by solver
parallelism — which is also why the remaining CLI work has to be
preparation work.  (3) `#21`/`#24` **complete** on a 16 GB host
(12.6-12.7 GB peak) but at 2.5-2.7× HEAD's wall time with the
characteristic decay (61-66 → 24-27 v/s across quartiles), while
phase 4 walks the same corpus at 1.46 GB flat: the heap→throughput
coupling is a throughput fact, not only a survival fact.

### Track 4, follow-up: Property lookups made cheap; representation
### left upstream

The one cross-cutting target the profile exposed got its
non-intrusive half: monomorphic pid equality and loop-based
has/get/query in `util/property.ml` (output-identical; strict golden
dumps, both suites green).  Whole-module preparation on the monolith,
two interleaved before/after pairs: 199.1/201.7 s → 188.8/188.9 s
(**−5..−6 %**), same peak RSS.  The representation change itself
(dedicated slots for hot properties) remains upstream-discussion
material — the argument and options are written up in
`UPSTREAM_NOTES.md` together with the INSTANCE×EXTENDS deduplication
and the pre-expansion-triviality record.

### Track 4 — CLI grinding: no local hotspot, one cross-cutting one

Stack-sampling the whole monolith preparation (60 samples, innermost
attributed frame): `Property` 22 %, `E_visit` 17 %, `Prep` 12 %,
`E_subst` 12 %, `Fingerprints` 10 %, then a long tail (`E_levels`,
`E_tla_norm`, `E_constness`, `Coalesce`…). Verdict: the action
frontend's 93 s hides no dominant fixable loop of its own — its cost
is the same generic machinery as everywhere else. The one broad
target the profile exposes is **property-list lookups** (`Property.query`
walking per-node association lists on every visit): ~a fifth of
preparation across all stages. A representation change (hot properties
in dedicated slots, or interned pfuncs) could plausibly buy ×1.2–1.4
on the whole preparation — but it touches the core wrapper type used
by every file of the code base, the opposite of a granular reviewable
change. Classified: upstream-discussion material, not a branch
experiment. Everything else on this axis is confirmed intrinsic.

### Track 5 — C3: what exists, what's next, expected shape

Everything C3 needs as groundwork now exists and is measured: the
resumable stepper with document-order ids (étape 3, landed), the
proof-tree shape numbers (Δ≈3.4, depth ≤ 11, flat/tree 442–921×), the
INSTANCE node design (export table, parameter-free hoisting — the
study), the fingerprint semantics (usage-scoped invalidation, not
prefix-compositional), and two negative results steering it (value
caches across versions interact badly with per-node mutable state;
de-materialization alone saves nothing that structural sharing hadn't
already). The realistic expected gains, stated against those bounds:
CLI single-pass ≈ nothing further (the caches already capture the
sharing); interactive = the real prize, delivered through track 1
which is C3's first vertical slice. Recommended next concrete step:
prototype the LSP→stepper path (range-scoped generation +
fingerprinting) as the C3-lite vertical, ahead of phase, feeding the
optimistic-display discussion with a working demo instead of a design
note.

### A robustness bug found by accident: SIGHUP, `nohup`, and provers
### that outlive their own timeout (2026-08-20)

Found by contaminating a measurement: the first occupancy run of the
30k monolith was launched under `nohup` and took **725 s instead of
285**, with a mean of 4.60 concurrent provers against a limit of 4, a
peak of 8, and a peak RSS of 6.86 GB held by a single `z3`.

Mechanism.  `System.unix_kill` sent **signal 1**, and it is the only
place in the CLI that kills a prover.  SIGHUP means "the controlling
terminal went away", so launchers set it to `SIG_IGN` — that is exactly
what `nohup` does — and unlike a handler, `SIG_IGN` is inherited across
both fork *and* exec.  A tlapm started that way cannot kill anything it
spawns: the deadline fires, the timeout is announced, the scheduler
slot is freed, and the prover keeps running.  Confirmed directly: a
child's `SigIgn` mask carries bit 0 under `nohup` and not otherwise,
the leaked `z3` processes ignored SIGHUP for ten minutes, and a plain
SIGTERM killed them instantly.

Fixed by sending SIGTERM (one line).  The gate is the accident itself —
the same run, under `nohup`, before and after:

| sequential run, `--nofp`, one boot | wall | provers mean/peak | peak RSS | failures |
|---|---|---|---|---|
| started normally, before fix | 284.5 s | 0.38 / 3 | 1.46 GB | 958 / 29 965 |
| under `nohup`, before fix | **725.2 s** | 4.60 / **8** | **6.86 GB** | — |
| under `nohup`, after fix | **282.2 s** | 0.43 / 4 | 1.54 GB | 958 / 29 965 |
| | | | | |

The third row is within 0.8 % of the first and the prover count no
longer exceeds `max_threads`: the penalty is gone, ×2.57 in that
configuration, −5.3 GB of peak RSS, and no leftover process after the
run.

Two consequences worth carrying.  **For users**: any tlapm run with
SIGHUP ignored — `nohup`, a detached or daemonised run, some CI and
batch harnesses — silently lost its prover timeouts before this fix,
which makes it a candidate explanation for part of the single-pass OOM
history: what grows is not tlapm's heap but forgotten solvers at
several GB each.  **For the code**: escalation is still missing (SIGKILL
after a grace period, for a backend that traps SIGTERM), and it needs
the scheduler to remember the pids it killed — a separate change,
noted, not done.

### Occupancy measured: the CLI run uses 1.54 cores of 4 (2026-08-20)

Full table and interpretation in `PARALLEL_PREP.md`.  Summary: the
sequential run consumes 374 of the 1 138 available core-seconds, has no
prover alive in 70 % of samples, and never reaches its own
`max_threads = 4` cap; `--chunks 16 --spawn 4` takes it to 3.88/4 and
127.2 s (×2.24, same 958 failures).  Parallelising the producer
multiplied prover concurrency by 3.8 — the provers were the
consequence, not the constraint.  Two hypotheses of ours died here: the
process primitives are negligible (10 437 forks + `/bin/sh` execs cost
4.2 s of 258.9 s) and the per-worker redundant parse is ≈ 3 s, not the
43 s previously assumed.

### Pruning before expanding: measured, x3-4 SLOWER, withdrawn (2026-08-21)

The question was whether the lazy tree's "only what is used
materializes" is portable to the flat pipeline.  It measures as a clear
negative, and the reason is worth keeping.

`prune_context` drops **85 % of every obligation's hypothesis slots**
(10.15 M of 11.88 M on the monolith, 2.28 M of 2.68 M on Ffi -- new
counters under `TLAPM_PREP_TIMES`), and it runs after `expand_defs`,
`Expr.Elab.normalize` and the triviality check, all of which walk the
whole context.  `expand_defs` alone is 18 % of the monolith's
preparation and **57 % of Ffi's** (108.8 s of 190.3 s).  So the dead
weight looked expensive.  We implemented the early prune -- after the
fingerprint so digests are untouched, dropping only unreachable *hidden
definitions* (facts stay: the triviality check can discharge a support
obligation from a hidden fact equal to the goal, which is why the
existing pass sits where it does), old path for the
ENABLED/`\cdot`/AutoUSE/Lambdify obligations.

Measured, `--noproving`, one host, one boot:

| corpus | off | on | `expand_defs` | the prune itself | peak RSS |
|---|---|---|---|---|---|
| monolith (29 965 obl.) | 285.9 s | **910.9 s** (x3.19) | 49.1 -> 294.1 s | 154.6 s | 1.16 -> 1.14 GB |
| Ffi (9 967 obl.) | 190.3 s | **842.4 s** (x4.43) | 108.8 -> 610.5 s | 68.0 s | 0.63 -> 0.92 GB |

**The dead weight is free precisely because it is shared.**  Pruning per
obligation rebuilds the context, which destroys the physical prefix
identity the expansion and normalization caches resume from; the median
divergent suffix (1 hypothesis) becomes a full walk of ~400 entries.
Memory gets worse too, for the same reason -- fresh nodes instead of
shared ones.  The experiment is reverted; the drop-rate counters stay as
a diagnostic.

**What this says about C3.**  "Materialize only what is used" and "share
context prefixes across obligations" optimize the same cost and exclude
each other.  The flat pipeline chose sharing and that is where its speed
comes from.  A lazy tree is only faster if its node addressing *also*
delivers cross-obligation sharing -- design work, not a free consequence
of the representation.  Third result of this family, with B2-lite and
de-materialization.

**And a harness defect worth fixing.**  The synthetic generator misled
us: on `gen_synth.py` modules, adding 2 000 never-cited hidden
definitions took the wall from 8.2 s to 52.9 s and the early prune won
x2.1 -- because those contexts share *no* prefix (the expansion fold
walks all ~2 050 entries per obligation, i.e. the cache resumes at 0),
where the real corpora share >99 %.  A generator that does not reproduce
prefix sharing mis-ranks every optimization that depends on it.

## Sequence

A1 (user-side confirmation run on the 7.7 GB machine) →
B0 (probe; ~1 day) →
B1 in the C3-compatible form unless upstream kills C3 →
B2 portable core (criterion + validation) →
C1/C2 (EXTENDS cache, range-gated proof elaboration — cheap, on the
current architecture) →
C3 (the lazy tree), timed by the maintainer conversation, not by this
file.

Standing gates for every step: strict (or explicitly-subset) golden
dumps, unchanged test fail-set, real-solver verdict parity on the three
corpora, and a monitored before/after run at each expected transition.
