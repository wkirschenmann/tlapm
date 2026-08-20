# Notes for the upstream discussion (tlaplus/tlapm#286 follow-up)

This file collects the performance topics that are, by design, **not**
addressed on this branch because they change interfaces or
representations that belong to the maintainers: each entry states the
measured evidence, the mechanism, the options we see, and what this
branch already contains that the discussion can build on.  The
measurement corpus is described in `ANALYSIS.md`; the running results
log is `NEXT.md`.

## 1. Property lists: representation of node metadata

**Evidence.** Stack-sampling the whole backend preparation of a
30k-line, 30k-obligation module attributes ~22 % of samples to
`Property` (list lookups), ahead of every individual pipeline stage
(`E_visit` 17 %, `Prep` 12 %, `E_subst` 12 %, fingerprints 10 %).
Every AST node carries a `props : (pid * Obj.t) list`, and every visit
of every node queries it several times (locus, level information,
constness…).

**What this branch does about it.** The lookups themselves were made
as cheap as the representation allows, with no interface or behavior
change: monomorphic pid equality (the generic structural `=` is a C
call per list element), direct loops instead of
closure-plus-`Not_found` round-trips (`query` misses are the common
case).  Numbers in the commit message.

**What is left for discussion — the representation itself.** The
per-node association list means O(list length) per read and one list
cell + one boxed pair per assignment.  Options, in increasing order of
intrusiveness:

  * dedicated record slots for the 2–3 hottest properties (locus,
    level/constness annotations), keeping the list for the tail — the
    wrapper type `'a wrapped` is used by every file of the code base,
    so even this "small" change is a large diff;
  * interning pids as small ints only (dropping the `Puuid`
    constructor from the hot path — UUIDs appear only on
    externally-identified properties);
  * a per-node small immutable array sorted by pid.

We measured no *single* dominant property, so the win is bounded by
the total (×1.2–1.4 on preparation at best) and has to be weighed
against churn.  We recommend discussing this only after the cheap
lookups above are in.

## 2. INSTANCE × EXTENDS: duplicated context definitions

**Evidence** (full study in `INSTANCE_STUDY.md`): when a module both
`EXTENDS` a library and instantiates modules that extend the same
library, the instantiated copies of the library definitions coexist
with the directly-extended ones in every obligation context.  On the
private FfiGrpc corpus this accounts for **20.5 % of all context
definitions** (a single top-level `INSTANCE AbstractGrpcTheorems`
whose transitive extends overlap the spec's own).  The EXTENDS diamond
itself is already deduplicated by flattening (`m_flatten`'s `seen`);
the INSTANCE path bypasses it because instantiated definitions are
renamed (`I!op`), so the sharing is invisible to the name-based
dedup.

**Design input, not a flat-pipeline change** (decision recorded in
`INSTANCE_STUDY.md`): for parameter-free extendees, the instantiated
copy is α-equivalent to the directly-extended definition, so the
instantiation could re-point to the existing definitions instead of
copying — the natural home for this is the lazy/graph module
representation discussed for the C3 track, not the current flat
expansion, whose semantics this branch deliberately leaves untouched.

## 3. Pre-expansion triviality (the B2 negative results)

Recorded in `NEXT.md`: pruning or skipping obligations before
expansion is blocked by the triviality check running on the expanded
form, and a B2-lite short-circuit measured ≈ 0 because the prefix
caches already make per-obligation preparation marginal.  Any upstream
design that wants cheap obligation skipping needs a triviality
criterion defined on the pre-expansion form; we did not find one that
preserves the current semantics.

## 4. What the branch itself offers upstream

In upstream-adoptable order (each is a self-contained commit series
with its gates recorded in the messages):

  1. micro-fixes and probes (inert or output-identical);
  2. the preparation caches (`normalize` memoization, prefix resume) —
     the single-pass memory/speed unlock (OOM → 235 s flat-RSS on the
     30k corpus);
  3. the resumable generation stepper + `TLAPM_STREAM_GEN` (platform
     for lazy generation; CLI-neutral, fully gated);
  4. the LSP incremental track (`TLAPM_LSP_SCOPED=1/2/3`,
     `TLAPM_LSP_FORK=1`): keystroke 59.7 s → 2.0 s, edit→verdict
     ~3.2 s on the 30k corpus, each stage gated by byte-identical
     client-visible streams.  The scoped modes carry elaborated
     material across versions; inner expression locations of reused
     units are stale by design (fingerprints are position-independent;
     everything the client sees positionally is shifted) — the
     step-decomposition code actions would need the same shifting
     before the modes become defaults.
