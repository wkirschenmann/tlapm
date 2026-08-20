# Parallelising preparation — feasibility inventory

## Why this is the remaining CLI lever (measured, this machine)

The single-pass run is bounded by preparation, not by solvers:

| measurement (30k monolith, 4 cores) | result |
|---|---|
| cold run, real solvers, `--nofp` | **291 s** |
| preparation only (`--noproving --printallobs`) | **189 s** |
| fully warm re-run (all fingerprints present) | **229 s**, with `prune_context`, `action_frontend`, `encode` at **0.000 s** — no solver work at all |
| same binary, 16 cores → 4 cores | **×1.24** only |

Two consequences.  The warm re-run — the dominant real workflow, since
one re-runs a file after touching one lemma — is 229 s of pure
preparation on one core while three sit idle.  And the ×1.24 says the
cold run is preparation-bound too: solver parallelism is not what
limits it.

Ceilings, from those numbers:

* **step (a), overlap only**: wall ≥ max(preparation, solver-exclusive
  time) ≈ max(189, ~100) → 291 s → **~190-200 s (−30 %)**;
* **step (b), K-way preparation**: the 189 s is the divisible part;
  on 4 cores, ~×2-2.5 on it realistically → **~110-130 s total**.

## Inventory: mutable state on the preparation path

Categories matter more than counts: what breaks depends on whether
preparation is *relocated* to one other domain (step a) or *split*
across several (step b).

**A — per-traversal scratch.**  Set and reset within one traversal;
shared only if two traversals run at once.  Harmless under (a) — a
single preparation domain touches them exclusively — and the main
obstacle under (b).
`e_elab`: `current_at`, `will_replace` · `e_levels`: `filled_caches` ·
`smtcommons` (encoding): `ctr`, `record_ids`, `tla_op_set`, `chooses`,
`skolem1_ids`, `skolem2_ids`, `record_signatures`, `simplefacts`,
`tuples`, `newvars` · `typesystem`: `typ_impgraph` (5 refs), `typ_c`
(4), `typ_e` (3).  ≈ 25 refs over 6 modules.

**B — cross-obligation prefix caches.**  These *are* the sequential
discipline: they hit because consecutive obligations share a context
prefix, which is why document order matters.
`prep`: `expand_cache`, `elab_cache`, `constness_cache`,
`find_meth_stable`.  Untouched under (a) (preparation stays sequential,
just elsewhere).  Under (b): one cache set per chunk — locality is
intra-chunk, so most of the hit rate survives, but this must be
measured, not assumed.

**C — shared across the split.**  `Fpfile.fptbl`: read by preparation
(`already_processed`), written when a verdict is recorded.  The single
genuine synchronisation point, and cheap to guard (queries are
microseconds and are not the bottleneck).

**D — measurement.**  `Timing.stack`, `Timing.last_event`,
`Deque.nth_calls/nth_walk`, `prep_timers`, `prep_current_id`,
`prep_share_prev`, `p_gen.tree_depth`.  Per-domain or disabled in
parallel mode; no semantic content.

**E — configuration, read-mostly.**  `Params` (44 refs).  Checked: the
only runtime writes are at startup or module setup (`output_dir`,
`fp_loaded`, `fp_original_number`, `input_files`, and the LSP entry
points), never from preparation.

**F — main-domain only.**  `Toolbox.stopped/killed/got_eof` (stdin
polling), `Util.err_formatter/std_formatter`, `Errors.loc/msg/warning`.

**G — not on the path.**  `m_elab.salt_counter` (elaboration);
`Property.ids`, the pid counter — checked, every `Property.make` is
evaluated at module initialisation, so preparation never allocates a
pid.

## The other half: preparation performs ordered effects

Preparation today interleaves computation with reporting, and the
toolbox protocol is order-sensitive:

* `Toolbox.toolbox_print` ("being proved", "normalized"),
  `Toolbox.print_new_res` (verdicts, seven call sites);
