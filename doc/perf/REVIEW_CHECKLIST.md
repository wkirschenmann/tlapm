# Internal review checklist for tlapm performance patches

Derived from the observed review practice of upstream `tlaplus/tlapm`
(merged and stalled PR threads, CONTRIBUTING.md/DEVELOPING.md, CI config, as
of 2026-08-18). Every change on this branch must pass this checklist
**before push**; the filled checklist is kept with the work so the evidence
is ready when the upstream PRs are opened. Items marked *(upstream-time)*
only bind when a PR is actually opened against `tlaplus/tlapm`.

## Context: what upstream review demonstrably cares about

* Reviewers: muenchnerkindl (semantics/soundness, merges most PRs), lemmy
  (same-day first reviews, edge cases, policy), ahelwer (CI/tests; demands
  tests *before* the change — PR #177), kape1395 (re-measures perf claims
  himself — PR #198), damiendoligez (deep OCaml review), glondu (OCaml
  idiom; reviews the efficiency of efficiency patches — PR #285).
* Perf PRs that merged were **small (1–5 commits), single-mechanism, opt-in
  or provably behavior-preserving, with a reviewer-runnable repro**
  (#198, #222, #283, #285). Mega-branches stall for years (#148, #177) and
  minimal extractions from them merge in weeks (#148 → #198).
* Regressions get **reverted, not patched forward** (#186 → revert #221 →
  redo #222 behind a default-off flag).
* AI policy: no merged policy, but the draft (#264) and maintainer practice
  (#285 is Claude-co-authored, with tests and numbers) converge on:
  human-first contact, per-commit disclosure of the model used.
  Issue #286 (our context) has had no maintainer reply — silence is not
  rejection; the unblocking channels are issue comments and the monthly
  community meeting.

## Checklist

### A. Scope and series

- [ ] **A1** One mechanism per commit; no drive-by refactors, no formatting
  churn outside touched lines, no unrelated fixes.
- [ ] **A2** The commit message states: the mechanism, the invariant
  ("output-preserving" / "shipped context becomes a subset, behind flag X"),
  the complexity change, and the measurement that justifies it.
- [ ] **A3** Each commit builds and passes `make test` on its own
  (DEVELOPING.md: logical, publishable sequence; no reliance on squash).
- [ ] **A4** *(upstream-time)* The PR maps to exactly one mechanism, links
  issue #286, states what is deliberately NOT changed, names the follow-ups
  in the series, and is preceded by a human comment on #286.

### B. Behavior preservation

- [ ] **B1** Default behavior is bit-for-bit unchanged: the golden-dump
  checker (`test/perf/oblcheck.py --strict`) passes against the pre-change
  baseline on the synthetic corpus and `test/fast`.
- [ ] **B2** Any semantics-visible change (pruning) is behind an **opt-in
  flag defaulting to off**, and is validated with
  `oblcheck.py --subset` plus full proof runs on the pruning-sensitive
  corpus (precedent: #222, #283).
- [ ] **B3** **Fingerprint impact statement** in the commit message: does
  the change alter fingerprints or cache-hit semantics, and how do stale
  fingerprint files behave (muenchnerkindl's concern on #283).
- [ ] **B4** Edge cases self-reviewed for the classes reviewers actually
  caught: numeric clamping/underflow, timeout/watchdog/prover-process
  lifecycle interactions, exit codes and error friendliness
  (lemmy on #282/#283).

### C. Tests

- [ ] **C1** A behavior-preserving change is covered by existing suites; if
  it touches an area with thin coverage, a small `*_test.tla` regression
  test is added first, in its own commit (ahelwer's tests-first demand,
  #177).
- [ ] **C2** A performance fix for a pathological complexity includes a
  small spec that *demonstrates* the pathology, runnable via
  `dune runtest`, in the style of #285's regression test — or, when the
  pathology needs sizes unsuitable for CI, a `test/perf/gen_synth.py`
  recipe in the commit message.
- [ ] **C3** Full `make test` passes locally; *(upstream-time)* on both CI
  compilers (OCaml 4.14.1 and 5.1.0); any new CI step stays under the
  ~5-minute budget (ahelwer, #257).

### D. Performance evidence

- [ ] **D1** Before/after numbers from `test/perf/bench.sh` at the level
  the analysis predicts (M0–M3), on at least 3 synthetic sizes — the change
  must move **its own predicted curve**, not just the noisy total.
- [ ] **D2** A command-line repro recipe a reviewer can run on a public
  spec (reviewers re-measure claims themselves — kape1395/damiendoligez on
  #198). Machine and noise floor stated (±20 % wall clock).
- [ ] **D3** The new code is itself efficiency-reviewed: no linear scan
  inside a loop, no assoc-list where a map is due, no per-call regex or
  closure reconstruction (glondu's review of #285 — this exact review will
  happen to us).

### E. Mechanics

- [ ] **E1** Style matches the surrounding code; `.ocamlformat`
  (version 0.29.0, default profile) compatible on touched regions only —
  no whole-file reformat diffs.
- [ ] **E2** No new opam dependency without prior discussion.
- [ ] **E3** AI assistance disclosed per commit via `Co-Authored-By:`
  naming the model (draft policy #264; maintainer practice #285).
- [ ] **E4** *(upstream-time)* Every commit DCO signed-off
  (`git commit -s`) — hard bot gate on upstream PRs.
- [ ] **E5** *(upstream-time)* Respond to review comments within days;
  pivot quickly if a maintainer proposes another approach (#256 → #258
  merged after a 3-day pivot; stalling is how PRs die — #177).

## Known gaps in the evidence

Contributor-graph statistics were unavailable; the absence of a PR template
is inferred from a possibly-incomplete `.github/` listing; no direct
evidence on naming-convention preferences; quoted review sentences may be
lightly condensed — verify exact wording before quoting maintainers
publicly.
