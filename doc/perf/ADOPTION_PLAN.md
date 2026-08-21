# Adoption plan: what to take from this branch, in what order

This file answers one question: **starting from `main`, which changes
give the most performance per line of diff, and in what order should
they land.**  The branch's own history is chronological — it follows
what we were investigating — and that is *not* the order to adopt.
This is the reordered path, ranked by gain over modification size, with
the test and measurement protocol for each item.

Nothing here is a new claim: every number is one already recorded in
`NEXT.md`, `BASELINE.md`, `PARALLEL_PREP.md` or the per-commit sweep
(`_perf/sweep.csv`, `_perf/sweep_ffi.csv`).  What is new is the
ordering, the diff sizes, and the per-item protocol.

## Enough context to read this cold

`tlapm` parses a TLA+ module, *elaborates* it (resolves names, expands
`EXTENDS` and `INSTANCE` into one flat context), walks it to *generate*
one obligation per proof leaf, *prepares* each obligation through seven
stages, and only then starts a prover subprocess.  Two things hurt on
large specifications, and they are different problems:

* **latency** — in the editor, every interaction re-parses,
  re-elaborates and re-fingerprints the whole file and its dependencies,
  twice (server and child).  Measured on a 30k-line module before this
  work: keystroke → diagnostics **59.7 s**, one step's verdict
  **5.1–7.9 s**.
* **throughput** — the same module was provable in five slices of
  ~2 000 lines but not in one pass: live memory grew with the obligation
  count until the heap gave out (**OOM at ~26 000 of 30 000** after
  110 minutes).

Where the branch leaves it, same machine, same module: keystroke
**2.0 s**, step verdict **0.4–1.0 s**, single pass **285 s** at a flat
1.5 GB, or **127 s** on four cores.

**Where the time goes** (one solver-free run, 9 967 obligations, 190 s):
parse 0.85 s, elaborate 1.99 s, generate 0.36 s — 1.7 % in total — and
**182 s in per-obligation preparation**, single-threaded, of which
expanding definitions alone is 108.8 s (57 % of the run).  The provers
are subprocesses that already overlap the loop: the scheduler blocked on
them for 0.1 s of 273 s over 259 waits.

**The one mechanism to understand.**  Consecutive obligations share
almost their whole context: median 743 hypotheses, of which 699 are the
*physically same objects* as in the previous obligation, leaving a
median divergent tail of **one** hypothesis.  Preparation exploits this
by storing each pass's state per position and resuming where the
contexts first differ.  That is what removed most of the throughput
problem — and it is why pruning the (85 % dead) context *per obligation*
makes things ×3-4 worse: it rebuilds each context and destroys the
sharing.  See the entry in `NEXT.md`.

**Vocabulary**, for the same reason: an *obligation* is one thing a
prover must show; its *sequent* is a context (list of hypotheses) plus a
goal; a *fingerprint* is the digest used as a cache key so a re-run
skips what is proved, and its definition must not change or every
existing cache is invalidated; a context entry is *hidden* when the
prover never sees it unless something refers to it; a *module unit* is a
top-level item (definition, declaration, theorem) — the granularity item
#15 splits by, because a proof's position is its keyword while its
obligations sit where the facts it cites are.

## How to read the numbers

**Metrics** (defined in `BASELINE.md`, all reproducible with
`test/perf/bench.sh`):

| | what it measures | why it matters |
|---|---|---|
| **M0** | parse + elaboration + generation (`-N`) | the floor of every interactive action, and the per-worker fixed cost of chunked runs |
| **M1** | full preparation, no prover (`--noproving`) | CLI throughput; the term that made large specs unusable |
| **M2** | fingertip (`--toolbox L L`) | "prove this one step" latency |
| **M3** | peak RSS during M1 | the OOM axis |
| **M4** | full run, real provers | the number a user feels |
| **LSP** | keystroke → diagnostics, scripted client (`test/perf/lsp_c0.py`) | the editor axis |

**Corpora**: `Synth_L300_S5_D50_C3` (1 800 obligations, public,
`test/perf/gen_synth.py`); an INSTANCE-heavy private spec (9 967
obligations, "Ffi" below); a 30k-line single-module private spec
(29 965 obligations, "monolith").  Only the synthetic one is
publishable; the others are calibration.

**Two measurement hosts** appear in the record: host A (16 cores, the
phase-0/1 sweep) and host B (4 cores, everything from the re-baseline
on).  Absolute values are only ever compared inside one host and one
boot.  Ratios inside a series are what carry over.

## Item #0 — the bugfixes, and why they are not in the table below

**These are not optimizations, and the decision to take them is not of
the same kind.**  An optimization is a trade: review effort and risk
against a measured gain, and it can reasonably be declined on either side
of that trade.  A bugfix repairs behaviour the program already advertises;
declining it means keeping the defect.  Mixing the two in one ranked list
invites the wrong conversation, so the three are grouped here, out of the
table, *even though two of them do have a positive performance effect*.

**Grouped: 5 commits, 8 files, +138/−35.**  Nothing else in this document
depends on them.

