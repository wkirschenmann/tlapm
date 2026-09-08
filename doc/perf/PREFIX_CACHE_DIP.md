# The prefix-cache dip: what got fixed, what didn't, and why

Investigation triggered by a "Preparation rate against position" chart on the
private DotNet binding layer (28,818 obligations) showing a massive
throughput dip at some positions. Corpus: `DotNetBindingTheorems_proofs.tla`
(private, gitignored — only aggregate numbers, line numbers, and operator
*names* are reported here, never formula content). All measurements use
`--noproving --nofp` (exercises the full prep pipeline, no solver). Probes
referenced below are all env-gated, inert unless their variable is set:
`TLAPM_PREP_TIMES`, `TLAPM_EXP_TAIL`, `TLAPM_INST_KEYS`, `TLAPM_INST_MEMO`,
`TLAPM_PREFIX_CURVE`, `TLAPM_EXPCACHE`.

## 1. What was fixed (real, measured, kept)

`Prep.expand_defs_cached`'s prefix cache resumes an obligation's
definition-expansion fold from the longest run of hypotheses that are
physically the same node (`==`) as some recent obligation's — cheap, but a
scan that stops at the first non-`==` pair, even when what follows is
still overwhelmingly shared.

Two independent causes were found and fixed for the *same* divergence
shape (a `Defn` hyp that is structurally identical — same qualified name,
`Expr.Eq.hyp` true — but not physically `==`):

