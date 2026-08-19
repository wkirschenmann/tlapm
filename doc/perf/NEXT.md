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
2. The toolbox protocol announces the obligation count up front
   (`tlapm_lib` prints it from `Array.length final_obs`); with lazy
   generation the total is only known at the end. Either a cheap
   counting pre-pass (re-runs generation without retaining, ~6 s on
   the monolith), a late count message (protocol/UI change), or
   accepting the count after the stepper drains (it finishes well
   before proving does — the progress denominator arrives a few
   seconds late).
3. Per-theorem granularity is proposed as final — going per-obligation
   inside a theorem would require re-splitting `generate`/`collect`
   (the supp filter and the Steps/QED dependency make creation-time
   emission subtle) for no measured benefit.

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
