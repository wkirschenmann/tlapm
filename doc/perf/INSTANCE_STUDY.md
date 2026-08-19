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

## Improvement avenue (to bring to the team/maintainers)

During instantiation (`M_subst.app_modunits`), a definition whose body
has **no dependence on any substituted parameter** (transitively: nor
on another re-emitted definition) is semantically identical to the
already-present original. Instead of re-emitting it under the instance
prefix, remap references to point at the original — index surgery of
the same nature as what `app_modunits` already performs. Expected
effect: remove the closed copies (~20 % of all context definitions on
FfiGrpc) from every obligation context, shrinking `expand_defs` /
`add_constness` / fingerprint traversal proportionally on
INSTANCE-heavy specs; strictly a context-subset change (same
obligations, fewer redundant definitions in scope).

In the tree-addressed world (C3/étape 4) the same idea is structural:
an INSTANCE node holds a reference to the instantiated module plus the
substitution, and only parameter-dependent definitions ever
materialize; the closed-copy elimination above is the flattened-world
approximation of that, implementable now and upstream-reviewable on
its own.
