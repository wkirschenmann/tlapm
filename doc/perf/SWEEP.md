# Per-commit performance sweep — 2026-08-18

Every commit of the branch was built and measured on an idle 16-core
container (median of 3 for sub-second metrics, single run otherwise).
Raw data: `_perf/sweep.csv`, `_perf/sweep_ffi.csv`, `_perf/sweep_ffi_m1retry.csv`
(reproduce with `test/perf/` + the sweep scripts described there).

Metrics — what characterizes what:

* **P1 (interactive latency)** = **M2** (one `--toolbox L L` "fingertip"
  invocation: what a VSCode user waits for on every interaction),
  decomposed by **M0** (`-N`: parse + elaboration + generation, the fixed
  cost replayed each time).
* **P2 (full-run time/memory)** = **M1** (whole pipeline with
  `--noproving --printallobs`: tlapm's own cost, no solver noise) and
  **RSS** (max resident set of the M1 run).

Corpora: `Synth_L300` (synthetic, 1800 obligations, lemma-dense),
`AbstractGrpcTheorems_proofs` (real, 1632 obligations, 758-hyp contexts),
`FfiGrpcTheorems_proofs` (real, 9927 obligations, 1288-hyp contexts).
Noise floor: ±3–6 % (same binary re-measured under doc-only commits).
TO = timeout (200 s for Abs, 420 s / 2400 s for Ffi). TO\* = implied
(Ffi is strictly heavier than Abs, which already times out).

## Interactive track (P1)

| # | commit | M0 synth | M2 synth | M0 Abs | M2 Abs | M0 Ffi | M2 Ffi |
|---|---|---:|---:|---:|---:|---:|---:|
| 0 | base upstream | 2.13 s | 2.37 s | 2.43 s | 2.44 s | 32.1 s | 33.0 s |
| 3–5 | timing clocks (control) | 2.1 s | 2.2 s | 1.9 s | 2.4 s | 31.8 s | 31.9 s |
| **7** | **Deque nth/first_n/equal** | **0.32 s** | **0.36 s** | **0.59 s** | **0.91 s** | **3.9 s** | **3.7 s** |
| 9–14 | Ctx, smtlib, app_ix, flatten, tempfiles, schedule | ~0.34 s | ~0.36 s | ~0.59 s | ~0.95 s | ~3.9 s | ~3.7 s |
| **15** | **linear ENABLED scan** | 0.26 s | 0.28 s | 0.46 s | 0.95 s | **2.35 s** | **2.10 s** |
| 16 | de Bruijn level fast path | 0.27 s | 0.31 s | 0.51 s | 0.84 s | 2.22 s | 2.04 s |
| **17** | **expand_defs single pass** | 0.29 s | 0.28 s | 0.52 s | **0.60 s** | 2.26 s | 2.13 s |
| 20 | prune hidden facts | 0.27 s | 0.28 s | 0.57 s | 0.52 s | 2.60 s | 2.61 s |
| 24 | final | 0.26 s | 0.26 s | 0.51 s | 0.50 s | 2.41 s | 2.32 s |

**Reading:** P1 is decided by two commits. The Deque fix (#7) alone gives
×6.7–×8.9 on all three corpora (its allocations sat under every context
lookup of elaboration); the linear ENABLED scan (#15) adds ×1.4–×1.8.
On the biggest real spec the fingertip goes **33.0 s → 2.1 s (×15.7)**.
expand_defs (#17) further helps the Abs fingertip (0.95 → 0.60 s) because a
fingertip also prepares the in-range obligations.

## Full-run track (P2)

| # | commit | M1 synth | RSS synth | M1 Abs | M1 Ffi | RSS Ffi |
|---|---|---:|---:|---:|---:|---:|
| 0 | base upstream | 61.5 s | 1.81 GB | TO >200 s | TO\* | — |
| 7 | Deque | 44.8 s | 1.81 GB | TO | TO\* | — |
| 15–16 | ENABLED + levels | ~44 s | 1.8 GB | TO | TO\* | — |
| **17** | **expand_defs single pass** | **30.2 s** | 1.50 GB | **99 s** | **458 s** | **13.9 GB** |
| 19 | prune hidden defs | 28.5 s | 1.46 GB | 97.7 s | 524 s | 13.9 GB |
| **20** | **prune hidden facts** | **11.2 s** | **173 MB** | **55.1 s** | 842 s | **5.11 GB** |
| **21** | **prefix-resume caches** | **8.5 s** | 174 MB | **25.7 s** | **310 s** | 4.71 GB |
| 24 | final | 8.5 s | 174 MB | 26.0 s | 310 s | 4.71 GB |

**Reading:**

* **expand_defs (#17) is the unlock** on real specs: both real corpora go
  from unmeasurable to measurable (Abs: TO → 99 s; Ffi: TO\* → 458 s).
* **prune hidden facts (#20) is corpus-dependent — by design.** Where dead
  theorem statements dominate the context (synthetic, Abs) it halves M1
  and, on the synthetic, collapses RSS ×10. On Ffi its prune pass *costs*
  time in the solver-free pipeline (524 → 842 s: M1 stops before the SMT
  encoders, which is where pruning pays back) while still cutting RSS
  **13.9 → 5.1 GB**. The prefix caches (#21) then amortize the prune pass
  and more (842 → 310 s).
* **The commit-by-commit curve is not monotonic; the set is what wins.**
  Never judge #20 alone on M1: its payoff is memory (×2.7 on Ffi) plus
  encoder time that M1 does not see.
* **The remaining 4.7 GB on Ffi is the B1/B5 retention** (obligations kept
  alive until end of run), not dead context: on the synthetic the same
  pipeline ends at 174 MB. This is the measured case for the next phase
  (task streaming + releasing Props.goal/Props.obs).

## Controls

Doc-only commits and the timing-clock commits move nothing beyond the
±3–6 % noise floor, as expected. Ctx/smtlib/app_ix/flatten/tempfiles/
schedule are neutral on these corpora — their targets (SMT print time,
verdict stability under load) are not exercised by M0–M2.

## Addendum — throughput curves and the memory wall, reproduced (2026-08-18)

Follow-up measurements requested during review of the sweep.

**No intermediate M1 unlock before #17.** The base binary and the
commit-16 binary (everything up to the de Bruijn fast path, i.e. the
reference fork minus its four backend commits) both exceed a 40-minute
timeout on the FfiGrpc solver-free prep. The unlock is entirely
`expand_defs` (#17): >2400 s → 458 s (≥5.2× as a hard lower bound).
Commits 7–16 improve parse/fingertip (33 s → 2.2 s) but not the prep wall.

**Per-verdict timestamped runs** (`test/perf/monitor_run.sh`, real
solvers, FfiGrpc, quartiles of the verdict index):

| binary | throughput by quartile | RSS by quartile | outcome |
|---|---|---|---|
| final (#24) | 67.7 → 52.2 → 48.2 → 37.4 verdicts/s | 1.6 → 2.4 → 3.6 → 4.9 GB | completed, 204 s |
| #17 only | 19.1 → 15.4 → 11.3 → 10.5 verdicts/s | 3.5 → 6.6 → 10.2 → 13.6 GB | **OOM-killed at verdict 4440/9927** (memcg kill at 13.9 GB anon-RSS, confirmed in dmesg) |

Both curves decline monotonically as the live heap grows (÷1.8 within a
single run, on a machine with ample RAM, no swap and no Isabelle — the
user's 7.7 GB machine shows ÷3 on a 26k-verdict monolith run, with the
same shape). This is the memory→speed coupling measured directly:
throughput is a function of live-heap size, and the wall is real — the
pre-pruning binary dies mid-run even on a 15 GB container once solver
processes are running alongside.

**External datapoints (user's monolith, ~30k obligations, 7.7 GB
machine, reference fork):** unpatched: RSS slope 380 KB/verdict,
OOM at 17.5k; with chunked `Gc.compact`: post-compaction floor
177 KB/verdict (live, uncollectable), OOM at 26k; throughput ÷3 across
the run in both cases. The 380/177 ≈ 2.15 ratio matches OCaml's default
GC space overhead, separating GC lag (fixable by tuning) from live
retention (fixable only by dropping references).

**Consequence for the next phase (task streaming + obligation release):**
acceptance is not a wall-clock number but two curve properties measured
by `monitor_run.sh`: (a) RSS flat (bounded by the in-flight window) for
the whole run, and (b) throughput independent of the verdict index,
lower-bounded by today's small-chunk throughput. On the user's monolith
that projects the 30k-obligation single pass at roughly the chunked
throughput (~43 verdicts/s) instead of dying at 26k.

## Addendum 2 — the retention hypothesis, corrected (2026-08-19)

The line above («the remaining 4.7 GB on Ffi is the B1/B5 retention»)
was the audit's guess, and the phase-4 probe **disproved it**: with
no-op tasks the obligation array plus the proof tree hold a constant
~25 MB, and the entire linear accumulation comes from the
level-memoization cache in `src/expr/e_levels.ml` pinning one
preparation context per obligation on shared syntax nodes. The
attribution table (E1–E8), the ~20-line fix, and the gate measurements
(FfiGrpc real-solver RSS 4.9 GB → 439 MB flat, wall unchanged) are in
doc/perf/PHASE4.md «Results». This is exactly why phase 4 was gated on
a probe before any surgery.