**B1 — the `--timing` report is wrong, and three of its rows are always
zero.**  Two independent faults in an existing documented flag:

  * *the accounting cannot nest.*  `start c` closed the running interval
    and made `c` current, `stop` switched back to ambient — so a clocked
    call inside another clocked region sends the **remainder of the
    enclosing region to `other`**.  Not hypothetical: `store_module` is
    clocked as *analysis* and runs inside the *simplification* region, so
    `simplification` is under-reported on every run.  Fixed by making the
    current clock a stack whose bottom is ambient.
  * *three declared and reported clocks are never started.*  `generation`,
    `fp_compute` and `fp_saving` print `0.000000` on every run;
    obligation generation is silently charged to *analysis* and
    fingerprint computation and writing to *interaction*, so the report
    cannot separate tlapm's own cost from prover time — which is the one
    thing it is read for.  Fixed by starting them at their natural sites,
    all under `Std.finally` so a raised exception cannot leave a clock
    running.

  *Verification:* run `tlapm --timing` on anything, before and after.  No
  performance effect at all; output-preserving apart from the report
  itself, so the dump comparison of T1 applies unchanged.  *Ordering
  bonus, not a dependency:* taken first, B1 removes the phase-table caveat
  that every later pull request otherwise carries (see "Local proof").

**B2 — provers reported as timed out when they had already answered.**
Preparing the next obligation can take seconds, and during that time an
exited prover sits unread past its deadline and is reported as a timeout.
Already described in #286.  `src/backend/schedule.ml`, +31/−0.

  *Verification:* the observable is the *set* of obligations reported
  timed out — none may be reported that was not before, and the spurious
  ones disappear.  Reproduce with a slow preparation and one prover slot.

**B3 — timed-out provers are not killed when the hangup signal is
ignored.**  Signal 1 is the only kill path in the CLI, and `SIG_IGN` for
it is inherited through `fork` *and* `exec`, so any run started under
`nohup` or detached announces its timeout, frees the scheduler slot, and
leaves the prover running.  `src/system.ml`, +12/−1.

  *Verification:* run the same specification **under `nohup`** before and
  after, counting live prover processes with `ps` and peak memory.
  Measured: 725 s → 282 s, 4.60 → 0.43 provers alive on average against a
  limit of 4 (peak 8 → 4), 6.86 GB → 1.54 GB.

  *That effect is large, and it is precisely why this sits here rather
  than in the table*: the number is an argument for **urgency**, not the
  reason to take the change.  It would be worth taking at zero measured
  gain.

## Ranked by gain over modification

Ratio is the headline gain divided by the diff size — a blunt
instrument, deliberately, because it is what decides what to review
first.

**Granularity: one row = one pull request.**  Five rows are a group of
commits that must land together (the `commits` column says how many); the
other seventeen are a single commit.

**Bugfixes are not in this table**, by construction — including the two of
them that do have a positive performance effect.  They are item #0 above,
and the decision to take them is of a different kind.

**No row is an instrumentation change, and none depends on one.**  The
branch carries probes and a measurement harness, and they are what
produced the numbers below — but they are *our* tooling, not part of the
proposal.  An optimization must not have to wait for a maintainer to
accept a probe.  So: each pull request states its measured effect,
labelled as obtained with an instrumented build where that is the case,
and carries a **reproduction recipe that runs on stock `tlapm`** — see
"Local proof" below.  If the instrumentation is ever wanted, it is a
separate proposal of its own, and it changes nothing here.

