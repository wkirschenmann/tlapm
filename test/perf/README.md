# tlapm performance harness

Companion tooling for `doc/perf/ANALYSIS.md`. Three goals:

1. **Mechanical validity**: prove that a change did not alter what the
   backends receive (`obldump.sh` + `oblcheck.py`). This encodes the hard
   criterion "backends receive a subset of what they receive today".
2. **Cheap measurements first**: the level hierarchy M0–M4 below. Full
   solver runs (M4) are reserved for milestones; everything else runs in
   seconds to minutes with no solver at all.
3. **Reproducible corpus**: `gen_synth.py` generates scaling families of
   provable specs; real specs are used once to calibrate the shapes.

## Measurement levels

| level | command | cost | answers |
|---|---|---|---|
| M0 | `tlapm -N --toolbox 0 0` + `TLAPM_TRACE_DEFS=1` | seconds | obligation count/set, context statistics |
| M1 | `tlapm --noproving --printallobs --nofp` | seconds–minutes | full preparation pipeline cost, zero solver. `--printallobs` is load-bearing: it forces the normalization/expansion lazy that `--noproving` alone would skip (`src/backend/prep.ml:1418-1431`) |
| M2 | `tlapm --toolbox L L --noproving …` at sampled lines | tens of seconds | interactive ("fingertip") latency; fixed vs per-obligation cost |
| M3 | M1 under `/usr/bin/time -v` (or RSS sampling) | = M1 | live-memory slope per obligation |
| M4 | real provers, whole file | 10 min–hours | verdicts + end-to-end wall time. Milestones only, interleaved A/B pairs, ±20 % wall-clock noise floor — compare verdict-indexed curves, never a single wall-clock number |

## Tools

### `gen_synth.py` — synthetic spec generator

    python3 test/perf/gen_synth.py --lemmas 200 --steps 5 --defs 100 \
        --cite 3 --out _perf/synth_L200.tla

Generates a self-contained, SMT-provable module whose shape stresses the
mechanisms identified in `doc/perf/ANALYSIS.md`: `--defs` operator
definitions (Hidden, expanded on citation), `--lemmas` named lemmas (each
becomes a Visible statement in the context of all following obligations —
the Θ(N²) term), `--steps` proof steps per lemma, `--cite` definitions
cited per `BY DEF`. Sizes are printed on stdout. Deterministic output.

### `obldump.sh` — golden obligation dumps

    test/perf/obldump.sh <tlapm-bin> <spec.tla> <outdir> [extra tlapm args]

One `--noproving --printallobs --nofp --threads 1` run; splits the `@!!`
stream into:

* `generated.txt` — the `status:to be proved` blocks (obligation set and
  statements, emitted before any preparation);
* `shipped.txt` — the `status:normalized` blocks (the exact material that
  would be sent to the backends, after expansion — where the subset
  criterion lives);
* `raw.log` — everything, for debugging.

Volatile fields (`time-used`, `id` renumbering) are normalized out; blocks
are keyed and sorted by `loc`.

### `oblcheck.py` — subset-invariant checker

    python3 test/perf/oblcheck.py --strict  <baseline-dir> <candidate-dir>
    python3 test/perf/oblcheck.py --subset  <baseline-dir> <candidate-dir>

* `--strict` (default): both dumps must be identical up to volatile fields.
  Required for every output-preserving change (Tiers 1–3 of the analysis).
* `--subset`: `generated.txt` must be identical (no new/changed
  obligations); in `shipped.txt`, per obligation, every hypothesis line of
  the candidate must be present in the baseline and the goal must be
  identical. Only for explicitly-flagged pruning changes (Tier 4).
  The comparison is line-based on the pretty-printed sequent; it is a
  conservative gate, not a parser — a layout-changing commit must be
  validated in strict mode separately from a pruning commit.

Exit code 0 = pass. Differences are reported per obligation location.

### `bench.sh` — M0/M1/M2/M3 matrix

    test/perf/bench.sh <tlapm-bin> <outdir> <spec.tla> [<spec.tla> ...]

Writes `<outdir>/bench.csv` (`spec,level,metric,value` rows) and keeps the
`--timing` reports. Runs each level 3× and reports the median wall time.

## Workflow for a candidate change

1. Baseline: `obldump.sh` + `bench.sh` on the synthetic family (3 sizes)
   with the pre-change binary.
2. Apply the change; rebuild.
3. `oblcheck.py --strict` (or `--subset` for pruning) against the baseline
   dumps — any unexplained difference stops the change.
4. `bench.sh` again; the change must move the metric its analysis predicts
   (e.g. an O(N²)→O(N) fix must flatten the scaling curve), not merely the
   noisy total.
5. `make test` (full suite) before commit.

Generated specs and results live outside the source tree (suggested:
`_perf/`, gitignored). Do **not** name generated files `*_test.tla`: the
`test/` harness picks that suffix up.