* `Isabelle.thy_temp` / `thy_write`;
* `Fpfile.fp_writes`;
* the `record` callback (the driver's treated/proved sets);
* `Errors.err` / `Errors.warn`.

So the split is not "run prep elsewhere" but **"compute there, report
here"**: the producer must return a prepared value and perform no
effect.  This is the real refactoring cost of step (a), and it is
mostly plumbing in `prep.ml`'s `prep_meth`/`really_ship`.

## Step (a) is dead — measured, not argued

`TLAPM_SCHED_TIMES` attributes the scheduler's own wall time on the
cold monolith run:

```
total=247.8s  next(prep)=11.1s  launch=233.6s  wait=0.0s (68915 selects)
overlap potential: serial=244.8s   max(prep+launch, wait)=244.7s
```

**Waiting for provers costs zero.**  Over 68 915 `select` calls the
loop never blocks, because the provers are *subprocesses*: their
execution already overlaps the main loop's preparation.  The premise of
step (a) — preparation and solver waiting strictly alternating — was
simply wrong, and the −30 % it promised does not exist (0.1 s of 245).

What the same measurement establishes: **233.6 s of the 247.8 s are
spent inside `start_process`**, i.e. forcing preparation.  The run is
preparation-bound from inside the scheduler, matching the ×1.24 core
scaling and the 229 s solver-free warm run.  So step (b) is not "the
bigger win", it is the only one, and its target is the whole 233.6 s.

## Step (b): parallelise preparation by contiguous chunks

K domains, each preparing a contiguous range of the document, one
prepared-task queue per chunk, and the main domain consuming them in
document order and performing every effect.

* contiguous chunks, because the category-B prefix caches hit on
  consecutive obligations: one cache set per domain keeps the locality
  inside a chunk, and only the cross-chunk hits are lost;
* category A (~25 scratch refs over 6 modules) must become
  domain-local: this is the real price of (b), and it is a
  functorisation or a `Domain.DLS` pass, not a patch;
* the consumer keeps all reporting (toolbox messages ordered by
  obligation id, theory and fingerprint writes, the `record`
  callback), so the observable stream is unchanged;
* behind a flag, with the sequential path as the reference.

**Category C without a lock.**  The fingerprint table is a memo of a
deterministic function, so the write is idempotent: read, and on a miss
compute and store — two domains racing store the *same* value, and the
only cost is duplicate work on cores that would otherwise idle.  That
removes the synchronisation point as such.  One implementation caveat,
though: OCaml's `Hashtbl` is not safe under concurrent mutation — a
resize during a lookup can crash or lose entries, and "the value is the
same" does not help because the corruption is structural.  The faithful
way to keep the lock-free design is a word-sized atomic slot: an
immutable map (or an array of per-bucket immutable maps) behind
`Atomic.t`, where storing is a plain set of the same value.  Reads stay
lock-free and always see a consistent structure.  The fingerprint
*file* writes stay on the consumer, where they are already ordered.

**Gate.** Strict golden dumps (generated *and* shipped obligations
byte-identical) plus a **byte-identical toolbox stream**: the message
order is part of the contract, and it is the property most likely to
break.

## Step (b) sized before writing it

Two questions decide the ceiling: do the prefix caches survive
chunking, and does the work balance?  Both answered from a
`TLAPM_PREP_SHARE` run on the 30k monolith (29 965 obligations).

**The caches survive, by a wide margin.**  Contexts have a median of
743 hypotheses, of which a median of **699 are physically shared with
the preceding obligation** — the median divergent suffix, i.e. the real
per-obligation work, is **1 hypothesis** (mean 81).  The caches
therefore avoid **90.1 %** of the context work, and since they are
single-slot and keyed on the *previous* obligation, contiguous chunking
only breaks the chain at chunk starts: **0.096 % extra work at K=4**,
0.23 % at K=8.  The locality worry was quantitatively unfounded.

**Balance is the real limiter, and coarse dynamic chunks fix it.**  With
K chunks of equal *obligation count*, the load ratio reaches 1.61 at
K=4, capping the speedup at 2.48×.  But no single obligation dominates
(the heaviest is 0.05 % of the total, the top 1 % carry 11.7 %), so
splitting into more chunks than domains and letting domains pull them
recovers almost everything.  Modelling per-obligation cost as 87 %
proportional to the divergent suffix plus 13 % uniform (the digest
hashes the whole context, 29.4 s of the 233.6 s, so it is
size-independent):

| K | chunks | obl./chunk | speedup on preparation | boundary overhead |
|---|---|---|---|---|
| 4 | 4 | 7 491 | 2.61× | 0.08 % |
| 4 | 8 | 3 745 | 3.89× | 0.20 % |
| **4** | **16** | **1 872** | **3.98×** | **0.44 %** |
| 4 | 64 | 468 | 4.00× | 1.72 % |
| 2 | 16 | 1 872 | 2.00× | 0.44 % |

Sixteen chunks on four domains is the knee: 3.98× of the theoretical 4,
each chunk still holding ~1 900 consecutive obligations for the caches.

**Projection.** Preparation 233.6 s → 59 s, plus 14.2 s of serial
scheduler work → **≈ 73 s inside `run_stream`** (3.4×).  The cold run's
remaining 43 s (parse, elaboration, generation, fingerprint load,
report) is untouched, so the whole run goes **291 s → ≈ 116 s (×2.5)**;
the warm re-run, which is preparation end to end, goes **229 s → ≈ 70 s
(×3.3)**.

## Validated on the machine, and it changes the implementation route

Before touching the code: four independent `tlapm` processes, each on a
contiguous quarter of the monolith (separate cache dirs, `--nofp`).

```
part0 65 s   part1 98 s   part2 84 s   part3 141 s      wall 141 s   (vs 291 s serial: x2.06)
```

Two results.  **The machine scales**: four OCaml processes doing this
work do not contend — no memory-bandwidth wall — even though each one
*repays ~43 s of redundant parse and elaboration*.  And the imbalance is
exactly the one modelled above (predicted 137 s for the heaviest
quarter, measured 141 s: 3 % error), which validates the model that
predicts 3.98× for 16 dynamic chunks.

**Therefore: fork, not domains.**  The experiment is nearly the target
architecture already.  Preparation per chunk is independent; only the
*effects* need ordering.  A process forked after elaboration inherits
the elaborated module by copy-on-write — exactly the mechanism already
built and gated for the LSP prove path (`TLAPM_LSP_FORK`) — and pays the
parse and elaboration **once**, in the parent.

This removes the entire category-A problem: separate address spaces, so
none of the ~25 scratch refs is shared, and no OCaml 5 domain hazard at
all.  What remains is bounded and already has precedent in the tree:

* the toolbox stream must be reassembled in chunk order — one pipe per
  child, the parent forwarding them in order (children are contiguous
  ranges, so the ordering is a concatenation, not an interleave);
* each child writes its own fingerprint file and the parent
  consolidates — `Fpfile.fp_close_and_consolidate` already exists for
  this;
* the parent keeps the verdict accounting and the final report;
* the fork hygiene lessons from `TLAPM_LSP_FORK` apply verbatim (reset
  signal dispositions, blocking descriptors, leave through
  `Unix._exit`).

Projection with the redundant parse paid once: 43 s (parse, elaboration,
generation) + 233.6/3.98 ≈ 59 s of preparation + merge ≈ **~105 s, i.e.
×2.8 on the cold run**, and the warm re-run ≈ ×3.3.

The one new risk this route carries is **memory**: K children each
copy-on-write over a 1.4 GB heap and then allocate their own working
set.  Measurable before committing to it, and the 7.7 GB target machine
is the constraint to check, not the 16 GB one.

**Usable today, without any code change.** The same experiment is a
technique, not just a measurement: splitting a large spec across
processes by line range already gives ×2 on this corpus.  It also
explains why chunked proving has been the practical workaround.

## Risks, stated plainly

* A stray access from the wrong domain is a data race, not an error.
  Mitigation: (a) relocates rather than shares, and a domain-identity
  assertion in the category-A modules would catch violations while
  testing.
* The encoding stage carries ~25 scratch refs (category A).  Fine under
  (a); under (b) they must all become domain-local, which is the honest
  price of step (b) and probably a functorisation, not a patch.
* Under (b), the prefix caches lose cross-chunk hits.  The measured
  per-chunk hit rate decides how much of the ×K is actually available —
  and since (a) is dead, there is no cheaper fallback to retreat to.

## Sequence

0. This inventory — done.
1. Measure the overlap potential inside the scheduler — done, and it
   removed step (a) from the plan.
2. Measure the per-chunk prefix-cache hit rate (a pure simulation over
   the existing `TLAPM_PREP_SHARE` data: replay the obligation sequence
   split into K contiguous chunks and count the hits each chunk would
   still get).  This sizes (b) before any refactoring, the same way
   step 1 unsized (a).
3. Make category A domain-local, behind a flag, with a domain-identity
   assertion to catch stray accesses during testing.
4. Step (b) proper: K chunk domains + ordered consumer, gated on
   byte-identical toolbox stream and golden dumps.
