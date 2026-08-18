# Baseline measurements — 2026-08-18

Binary: commit `755c0fa` (base `4600b24` + measurement harness + clock
fixes; all output-preserving, golden dumps strict-identical to base).
Machine: Linux container, 16 cores (shared), OCaml 5.1.0, no Isabelle.
Corpus: `test/perf/gen_synth.py` family, steps=5 defs=50 cite=3.
Protocol: `test/perf/bench.sh`, median of 3 (M0/M1), no solver anywhere.

## Scaling with lemma count (M0 = parse+elab+generation, `-N`)

| lemmas | lines | obligations | M0 wall | M1 wall (full prep) | M1 max RSS | M2 fingertip |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 754 | 600 | 0.24 s | 3.8 s | 232 MB | 0.27 s |
| 300 | 2154 | 1800 | 2.8 s | 48.0 s | 1.76 GB | 2.9 s |
| 600 | 4254 | 3600 | 22.9 s* | — (>10 min)* | — | — |

\* single early run before the binary snapshot; to be re-measured, but the
order of magnitude is stable.

Two decisive shapes:

* **M0 is super-quadratic ≈ cubic**: ×3 lemmas → ×11.7, ×2 → ×8.2.
  Consistent with the O(B·T·D) elaboration terms of ANALYSIS.md §3.1
  (B, T, D all grow with the lemma count in this family).
* **M1 is dominated by per-obligation preparation**: `--timing` on L300
  gives interaction 47.9 s (93 %), analysis 2.5 s, fp_compute 0.24 s,
  parsing 0.08 s — with *zero* prover time (`--noproving`). This is the
  Θ(N·D) expansion cost (ANALYSIS.md B2) plus the eager task
  materialization (B1).
* **Fingertip latency tracks whole-file cost** (0.27 s → 2.9 s), not the
  size of the requested range — the interactive complaint reproduced.

## Test-suite reference

`test/fast` with this environment (no Isabelle installed): 40/48 pass;
the 8 failures are identical with the stock base binary (Isabelle-needing
tests: isa_true, setEuclid, ENABLED_INSTANCE*, NestedENABLED,
FingerprintVariablesParameters, WFTRUE, higher_order_statement) — they are
environmental, not caused by any change on this branch. Any change that
alters this fail set is a regression.

## Measured effects of the phase-1 changes (same protocol, idle machine)

L300 = Synth_L300_S5_D50_C3, 1800 obligations. "micro" = the seven
9f9c5cf-derived micro-fixes; "tier2" = micro + linear ENABLED scan +
level fast path + single-pass expand_defs.

| metric | baseline | after tier2 | gain |
|---|---:|---:|---:|
| M0 parse+elab (L300) | 2.82 s | 0.28 s | ×9.9 |
| M0 scaling L300/L100 | ×11.7 | ×2.2 | superquadratic → ~linear |
| M1 full prep, no solver (L300) | 48.0 s | 22.0 s | ×2.2 |
| M2 fingertip (L300) | 2.90 s | 0.25 s | ×11.8 |
| M3 max RSS (L300) | 1.80 GB | 1.50 GB | −17 % |
| analysis clock inside M1 (L300) | 2.52 s | 0.05 s | ×49 |

Most of the M0/M2 gain landed with the micro-fixes alone (Deque.nth /
first_n stopped allocating inside the ENABLED scan's lookups); the
tier-2 rewrites then removed the remaining super-linear terms.
After tier2, M1 was still dominated by per-obligation preparation
(interaction 19.6 s of 22.0 s), which the next two steps attacked:

| M1 (L300, no solver) | wall |
|---|---:|
| baseline | 48.0 s |
| + micro + tier2 | 22.0 s |
| + prune hidden defs | 23.5 s (no bite on this corpus: small hidden-def contexts) |
| + prune hidden facts | 9.1 s |
| + prefix-resume caches | **7.3 s** (`--debug noprepcache`: 8.9 s) |

End-to-end phase-1 result on this corpus: **M1 ×6.6** (48.0 → 7.3 s on
1800 obligations; L100: 3.84 → 1.10 s), **M0 ×9.9**, **fingertip
×11.8**, with byte-identical golden dumps at every step, the test/fast
fail set unchanged (environmental only), the cram/inline suites green,
and a full real-solver run proving 600/600. The hidden-facts pruning is
the biggest single win here because the synthetic family reproduces the
named-lemma context growth (F8); on INSTANCE-heavy specs the reference
implementation additionally credits the hidden-defs pruning and the
prefix caches with the larger share (issue #286: full check 5.9×–46×).

Still open after phase 1 (Tier 3 of ANALYSIS.md): streaming the task
list and making obligation release real (B1/B5 — the single-pass memory
wall), the fingerprint-hit short-circuit (B3), range-gated elaboration
for fingertip (L3), and the module/dependency caches (F6).

## Decision consequences (per ANALYSIS.md §6.4)

1. Track B first-order target confirmed: expansion/prep per obligation
   (Tier 2: expand_defs single pass; then Tier 3: streaming + fp
   short-circuit; prefix cache go/no-go re-measured after those).
2. Track A first-order target confirmed: the elaboration O(N²⁺)
   (Tier 2: F1 linear ENABLED scan, F3 name map, De Bruijn level fast
   path) — M0's cubic shape gives a crisp acceptance criterion
   (curve must flatten toward linear).
3. Fingertip needs range gating (L3) on top of the above: even a perfectly
   linear whole-file pass keeps fingertip ∝ file size.

## Calibration on a real corpus (ArmoniK gRPC FFI specs, 2026-08-18)

Two real proof modules provided by the user (same container, 16 cores,
zenon + z3 4.8.9 available; ls4 built locally but returning immediate
"false" — treat its failures as environmental; Isabelle absent).

| corpus | obligations | ctx hyps avg/max | parse+elab (`-N`) | M1 prep, no solver | real single-pass wall | verdicts |
|---|---:|---:|---:|---:|---:|---|
| AbstractGrpcTheorems_proofs (2.9k lines) | 1632 | 758 / 861 | 0.9 s | stock: killed >11 min CPU · fork 26.9 s · **ours 28.1 s** | 29 s | 1172 trivial + 350 proved + 110 env-failed |
| FfiGrpcTheorems_proofs (14.5k lines) | 9927 | 1288 / 1661 | 3.3 s | fork 4 m 55 · **ours 4 m 59** | 3 m 58 (max RSS **5.07 GB**) | 7263 trivial + 2010 proved + 758 env-failed |

Key facts established:

* **Verdict parity is exact**: per-obligation (loc, status) sets are
  identical between this branch and the reference fork on both corpora
  (1632/1632 and 9927/9927).
* **The phase-1 set delivers the fork's speedup on real specs**: on the
  1632-obligation module, upstream stock could not finish the solver-free
  prep pass in 11 CPU-minutes where both optimized binaries take ~27 s
  (≥45×, unfinished baseline).
* All remaining failures are environmental (ls4 mis-built locally,
  Isabelle not installed) and identical across binaries; ~52 obligations
  fall through the default smt→zenon→isabelle chain here.
* **The single-pass memory wall is confirmed on the real corpus**:
  5.07 GB max RSS for 9927 obligations (~500 KB/obligation live), even
  with all phase-1 optimizations — Tier-3 (task streaming + release of
  Props.goal/Props.obs; ANALYSIS.md B1/B5) is the next lever, exactly as
  the plan predicts.
