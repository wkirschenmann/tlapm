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

Compute, at the top of `ship`, the kept set: goal + `BY`/`BY DEF`
transitive closure + the declarations well-formedness needs — and let
the expensive stages walk only that. Hard constraint: the fingerprint
is still computed on the *unselected* obligation (digest invariance —
existing .tlacache files must stay valid).

What the lazy tree changes here — and what it does not: the tree gives
the *candidate* context for free (parents + earlier siblings + module
prefix at the root + INSTANCE-imported units, O(Δ) per node). It does
**not** give the *cited subset*: the closure computation, its soundness
edge cases (ENABLED expansion needs, level computations, implicit
declarations) and the whole validation battery (subset dumps, verdict
parity) are representation-independent. That is where the risk and the
work live, and all of it survives C3. Only the small flat-deque
traversal is representation-specific and will be rewritten as the O(Δ)
tree walk.

So B2 is scoped to its portable core: establish and harden the
*criterion* on today's architecture, take the ÷8-slope gain now, accept
a small traversal rewrite later.

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
