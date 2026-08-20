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

## Step (a): relocate, do not parallelise

One producer domain; every effect stays on the main domain.  Because
there is exactly *one* preparation domain, category A is never shared —
that is what makes (a) tractable — and only C needs a lock.

* bounded queue (depth 1–2) of prepared tasks, preserving document
  order;
* producer: fingerprint query (under the C lock), `add_constness`,
  digest, `normalize_expand`, encoding → a prepared record;
* consumer: emits the toolbox messages, launches solvers, records
  verdicts, writes fingerprints and theory files;
* an environment variable or `--debug` flag to disable, so the
  sequential path stays the reference.

**Gate.** Strict golden dumps (generated *and* shipped obligations
byte-identical) plus a **byte-identical toolbox stream**: the message
order is part of the contract, and it is the property most likely to
break.

## Risks, stated plainly

* A stray access from the wrong domain is a data race, not an error.
  Mitigation: (a) relocates rather than shares, and a domain-identity
  assertion in the category-A modules would catch violations while
  testing.
* The encoding stage carries ~25 scratch refs (category A).  Fine under
  (a); under (b) they must all become domain-local, which is the honest
  price of step (b) and probably a functorisation, not a patch.
* Under (b), the prefix caches lose cross-chunk hits.  The measured
  hit rate per chunk decides whether (b) beats (a) at all.

## Sequence

0. This inventory — done.
1. **Measure the overlap potential directly** inside the scheduler
   (time spent building tasks vs waiting on solvers).  The 189/100
   split above comes from two different runs; one probe replaces the
   inference.  Cheap, and it decides whether (a) is worth its
   refactoring.
2. Step (a), behind a flag, with the gates above.
3. Re-measure, then decide on (b).
