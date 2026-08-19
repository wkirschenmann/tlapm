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
  - **Fingerprint prefix cache** (CLI + LSP): the fingerprint string
    is a serialization of the context + goal, and consecutive
    obligations share the same physically-identical context prefix the
    prep caches exploit. Subtlety that shapes the implementation: the
    printer (`Backend.Fingerprints`'s `spin`) emits hypotheses in
    POST-order — the shared prefix lands at the *end* of the buffer —
    and threads mutable state (a Stack, De Bruijn counters), so the
    checkpoint is (state at divergence point, tail string), not a
    buffer prefix. Gate: fingerprint files byte-identical; a
    both-ways oracle like TLAPM_CHECK_ELABCACHE.
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
