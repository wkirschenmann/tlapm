# INSTANCE and EXTENDS: what elaboration puts in the context

Study phase for the tree-addressing / lazy-DFS track (2026-08-19).
Reproducible material: `test/perf/instance/` (four-module synthetic
cases); corpus numbers are aggregates from the private benchmarks.
Probe: `TLAPM_TRACE_DEFS` with name fragments.

## Question 1 — a first-level object instantiated (`I == INSTANCE AA`)

Works, and the representation is the crux. `AA` defines `Init` and
`Next` (2 operators) and extends `Naturals`. After elaboration of

    I == INSTANCE AA

the enclosing module's context contains **14** `I!…` definitions:
`I!Init`, `I!Next` — and one instantiated copy of every operator `AA`
inherits from `Naturals` (`I!Nat`, `I!+`, `I!-`, `I!*`, `I!<`, `I!>=`,
`I!%`, `I!..`, …). The mechanism: `M_flatten.flatten` splices the
extendees' units into `AA`'s body *before* instantiation, and
instantiation (`M_subst.app_modunits`) then copies the whole flattened
body under the instance prefix.

The copies of the inherited operators are pure waste: their bodies do
not mention `AA`'s parameters (`x`, `y`), so the substitution leaves
them untouched — `I!+` is semantically the operator `+` that is
*already in the context* via the enclosing module's own `EXTENDS
Naturals`. Every such copy is walked by `expand_defs`/`add_constness`
and hashed by the fingerprint of every later obligation.

## Question 2 — an instantiated family (`A(i) == INSTANCE AA WITH x <- x[i], y <- y[i]`)

**Handled correctly today.** The exact example (a parameterized
instance indexed by `i \in Instances`, `WITH x <- x[i], y <- y[i]`)
elaborates, generates obligations, accepts `BY DEF Init, A!Init`, and
the shipped obligation is right:

    ASSUME NEW CONSTANT Instances, NEW VARIABLE x, NEW VARIABLE y
    PROVE (\A i \in Instances : x[i] = 0 /\ y[i] = "idle")
          => (\A i \in Instances : x[i] = 0)

Representation: the same 14 materialized definitions as the
first-level case, each parameterized by `i` (and `Local` this time).
A family therefore costs the same context space as a single instance —
the multiplication is *not* per family member (good); it is per
`INSTANCE` statement (see the waste above).

## Question 3 — the EXTENDS diamond (L0 and L1 both extend Base)

**No duplication — the fear is unfounded for EXTENDS.** With
`Base` (defining `Double`, `LEMMA BaseLemma`), `L0 == EXTENDS Base`,
`L1 == EXTENDS Base`, and `Main == EXTENDS L0, L1`: fragment counts
show `Double=1`, `BaseLemma=1` per obligation context, and the diamond
adds exactly the 2 definitions proper to `L0`/`L1` over the
single-parent variant (172 vs 170 context definitions). The
deduplication mechanism is explicit in `M_flatten.flatten`
(src/module/m_flatten.ml): the fold over `m.core.extendees` threads a
`seen` set of module names and skips an extendee already spliced.

Caveat kept for the record: `flatten_body` restarts submodule
flattening with `Ss.empty` (m_flatten.ml:76), so a *submodule*'s
extension is spliced into the submodule's own body — which is exactly
what makes the INSTANCE×EXTENDS copying of Question 1 happen when that
submodule (or any extendee-carrying module) is instantiated.

## The real duplication vector, quantified: INSTANCE × EXTENDS

| corpus | context-def occurrences (all obligations) | of which instantiated (`!`) | share |
|---|---|---|---|
| FfiGrpc (INSTANCE-heavy) | 8 930 351 | 1 826 568 | **20.5 %** (~184/obligation) |
| timer_wheel monolith (EXTENDS-style) | 15 072 708 | 89 896 | 0.6 % |

On FfiGrpc, the per-name tallies show the inherited stdlib operators
at **1–2 instantiated copies per obligation context** (`!Len`, `!+`,
`!Seq`, `!Append`, `!SubSeq`, `!Head`, `!Tail`, `!Nat` each = 19 854 =
2 × 9 927 obligations; `!Cardinality`, `!IsFiniteSet` = 1 ×). This is
a large slice of issue #286's "huge contexts of INSTANCE/refinement-
heavy specs".

## Improvement avenue: hoist parameter-free extendees to the
## instantiation root (proposal 2026-08-19, refined)

Why the copy exists at all: an implementation-order artifact, not a
semantic need. `M_flatten` splices the extendees' units into the
module body *before* elaboration, and `instantiate`
(src/module/m_elab.ml:521-527) then uniformly shifts, substitutes and
`localize`s the **whole** flattened body under the instance prefix —
it never sees the boundary between inherited material and the module's
own units.

The proposed alternative — *"repasser les EXTENDS à la racine
courante"* — is sound under one criterion, and the criterion is
per-module, not per-definition: **an extendee (transitively) declaring
no CONSTANTS and no VARIABLES is invariant under any `WITH`
substitution** — the substitution maps the instantiated module's
parameters, an extendee's definitions can only reference parameters
declared upstream of themselves, and a parameter-free module chain has
none. Such extendees can be spliced ONCE at the instantiation root
(deduplicated against the root's own extension by the same `seen`
logic `M_flatten` already uses) instead of copied per instance. The
subtlety is *not* semantic but representational: (i) the extension
boundary inside a flattened body must be recorded (or recomputed) at
flatten time; (ii) the instantiated own-units' De Bruijn references
into the hoisted prefix must be remapped to the root copies (index
surgery of the family `app_modunits` already performs); (iii) legal
but rare references like `I!+` or `I!SomeLibLemma` must still resolve
— either one-cell alias definitions (`I!op == <Ix to root op>`, keeps
the context count but kills the body copies) or a side table in the
anonymization pass (full win).

The criterion does real work on the corpus. On FfiGrpc, ALL 1 826 568
instantiated occurrences come from a single
`L0 == INSTANCE AbstractGrpcTheorems` (~184 `L0!…` definitions per
obligation context). Of the instantiated module's chain, the
parameter-carrying part (`AbstractGrpcState`'s CONSTANTS/VARIABLES and
the definitions over them — `AbstractGrpc_defs`, the theorems' own
statements, ~50-70 units) must legitimately be instantiated; the
parameter-free part — Naturals, Sequences, FiniteSets,
SequenceTheorems (40 theorem statements), NaturalsInduction (16),
FunctionTheorems, TLAPS…, ~110-130 units — is hoistable, and it is
precisely the *big-bodied* material (inherited theorem statements),
most of which the root module extends anyway (so after dedup the
copies vanish outright). Estimated effect: remove ~60-70 % of the
instantiated occurrences ≈ 12-14 % of all context-definition
occurrences on FfiGrpc, concentrated in the largest bodies.

Fingerprint impact: expected invariant for obligations that never
reference the copies (the digest only prints *used* hypotheses,
numbered by first use), and structurally identical bodies for those
that do — to be confirmed with the differential oracle before any
delivery.

In the tree-addressed world (C3/étape 4) the same idea is structural:
an INSTANCE node holds a reference to the instantiated module plus the
substitution, and only parameter-dependent definitions ever
materialize; the hoisting above is the flattened-world approximation
of that, implementable now and upstream-reviewable on its own.

## Retained design (PO decision 2026-08-19): usage-filtered hoisting
## with aliases

Refinement over blanket hoisting: only keep what is actually *used*
through the module's interface, and bring it to the top via aliases.
The instantiated context then contains: the instance's own
(parameter-carrying) units, plus **one alias per inherited name
actually referenced** — `I!op == <Ix to the hoisted/root definition>`
— plus the transitive dependencies of those hoisted definitions,
deduplicated against the root's own extension (`seen` logic). Nothing
unused ever enters the context, and the aliases *are* the name
resolution (no side table needed; `BY DEF I!op` expands through the
alias to the real body).

What "used" means, both statically computable:
1. references from the instantiated module's *own* units into its
   extension prefix (De Bruijn indices below the extension boundary —
   detectable on the module's elaborated body);
2. `I!name` references in the enclosing module's source — these occur
   *after* the INSTANCE point, so they require a pre-scan of the
   enclosing module's parse tree before emitting the instance
   (two-pass over the module, or an emission point that already knows
   the use set).
Plus the transitive closure of the hoisted definitions' own
references. The per-module parameter-free criterion above still
delimits what may be hoisted at all; parameter-carrying material is
instantiated as today.

Measured on FfiGrpc: the enclosing spec references **73 distinct
`L0!…` names**, of which **one** is inherited library material
(`L0!IsFiniteSet` — FiniteSets is not even in the root's own
extension chain, so the interface use is genuine); the other 72 are
AbstractGrpc's own definitions and theorem statements, which must be
instantiated anyway. Expected effect of the design on this corpus:
the ~110–130 unused inherited copies per obligation context (all the
SequenceTheorems / NaturalsInduction / FiniteSetTheorems statement
bodies among them) disappear outright, replaced by one alias and a
handful of hoisted dependencies — roughly −60 % of instantiated
occurrences, −12 % of all context-definition occurrences, concentrated
on the largest bodies.

Open implementation items: where to place the use-set pre-scan in
`m_elab`'s single elaboration pass; alias visibility semantics (a
`BY DEF I!op` must expand through the alias — chained `Operator`
expansion already does this, to be confirmed on a test); fingerprint
invariance (unused hypotheses do not enter the digest, used ones keep
structurally identical bodies through the alias — to be confirmed
with the differential oracle); and the `TLAPM_TRIVIAL_SPIKE`-style
validation run on the INSTANCE-heavy corpora.