| # | change | commits | files | +/− | headline gain | metric |
|---|---|---|---|---|---|---|
| 1 | `util/Deque`: nth / first_n / equal on rear-heavy deques | 1 | 1 | +37/−27 | **×8.2** M0 on Ffi (32.1 s → 3.89 s), ×8.8 M2 | latency |
| 2 | `backend/prep`: prune unreachable hidden definitions, then unreferenced hidden facts | 2 | 1 | +102/−16 | **×2.7** M1 (30.2 → 11.2 s), **×8.7** M3 (1.50 GB → 173 MB) | throughput |
| 3 | `backend/prep`: expand visible definitions in one pass | 1 | 1 | +31/−13 | ×1.45 M1, −17 % M3, and Ffi M1 goes from *timeout* to 458 s | throughput |
| 4 | `lsp`: sorted obligation pool instead of per-step `RangeMap.partition` | 1 | 1 | +100/−12 | **×5.2** keystroke on the monolith (59.7 → 11.5 s) | latency |
| 5 | `module/Elab`: linear ENABLED-axioms detection | 1 | 1 | +23/−18 | ×1.59 M0 on Ffi (3.74 → 2.35 s) | latency |
| 6 | `expr/parser`: memoize the two instances of each grammar rule | 1 | 1 | +75/−21 | ×2.4 keystroke (2.9 → 1.2 s) | latency |
| 7 | `util/property`: monomorphic pid equality, loop-based lookups | 1 | 1 | +43/−12 | −5..−6 % of *all* preparation, −8.2 % M4 monolith | throughput |
| 8 | `backend/toolbox`: single-pass expansion in the result printer | 1 | 1 | +18/−11 | ×4.3 on the warm (all-fingerprints-present) path | throughput |
| 9 | `expr/Levels`: stop the level cache pinning one context per obligation | 1 | 4 | +36/−1 | flat heap instead of monotonic growth | memory |
| 10 | `expr/Subst`: memoized index lookup for deep substitutions | 1 | 4 | +37/−3 | ÷2.1 on the expansion tail | throughput |
| 11 | `expr/Levels`: resolve reference levels without slicing the context | 1 | 1 | +57/−29 | ×49 on the analysis clock (with #5) | latency |
| 12 | `expr/Constness`: O(1) De Bruijn resolution | 1 | 6 | +69/−4 | −73 % of the deque walks in `add_constness` | throughput |
| 13 | `backend/prep`: prefix-resume caches (expand, then `Elab.normalize`) + differential oracle | 3 | 4 | +356/−51 | ×1.32 M1 synthetic, **×2.15** M1 Ffi (55.1 → 25.7 s) | throughput |
| 14 | `backend/schedule`: pull tasks from a stream | 1 | 3 | +57/−9 | removes the eager task array; the single-pass OOM unlock with #9 | memory |
| 15 | `cli`: `--chunks N --spawn P` — the branch also holds an add-then-revert pair here (a prover-slot-division hypothesis, refuted by measurement) which must **not** be replayed | 2 | 9 | +392/−13 | **×2.24** M4 monolith (284.5 → 127.2 s) | throughput |
| 16 | `lsp`: forked in-process prover | 3 | 13 | +360/−36 | step verdict 5.1–7.9 s → **0.4–1.0 s** | latency |
| 17 | `lsp`+`module`: scoped fingerprint carry, scoped generation, scoped re-elaboration | 6 | 10 | +889/−128 | keystroke 11.5 s → **2.0 s** after #4 | latency |
| 18 | `Ctx`: logarithmic index lookup | 1 | 1 | +23/−2 | below the noise floor alone — the argument is the mechanism: the context name index was a linear association list | throughput |
| 19 | `backend/Smtlib`: compile the identifier-escaping regexes once | 1 | 1 | +25/−7 | below the noise floor alone — the regexes were rebuilt for every identifier printed | throughput |
| 20 | `expr/Subst`: walk substitution spines in `app_ix` without allocating | 1 | 1 | +20/−10 | below the noise floor alone — one allocation per spine step, on the hottest walk | throughput |
| 21 | `backend`+`encode`: skip identity rebuilds when flattening extracts nothing | 1 | 2 | +11/−3 | below the noise floor alone — the sequent was rebuilt even when the pass changed nothing | throughput |
| 22 | `backend/prep`: write the obligation comment into solver files only when they are kept | 1 | 1 | +5/−1 | below the noise floor alone — the obligation was pretty-printed into a file deleted immediately after | throughput |

Reading of the table: **items 1–8 are 429 added lines (−130) across
seven files** and cover the ×8 latency drop, the ×2.7 throughput and the
×8.7 memory reduction.  Items 13, 15, 16 and 17 are 356 to 889 added
lines each and buy one specific, smaller multiple.  Items 18 to 22 are
five one-file fixes that are each below the noise floor on their own;
jointly with 1, 5 and 11 they are the ×1.35 that the hot-path series
delivers.

## Dependencies

The ranking says what is worth most; this says what is not free to
reorder.  Everything not listed here is independent — the per-commit
sweep measured each in isolation, which is how we know.

**Hard, in the code.**

  * **#2's two commits, in order.**  The facts prune extends the
    definitions prune: same function, same marking pass.
  * **#10 requires #13.**  The memoized substitution is attached to the
    *expansion fold's states*; without the prefix cache there are no
    substitution values shared across obligations for its table to warm
    on, so the change has nothing to attach to.
  * **#13's three commits, in order**: the expansion cache, then the
    normalization cache, then the differential oracle that validates the
    second.
  * **#17 requires #4.**  The scoped modes patch the proof-step tree that
    #4 rebuilt; over the old quadratic association they would have to be
    written twice.

**Hard by measurement — the one that is easy to miss.**  **#2 must not
ship without #13** for INSTANCE-heavy specs: on that corpus the prune
alone takes preparation from 458 s to 842 s while cutting peak memory
from 13.9 GB to 5.1 GB, and the caches are what turn it back into a win.
On the other two corpora #2 stands alone.

**Soft, worth grouping anyway.**  #5 and #11 jointly produce the ×49 on
the elaboration clock and neither is impressive alone.  #9 and #14
jointly are the single-pass memory unlock — one stops the level cache
pinning contexts, the other stops materialising the task array, and
either alone leaves the run growing.  #16 and #17 touch adjacent code in
the same three LSP files without depending on each other.

**Batching, if it has to be batched.**  Two coherent series, grouped for
review coherence rather than for performance — the ranking already covers
that: *(a)* #1, #5, #11 and #18 to #22 — pure hot-path fixes, all output-identical,
reviewable by reading; *(b)* #3, then #2 + #13 + #10 — the throughput
chain, where the semantic argument lives and where a reviewer should
spend their attention.  Everything else is standalone.

## Files touched, per item

Diff sizes are in the table above; these are the paths, so a reviewer can
see the blast radius before opening anything.  Note how concentrated it
is: `src/backend/prep.ml` carries items 2, 3 and 13 — the whole
throughput story — and every one of items 1, 4, 5, 6, 7, 8, 11 is a
single file.

| # | paths |
|---|---|
| 1 | `src/util/deque.ml` |
| 2 | `src/backend/prep.ml` |
| 3 | `src/backend/prep.ml` |
| 4 | `lsp/lib/docs/proof_step.ml` |
| 5 | `src/module/m_elab.ml` |
| 6 | `src/expr/e_parser.ml` |
| 7 | `src/util/property.ml` |
| 8 | `src/backend/toolbox.ml` |
| 9 | `src/backend/prep.ml`, `src/expr.mli`, `src/expr/e_levels.ml{,i}` |
| 10 | `src/backend/prep.ml`, `src/expr.mli`, `src/expr/e_subst.ml{,i}` |
| 11 | `src/expr/e_levels.ml` |
| 12 | `src/backend/prep.ml`, `src/expr.mli`, `src/expr/e_constness.ml{,i}`, `src/util/deque.ml{,i}` |
| 13 | `src/backend/prep.ml`, `src/expr.mli`, `src/expr/e_elab.ml{,i}` |
| 14 | `src/backend/schedule.ml{,i}`, `src/tlapm_lib.ml` |
| 15 | `src/chunked.ml{,i}` (new), `src/params.ml{,i}`, `src/tlapm_args.ml`, `src/tlapm_lib.ml`, `src/backend/fpfile.ml{,i}`, `src/backend.mli` |
| 16 | `lsp/lib/prover/prover.ml{,i}`, `lsp/lib/docs/doc_actual.ml{,i}`, `lsp/lib/docs/docs.ml{,i}`, `lsp/lib/docs/obl.ml{,i}`, `lsp/lib/docs/proof_step.ml{,i}`, `lsp/lib/server/session.ml`, `src/tlapm_lib.ml{,i}` |
| 17 | `lsp/lib/docs/doc_actual.ml`, `lsp/lib/docs/proof_step.ml{,i}`, `src/module.mli`, `src/module/m_elab.ml{,i}`, `src/module/m_gen.ml{,i}`, `src/tlapm_lib.ml{,i}` |
| 18 | `src/ctx.ml` |
| 19 | `src/backend/smtlib.ml` |
| 20 | `src/expr/e_subst.ml` |
| 21 | `src/backend/prep.ml`, `src/encode/n_flatten.ml` |
| 22 | `src/backend/prep.ml` |

## Guards: what needs a switch, and what does not

**The rule we applied.**  A change needs a runtime guard when it alters
*what the provers receive*, or the *order and content of client-visible
messages*.  A change that only alters how fast the same bytes are
produced does not — and the golden-dump protocol (T1 vs T2 above) is
exactly what classifies a change into one of the two, so the
classification is mechanical, not a judgement call.

**What is guarded today.**

| guard | covers | default |
|---|---|---|
| `--debug noprepcache` | all three preparation caches — `expand_defs`, `Expr.Elab.normalize`, `add_constness` — restoring the uncached path (item 13, and the memoized substitution of item 10, which lives inside the cached fold) | caches on |
| `TLAPM_CHECK_ELABCACHE` | differential oracle: runs the resumed *and* the whole-sequent normalization on every obligation and compares the terms structurally; fatal on divergence | off |
| `--chunks N` / `--spawn P` / `--chunk-lines a b` | the whole parallel path; absent, the run is byte-for-byte the sequential one; refused under `--toolbox`, which warns and proves sequentially | off |
| `TLAPM_LSP_SCOPED=1|2|3`, `TLAPM_LSP_FORK=1` | the editor's incremental modes and the forked prover (items 16, 17) | off |
| `TLAPM_STREAM_GEN=1` | lazy generation, with eager fallbacks for `--summary`, `--check`, `--stats`, `--suppress` and explicit targets | off |
| 14 `TLAPM_*` probes | measurement only, inert without the variable | off |

**What is missing, in priority order.**

1. **The context prunes (item 2) have no off switch, and they are the
   one change on the list that alters prover input.**  They remove
   hypotheses; a reachability mistake, or a backend that turns out to
   need a hidden fact we judged unreferenced, leaves a user with a
   failing proof and no way to test the hypothesis.  The
   `Opaque "__pruned__"` self-check makes such a bug *loud*, which is
   good, but loud is not the same as recoverable.  Recommendation:
   `--prune-context=none|defs|defs+facts`, default `defs+facts`, or the
   cheaper `--debug noprune`.  Either way the escape hatch should land
   *with* the prune, not after the first bug report.

2. **The single-pass `expand_defs` (item 3) cannot be turned off.**
   `--debug noprepcache` restores the *cache*, not the *algorithm*: the
   iterated formulation it replaced is gone from the file.  The change is
   argued output-identical and the golden dumps agree, but it is a
   rewrite of a substitution composition, and the cheapest bisection tool
   for a future "the prover now sees something different" report is the
   old path behind `--debug oldexpand`.  Keep it for one release — and
   note the side benefit: like `--debug noprepcache` for #13, it makes
   the item's own A/B observable **inside one binary**, which is the
   strongest form of local proof a reviewer can be handed.

3. **If the probes are ever proposed, they should converge on the
   existing `--debug` namespace.**  This is not part of the adoption plan
   — the instrumentation is deliberately outside it (see "Local proof")
   — but the note belongs somewhere: `tlapm` already has
   `Params.debugging "…"` with a dozen switches (`tempfiles`, `verbose`,
   `oldsmt`, `rw`, …), and our branch grew a second, undocumented
   namespace of 14 `TLAPM_*` environment variables.  Environment
   variables are the right mechanism only for what must be read before
   argument parsing; everything else reads better, and documents itself,
   as `--debug <name>`.

4. **The editor modes should graduate from environment variables to
   client settings** before they become defaults — the language server
   receives `initializationOptions`, which is where an editor-side toggle
   belongs.  And `TLAPM_STREAM_GEN` must become a real flag if it is ever
   enabled by default: it changes the *emission order* of the "being
   proved" messages, which is part of a client-visible contract even
   though the set of messages is identical.

**What deliberately needs no guard.**  Items 1, 5, 6, 7, 8, 10, 11, 12,
14 and 18 to 22 are output-identical by construction and verified strict; a
switch would only add a code path nobody exercises.  Of item #0's
bugfixes, B3 changes a signal number, not an output — what it is missing
is not a guard but an *escalation*: SIGKILL after a grace period, for a
backend that traps SIGTERM, which needs the scheduler to remember the
pids it killed — and B2 makes a spurious timeout impossible, so there is
nothing to fall back to.

## Our own issue #286, and the part of this branch that is already in it

**#286 is ours** — *"tlapm scales poorly on INSTANCE/refinement-heavy
specs (large per-obligation contexts)"*, opened 2026-07-27 by
qdelamea-aneo, same team, still open with no maintainer reply.  It
describes this exact problem — "the time is almost entirely tlapm-side,
not the solvers: it comes from the very large contexts that deep INSTANCE
hierarchies attach to every obligation" — and presents **four patch
families with measured speedups**: 1.0–1.5× on small foundation modules,
5.9× at 652 average hypotheses, **>41×** at 3 406 (baseline timed out
after six hours, patched ~529 s).

Its four families are, in this file's numbering:

| #286 family | our items |
|---|---|
| ENABLED-axiom detection made linear | 5 |
| backend micro-fixes (regex caching, substitution, spurious timeouts) | B2 of item #0, 18–22, part of 1 |
| context pruning of uncited hidden facts before encoding | 2 |
| preparation reuse across obligations with identical context prefixes | 13 |

So **items 2, 5, 13 and 18–22, and B2 of item #0, are not new ideas,
and not a contribution from this branch** — they are our own already-public
proposal, re-implemented.  What the branch adds on them is the thing
#286 could not offer: single-topic reviewable commits, each with its
invariant stated and a mechanical gate, and attribution measured per
commit instead of per patch set.  Any upstream conversation should open
by pointing at #286 rather than presenting these as findings.

**New on this branch relative to #286**: everything else — items 1, 3,
4, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16 and 17, plus B1 and B3 of item #0.
Item 1 (the deque lookups, whose ×8 on parse+elaborate is the largest
single gain here), the editor track (4, 16, 17) and the parse floor it
stands on (6) are the substantial ones — and the five negative results,
which are arguably the more useful contribution to a maintainer's time.

## Other people's pull requests that touch this work

Upstream `master` is at `4600b24`, which is exactly this branch's base:
**nothing has landed upstream since we forked**, so every merged PR below
is already in our base and no merge drift exists today.  What matters is
the open ones.

| PR | author, state | why it matters here |
|---|---|---|
| **#284** "Kill orphaned prover processes on Linux when tlapm dies" | tangruize, open, approved (LGTM by lemmy) | **Same problem family as B3 of item #0, complementary failure mode.** #284 covers *tlapm dies* (SIGKILL, OOM): it wraps each prover in `exec setpriv --pdeathsig KILL` at `get_exec`, so the kernel kills the child when the parent goes. Ours covers *tlapm is alive but its kill is ignored*: it sent SIGHUP, which `nohup` and detached launchers set to `SIG_IGN`, inherited through exec — the scheduler announced the timeout, freed the slot, and the prover kept running (measured: one z3 at 6.86 GB while tlapm believed it dead). Neither subsumes the other; #284 also supplies the SIGKILL escalation our fix lacks. **Action: reference #284, do not duplicate it, and offer our measurement as further evidence for it.** |
| **#285** "Keep record-flattening refactorings tractable in TLAPS" | lemmy, open | Different subject — folding record-literal `EXCEPT` chains during normalization ("~5000 printed lines with the fold, >=39000 without, >=9M at 6 layers") plus a field-wise rewrite of record-constructor equalities, ~30 % wall-clock on its corpus. **But not orthogonal in code:** it modifies `let_normalize` and `except_normalize` in `Expr.Elab`, the two functions our item 13 exposes and calls *per hypothesis* instead of once per sequent. A textual conflict in `src/expr/e_elab.ml{,i}` is certain, and our per-hypothesis equivalence argument must be re-established afterwards — a fold carrying state across hypotheses would break it. `TLAPM_CHECK_ELABCACHE` is the tool; rerunning it on that PR's own regression test is the concrete check. |
| **#275** "Add SANY as a parser backend option" | ahelwer, open | Opt-in `--parser SANY`, supplementing the OCaml parser, which stays the default — so our item 6 keeps its value. Two consequences anyway: the editor floor is now **95 % parse**, so which parser wins decides that floor; and glondu's review found that "SANY … performs full semantic analysis (name resolution, level-checking) as part of what it calls 'parsing'", which our scoped re-elaboration (item 17) does not assume — it treats parse and elaborate as separable stages. |
| **#268** "Proof decomposition by template" | kape1395, open (extends #241, merged and in our base) | **This is the feature our items 16–17 currently break**, and the reason they stay flag-gated: the decomposition code actions locate steps by *range* (`locate_proof_path`, `locate_proof_step`, `locate_proof_range`), and under scoped re-elaboration the inner expression positions of reused units are stale by design. Coordination, not conflict: the shifting must be applied to what the decomposition consumes before those modes can be defaults. |
| **#283** "Add a deterministic Z3 rlimit budget via SMTT(rN)" | tangruize, merged (in our base) | Directly useful to our measurement protocol P2: a deterministic budget removes prover-side variance from A/B runs, which is the noise we currently absorb by interleaving arms. Worth adopting in the harness. |
| **#266** "Fix SMT SetOf n-ary extensionality axiom" | ylht, open | Changes an SMT encoding axiom, i.e. what is shipped. If it lands, item 2's subset gate has to be re-run against it — the two touch the same output. |
| **#248** "Upgrade Z3" | kape1395, open | Invalidates every absolute figure in this file; ratios inside a campaign survive. Re-baseline after it lands. |
| **#264** "CONTRIBUTING.md: Add LLM contribution policy" | ahelwer, **closed without adopting a policy** | Bears on how this work is presented, and #286's author already flagged the uncertainty. Closed because it was "kicked up to the TLA+ Foundation board level"; the position lemmy stated in the thread is the one to assume: "Initial contact with the project must be made by a human. For each commit, any use of an LLM must be disclosed, including identification of the specific model(s) used", motivated by "maintaining a working theory of the codebase in the minds of the humans who work on it". Practically: a human opens the conversation, disclosure is per commit, and the review-cost argument of §"Ranked by gain over modification" — 429 lines for most of the gain — is the one that answers the workload concern. |

## Local proof: what each pull request carries, on stock tlapm

The rule: **a reviewer must be able to see the effect with the binary
they already have**, before and after applying the patch, using nothing
that the patch itself introduces.  Instrumented figures may appear in the
description — they are how we found the effect — but they are labelled as
such and they are never the reproduction path.

**The stock instruments, all of them already in `main`:**

| flag | what it gives |
|---|---|
| `-N` | parse + elaborate + generate, no backend at all — the interactive floor |
| `--noproving` | the whole per-obligation preparation with no prover — the throughput term, reproducible without solvers installed |
| `--toolbox a b` | one range, and the `@!!`-prefixed protocol messages, which are timestampable from outside |
| `--printallobs` | every obligation printed in the toolbox messages — the golden dump, on stdout |
| `--timing` | the phase table (`parsing`, `analysis`, `interaction`, `total`) |
| `--nofp` / `--cache-dir` | force a cold run; keep arms from sharing a cache |
| `--threads`, `--stretch`, `--debug` | hold the prover configuration fixed between arms |
| `/usr/bin/time -v` | wall clock and **maximum resident set size** |
| the editor itself | edit-to-diagnostics and step-to-verdict latency, observed client-side |

**Two caveats to state in any PR that quotes the phase table** — both of
them are what B1 above repairs, so they apply only while B1 has not
landed.  On stock `main` the clock accounting does not nest — a nested region is charged to
the innermost clock that was started — so the *wall clock* is the number
to argue from and the table is indicative.  And three rows
(`generation`, `fp_compute`, `fp_saving`) are never started on `main`, so
they read `0.000000` in the baseline arm: do not cite them.  `parsing`,
`analysis`, `simplification`, `interaction` and `total` are populated in
both arms and are safe.

**The two test protocols, in stock form.**

*T1, output-preserving.*  `dune runtest` green, and the known-failing set
unchanged (40 of 48 fast tests pass without Isabelle; a change to *which*
eight fail is a regression).  Then the obligation stream, twice:

```
tlapm -N --toolbox 0 0 --printallobs --nofp --cache-dir $D MODULE.tla \
  | sed -e 's,/tmp/[^ ]*,TMP,g' > arm.txt
```

and `diff` the two arms — no checker needed; the normalisation only
erases temporary paths.  Run it on the public synthetic module and on any
real module the reviewer has.

*T2, subset.*  **The T1 stream does not show pruning**, so it cannot be
the subset gate.  `really_ship` prints the obligation *after expansion and
normalisation but before* `prune_context`; the pruned form is never
printed.  Measured: two builds, one before both prune commits and one
after, produce a **byte-identical** `--printallobs` stream — and an
identical `--verbose` dump apart from six header lines — on a range where
the prune removes **5 664 of 7 509 hypothesis slots (75.4 %)**.  That
stream therefore verifies generation and expansion; the prune's own
safety rests on the `__pruned__` self-check and on real-prover verdict
parity.

**The form the solvers do receive is observable — in the solver input
files.**  `--debug tempfiles` keeps them, and each one opens with
`;; Proof obligation:` followed by the shipped sequent and
`;; Generated from file "…", line N, characters a-b`, which is a stable
key.  Two caveats: it needs a **real prover run** (`--noproving` writes
none — measured, zero files), and the names come from
`Filename.open_temp_file`, i.e. random, so they must be renamed by their
key before `diff` can pair them.  That is four lines of shell:

```
for f in $D/*.tlaps/tlapm_*.smt $D/*.tlaps/tlapm_*.znn; do
  k=$(sed -n 's/^;; Generated from file .*line \([0-9]*\), characters \(.*\)/\1-\2/p;/^;; Generated/q' "$f")
  n=1; while [ -e "$OUT/$k.$n.${f##*.}" ]; do n=$((n+1)); done
  cp "$f" "$OUT/$k.$n.${f##*.}"
done
```

after which the whole check is `diff`, and **the subset property is
exactly "the unified diff has no `+` lines"**:

```
diff -ru before/ after/                      # what changed, per obligation
diff -ru before/ after/ | grep '^+[^+]'      # must be empty  ==  subset
```

Verified on the pre-prune/post-prune pair: 11 solver inputs each, paired
by key, **4 200 deleted lines and 0 added**.  That is a stronger property
than "hypotheses only removed" — it forbids reordering too — and it needs
no tool beyond `diff` and `grep`.  Only #2 and #3 need T2.

**Consequence for the guards.**  Since *no* stock output prints what the
solvers receive, and observing it costs a full prover run, the
`--prune-context=none` switch recommended above is not a convenience: it
is the only way a user can bisect a prune-related failure.  Priority 1
stands, and this is the argument for it.

**Per item: the command, and the number that moves.**

| # | run this, before and after | what moves | signal |
|---|---|---|---|
| 1 | `tlapm -N --timing` on a large INSTANCE-heavy module | wall, `analysis` | **strong** — 32.1 s → 3.89 s |
| 2 | `tlapm --noproving --nofp --timing` on a large module | wall, `interaction`, max RSS | **strong** — ×2.7 wall, ×8.7 peak RSS |
| 3 | idem | wall, `interaction` | **strong** — and one corpus stops timing out, which is its own proof |
| 4 | edit inside a proof body in the editor, time to diagnostics; CLI proxy `tlapm --toolbox L L` | latency | **strong** — 59.7 s → 11.5 s |
| 5 | `tlapm -N --timing` | `analysis` | **strong** — 3.74 s → 2.35 s |
| 6 | `tlapm -N --timing`; and edit-to-diagnostics | `parsing`, latency | **strong** — 2.9 s → 1.2 s |
| 7 | `tlapm --noproving --nofp`, median of 3 on a **large** module | wall | **weak per run** — −5…−6 %; needs repetition, invisible on small inputs |
| 8 | run twice, cite the **second** (fingerprints present) | wall | **strong on the warm path**, zero on a cold one |
| 9 | `/usr/bin/time -v`, and sample RSS with `ps` during the run | max RSS, and the *shape* of the curve | **strong** — growth becomes flat |
| 10 | `tlapm --noproving --nofp --timing` on an INSTANCE-heavy module | wall, `interaction` | **medium** — visible on deep contexts, not on shallow ones |
| 11 | `tlapm -N --timing` | `analysis` | **medium alone**, strong with #5 |
| 12 | `tlapm --noproving --nofp` | wall | **weak** — the honest local proof here is the complexity argument (O(distance) index resolution made O(1)); the wall-clock share is a few per cent |
| 13 | after the patch, the **same binary** with and without `--debug noprepcache` | wall, `interaction` | **strong, and self-contained** — the guard makes the A/B observable without two builds |
| 14 | `/usr/bin/time -v`; and the timestamp of the first result message | max RSS, time to first verdict | **strong on memory**, visible on first-verdict latency |
| 15 | `tlapm --chunks 16 --spawn 4` against a plain run | wall; the final failed-obligation line must be identical | **strong** — ×2.24 |
| 16 | "prove this step" in the editor | step-to-verdict latency | **strong** — 5.1–7.9 s → 0.4–1.0 s |
| 17 | edit-to-diagnostics in the editor | latency | **strong** — 11.5 s → 2.0 s |
| 18 | `tlapm -N --timing` on a large module | wall, `analysis` | **weak** — below the noise floor; the local proof is the mechanism, and T1 shows the output is unchanged |
| 19 | a real prover run on an SMT-heavy module | wall | **weak** — same; the regexes are recompiled once per identifier printed today |
| 20 | `tlapm --noproving --timing` | wall, `interaction` | **weak** — same |
| 21 | `tlapm --noproving --timing` | wall, `interaction` | **weak** — same |
| 22 | a real prover run *without* `--debug tempfiles` | wall | **weak** — same |

**Consequence, stated plainly.**  Items 7, 12 and 18 to 22 do not have a
convincing single-run wall-clock signal on stock instrumentation.  Their
pull requests should be argued on the complexity of the code path, with
the instrumented figure quoted as supporting evidence and the joint
measurement of the series as the observable one — not dressed up as
individually measurable.  Everything else stands on its own with a stock
binary and a stopwatch.

## Verification: the protocols, and what differs per item

The same two protocols recur, so they are stated once.

**Test protocol T1 (output-preserving change).**  `dune runtest src` and
`dune runtest lsp` green; the `test/fast` fail-set unchanged (40/48 pass
without Isabelle — any change to that set is a regression, see
`BASELINE.md`); golden dumps **strict-identical** before and after, on
the synthetic family and both real corpora, with
`test/perf/obldump.sh` + `test/perf/oblcheck.py --strict`.  Both dumps
matter and they are different: the *generated* obligations ("to be
proved") and the form printed after expansion and normalisation.  Neither
is what the backends receive — that is the solver input files, see
"Local proof".

**Test protocol T2 (subset change).**  As T1, but the shipped dump is
checked with `--subset`: hypotheses may only be removed, the goal must
be identical, and no obligation may appear or disappear.  Plus a
real-prover run with **verdict parity at the locus level** — the same
obligations proved and unproved at the same source positions.  Used by
#2 and #3 only.

**Measurement protocol P1 (cheap, per commit) — our side.**  Median of 3,
solver-free, on two synthetic sizes and the real corpora: M0, M1, M2, M3.
This is what `_perf/sweep.csv` is, and it is how each commit's effect was
attributed to *that* commit.  It uses our harness; the reviewer-facing
equivalent is the stock recipe above.  **Known defect of the synthetic
corpus**: its obligation contexts share no physical prefix, where real
specs share >99 %, so it mis-ranks anything that depends on the prefix
caches (it told us the early prune was a ×2.1 win; on the real corpora it
is ×3-4 slower).  Never conclude from the synthetic corpus alone on a
cache-sensitive change.

**Measurement protocol P2 (per milestone).**  One real-prover run per
arm, `test/perf/monitor_run.sh` (per-verdict timestamps + RSS samples),
interleaved A/B on an otherwise idle machine, machine fingerprint and
boot recorded.  Absolute values compared only inside one campaign.
Reserved for the one item whose gain is not visible solver-free (#15),
and for B3 of item #0.

**Measurement protocol P3 (interactive).**  `test/perf/lsp_c0.py`
scripted client: didOpen, then a keystroke inside a proof body, timing
to the diagnostics notification; plus **byte-identical notification
streams** between the old and new server as the correctness gate (that
gate is what caught two bugs in the LSP track).  Used by #4, #6, #16,
#17.

Per item, then, only what differs from the above:

* **#1 Deque** — `src/util/deque.ml`. T1, P1.  The gain is concentrated
  in M0/M2, so measure the *parse+elab* metric, not M1: on M1 it looks
  like ×1.14 and would be dismissed.
* **#2 prunes** — `src/backend/prep.ml`.  T2.  The `Opaque "__pruned__"`
  self-check is part of the change: a reachability bug surfaces as that
  opaque leaking into a shipped obligation, i.e. a failing proof, never
  as a silent miscompilation.  Note the Ffi anomaly in the record: on
  that corpus M1 got *worse* at this commit (458 → 842 s) while M3
  dropped 13.9 → 5.1 GB — the prune pays for itself only once the
  caches (#13) are in.  Do not adopt #2 without #13 if that corpus
  shape matters to you.
* **#3 single-pass expand** — `src/backend/prep.ml`.  T1 (the result is
  identical, only the number of rebuilds changes).  P1, and record that
  Ffi M1 completes at all: a timeout becoming a number is the real
  result.
* **#4 LSP pool** — `lsp/lib/docs/proof_step.ml`.  T1 + P3.  Claiming
  semantics must be preserved exactly (first claimer wins, claim =
  range intersection, duplicate ranges collapse); the notification
  stream gate is what proves it.
* **#5/#11 elaboration** — `src/module/m_elab.ml`, `src/expr/e_levels.ml`.
  T1, P1 on M0.
* **#6 parser** — `src/expr/e_parser.ml`.  T1 + P3.  Watch memory: the
  memo table is per-parse and must not outlive it.
* **#7 Property** — `src/util/property.ml`.  T1, P1 *and* P2: −5 % does
  not show above P1's noise on small corpora.
* **#8 printer** — `src/backend/toolbox.ml`.  T1, and the measurement
  must be a **warm** run (all fingerprints present) — on a cold run this
  change is invisible.
* **#9/#14 memory** — `src/expr/e_levels.ml`, `src/backend/schedule.ml`.
  T1, and the metric is the *shape* of the RSS curve over the run, not
  its peak: sample RSS with `monitor_run.sh` and check it is flat.
* **#10/#12 substitution and constness** — T1, P1, with
  `TLAPM_PREP_TIMES` to attribute the gain to the intended stage; a
  stage-level probe is what keeps these from being noise-fitting.
* **#15 chunks** — T1 for the sequential path (the flag off changes
  nothing), plus two dedicated gates: `CHUNK_PARTITION_EXACT` (the union
  of the ranges generates exactly the whole-file obligation set, at the
  same loci) and `CHUNK_VERDICT_PARITY_EXACT` (same failing loci).  P2.
  Note the correctness trap this replaces: hand-chunking with
  `--toolbox` silently drops obligations, because a proof's locus is its
  keyword while its obligations sit at the positions of the facts it
  cites (measured: 4 obligations whole, 2 in lines 1–6, **0** in 7–9).
* **#16 forked prover** — Unix only, and the fork hygiene is the
  substance of the change: reset signal dispositions, `clear_nonblock`
  after `dup2` (tlapm's printers die on `EAGAIN`), leave only through
  `Unix._exit`, parent reaps with `WNOHANG` and no systhreads.  P3, and
  the byte-identical stream gate is not optional here — a first
  implementation corrupted the parent's LSP stream mid-frame.
* **#17 scoped modes** — the gates are `GEN3_STREAM_IDENTICAL`,
  `GEN3_INSERT_STREAM_IDENTICAL`, `GEN3_GAP_STREAM_IDENTICAL`: the
  client-visible notification stream must be byte-identical to full
  recomputation, for a keystroke, an insertion and an edit spanning a
  gap.  Known limitation to carry: inner expression locations of reused
  units are stale by design (fingerprints are position-independent, and
  everything the client sees positionally is shifted) — the
  step-decomposition code actions need the same shifting before these
  modes become defaults.

## What not to port — measured negative results

Five things were tried and should not be re-attempted from this record.
They are here so the effort is not spent twice.

1. **Pruning before expanding** (`TLAPM_PRUNE_EARLY`, on the branch,
   default off).  85 % of every obligation's context is dead weight
   dropped by `prune_context` — but dropping it *early* rebuilds the
   context per obligation and destroys the physical prefix sharing the
   caches live on.  Monolith M1 **286 s → 911 s (×3.2 slower)**, with
   `expand_defs` 49 → 294 s; Ffi **190 s → 842 s (×4.43)**, with
   `expand_defs` 109 → 611 s and peak RSS *up* 0.63 → 0.92 GB.  The dead
   weight is free precisely *because* it is shared: pruning per
   obligation rebuilds the context and destroys the physical prefix
   identity the caches resume from.  Reverted; only the drop-rate
   counters were kept.  Corollary for anyone evaluating the lazy tree:
   per-obligation minimality and cross-obligation prefix sharing
   optimize the same cost and exclude each other.
2. **Name-blind fingerprints.**  Merges 369 classes / 466 obligations on
   the monolith, and **3 of those classes have differing shipped
   forms** — one obligation's result would answer for a different
   problem.  Three counter-examples end it.
3. **Caching elaborated dependencies across versions** (LSP).  Worked
   mechanically, made the keystroke *slower* (6.1 → 10 s), the extra
   time inside the INSTANCE substitution.
4. **De-materialising the obligation array** (lazy generation, shipped
   as `TLAPM_STREAM_GEN`).  Correctness parity everywhere, **no
   performance or memory change**: contexts share their prefixes
   structurally, so retaining 30 k sequents was already nearly free.
   Keep it for what it is — the platform for range-scoped generation —
   not as a perf item.
5. **Overlapping preparation with prover waiting.**  `wait = 0.1 s` over
   259 blocking selects in a 273 s run: the provers are subprocesses and
   already overlap.  There is nothing to overlap.

And one design decision recorded rather than implemented:
**INSTANCE×EXTENDS deduplication** (20.5 % of context definitions on the
INSTANCE-heavy corpus).  The flat-world form — usage-filtered hoisting
with aliases — is fully designed in `INSTANCE_STUDY.md` and was
deliberately not implemented: elaboration is 1.99 s of a 190 s run on
that corpus (1.0 %), so the ceiling is 1 %, and the material it would
remove is in the shared prefix the caches already amortise.  It belongs
to the lazy-tree node design, where it is structural.