- **`Module.Elab.instantiate` rebuilt its own output on every call**, even
  when a later call was for the exact same `(module, cx_shift, arity,
  local alias, export mode, substitution)` — the module's own EXTENDS
  closure re-walked and re-substituted each time. Measured
  (`TLAPM_INST_KEYS`): 38 calls collapsing to 8 distinct keys on this
  corpus's dotnet window. Fixed by memoizing `instantiate` on that full
  key (commit `c4f78e6`), with `subst` compared structurally (cheap: it's
  bounded by the *instantiated module's own* parameter count, not by file
  or obligation count). Verified: the memo's hit/miss counts match the
  predicted 30 hits / 8 misses exactly, and — independently — the memoized
  `defn` payload (`d == d'`) was confirmed physically shared at every
  sampled divergence (`prep.ml`'s `DEFN==` field, commit `a0c73e3`).

- **The rebuilt payload still gets a fresh wrapper one layer up**
  (`Proof.Anon.anon#defns`/`M_t.hyps_of_modunit` re-wrap a `Defn` hyp
  around the shared `defn` at every textual `INSTANCE` occurrence,
  memoized or not) — so the *outer* hyp the scan compares is never `==`
  even once the inner payload is shared. Fixed by extending the scan's
  equality to accept two `Defn` hyps as equivalent when the inner `defn`
  is `==` (sound: it's still a pointer check, no name involved, no
  structural-equality cost) — and, since `Prep.expand_defs_cached`'s own
  `fold` ignores `wd`/`ex` entirely for a `Visible` `Operator` or for any
  `Bpragma`, relaxed those two fields out of the check specifically in
  those cases (commits `585e3b3`, `892fb3c`; `wd`/`vis`/`ex` breakdown
  confirmed the remaining stop-points were always exactly `vis` — see
  §2).

**Effect measured on the fenêtre `lines 13000–19000` (3667 obligations):**

| | before | after |
|---|---|---|
| long-tail obligations (tail > 1000) | 746 | 599 (**−19.7 %**) |
| `exp:tail` | 44.2 s | 32.5–38.0 s (**−14 to −27 %**) |
| `expand_defs` total | 46.2 s | 34.5–40.2 s |

Validated at every step: `make test` (`dune runtest src`) green; a strict
`--printallobs` dump diff (the *actual* obligation dump lives on stderr,
not stdout — a methodology trap hit once, see §4) byte-identical between
memo-off/memo-on/scan-relaxed states, on a substantial window (153,149
dump lines).

## 2. Where this mechanism's ceiling is

Extending the classification (`prep.ml`'s `div_kind_counts`, commit
`6d9280a`) to *every* long-tail obligation (not just the 25 sampled)
showed the remaining 598/599 stop-points are **all** the same shape:
`Defn`, `Operator`, `wd` and `ex` equal, only `vis` (Visible/Hidden)
differing. That's not a caching artifact: a proof step's `HIDE
DEF <name>` / `USE` / implicit `BY DEF <name>` genuinely flips whether a
named operator is expanded in place (`vis = Visible`, absorbed into the
substitution via `Cons`) or kept as an opaque hypothesis (`vis = Hidden`,
kept via `Bump`) for *that one obligation* — the definition stays at the
same context position either way (a `HIDE` does not remove anything from
the context, only flips this flag), but `Cons` vs `Bump` is a genuinely
different computation, not a representation choice: it changes the de
Bruijn numbering of everything below it (`Expr.Subst.app_ix`'s `Cons`
case removes a level from the count; `Bump` keeps it and shifts). Skipping
past a `vis` mismatch would silently apply the wrong substitution to
everything downstream — unsafe, not merely conservative. Confirmed this
is not a shortcut hiding in the current representation either: is the
*algebra* commutative enough to defer the choice and patch it in later
(the substitution's `Cons`/`Bump`/`Compose` combinators are already
lazy/symbolic)? No — the position's *decision* (`Cons` vs `Bump`) doesn't
depend on the accumulated substitution (only on the hyp's own `vis`), but
every subsequent position's *content* does, since the numbering it reads
already differs. Measured directly (`n_tail_hyp_noop`/`n_tail_hyp_real`,
commit `3e63fae`): 88.3 % of the tail's positions are real rewrites, not
free physical no-ops. This line of investigation stops here.

## 3. The dip's actual location: the fixed mechanism explains a minority of it

Confirmed by an artifact comparing the two curves position-for-position
(published from this session; see chat history for the link) using a new
per-obligation probe (`TLAPM_PREFIX_CURVE`, commit `7da72c4`, extended
with `loc=` in `3705a94`) run over the *whole* corpus (28,818 obligations,
matching `doc/perf/short/rate_by_position/dotnet_p21.csv`'s row order
exactly) and compared windowed (same 40-window scheme as
`charts.py:rate_by_position`) against that existing CSV:

- The **worst throughput window** in the whole run (~29.8 obl/s, vs a
  ~71 obl/s best — a ×2.4 factor) sits at obligation position
  ≈ 4321–8641 (source lines ≈ 10399–17696). Its windowed mean
  prefix-reuse rate there is ≈ 85.7 %, statistically indistinguishable
  from the run's overall mean (≈ 85.9 %) — **not** an unusually poor
  reuse zone. Correlation between the two windowed series across all 40
  windows: r ≈ 0.21 (weak).
- The fixed mechanism's own worst windows (lowest reuse rate: positions
  ≈ 17281, 23041, 25201) correspond to real but *secondary* rate dips
  (~43–44 obl/s), not the primary one.

So: **the fix is real and correctly targeted, but explains only the
secondary dips, not the primary one.**

## 4. The primary dip: same stage, different mechanism — also not fixable this way

Comparing `TLAPM_PREP_TIMES` on the primary-dip zone (lines 11559–17696,
3600 obligations) against a same-sized, non-dip comparison zone (lines
18695–25121, 3600 obligations):

| stage | dip zone | comparison zone | ratio |
|---|---|---|---|
| `exp:tail` | 39.6 s | 12.0 s | **×3.3** |
| `elab_normalize` | 10.6 s | 3.7 s | ×2.85 |
| `action_frontend` | 14.7 s | 14.7 s | ×1.00 (flat — not this) |
| `prune_context` | 6.7 s | 4.2 s | ×1.60 |

`exp:tail` again dominates (+28 s of the +35.7 s total gap ≈ 78 %) — but
per-obligation comparison (same `TLAPM_PREFIX_CURVE` data) shows the two
zones have near-identical reuse rate (85.7 % vs 85.0 %), near-identical
*total* tail size to refold (910,486 vs 1,025,093 positions — the dip
zone is if anything slightly better), and a *smaller* mean context
(1787 vs 1905). None of that explains a ×3.3 stage-time gap: **it's the
cost per refolded position that's higher in the dip zone, not the count
of positions.**

Direct per-obligation timing (`fold_s`, commit `e819550`) confirmed this
quantitatively: cost per tail position averages 4.40e-5 s in the dip zone
vs 1.26e-5 s in the comparison zone (**×3.5**). A companion size probe
(`Obj.reachable_words` on each real-rewrite result, safe — no content
printed, commit `de1df0c`) found the average rewrite ≈1.7× bigger in the
dip zone (38,409 vs 22,721 words) — real, but short of a full
explanation. The clearest pattern is in the *worst* individual
obligations of both zones: a specific, large (~1M-word) structure gets
rewritten near-identically across ~15 consecutive obligations, each
paying the cost separately. Checking the divergent operator *names*
there (safe — identifiers only, e.g. `L1!L0!TypeOK`, `HasStatus`,
`IsActiveCall`, ...) confirms the mechanism: this is the same `vis`-toggle
pattern from §2 (a per-step `BY DEF <name>` citing a possibly-large,
usually-hidden operator), just landing on unusually large operators in
this stretch of the file, and doing so densely.

**Tested and rejected: enlarging the prefix cache.** If the ring buffer
(`expand_cache`, default 12 slots, `TLAPM_EXPCACHE`) were evicting the
useful shared prefix before the next citation of the same big operator
could reuse it, growing it should help. Measured on the dip zone:
12 → 35.1 s, 64 → 32.2 s, 256 → 35.2 s — no monotonic trend, noise-level
differences only. On reflection this is the expected result, not a
surprise: a memo keyed on `(defn, accumulated substitution)` physical
identity can only ever hit where the *substitution itself* recurs
physically — and since a `vis` toggle permanently changes the numbering
for everything downstream (§2), two different obligations essentially
never share the same accumulated substitution past their own divergence
point. Any such memo would be **redundant with what the existing scan
already captures**: wherever the substitution is genuinely shared, the
scan's own prefix already extends that far. There is no hidden reuse
opportunity here for a cache of any size or shape to find.

## 5. Where this leaves things

The primary dip is real work, not a caching gap: individual proof steps
citing large, normally-hidden operators via `BY DEF`, each needing its own
honest expansion. Closing it further would mean changing *what* gets
computed, not *how* it's cached — e.g., substituting only within the parts
of the active goal that actually reference the cited operator, rather
than across the whole carried-forward context on every such citation.
That's a materially bigger, more invasive change than anything in this
document (closer to the "F5 / lazy expansion" family noted as out of
scope in `ANALYSIS.md`), not attempted here.

## Commits (branch `claude/tlapm-performance-optimization-ejlzq7`)

`c4f78e6` (instantiate memo) · `a0c73e3` (probe: memo hits, DEFN==) ·
`585e3b3` (scan sees through the memo) · `6d9280a` (probe: divergence-kind
tally) · `892fb3c` (scan: wd/ex relaxation where `fold` ignores them) ·
`3e63fae` (probe: noop-vs-real refold) · `7da72c4`/`3705a94` (prefix-curve
probe + loc) · `e819550` (probe: per-obligation fold timing) · `de1df0c`
(probe: rewrite-size proxy).
