# The short proposal, and how its numbers are produced

`SHORT_PROPOSAL.html` is generated, not written. `mkshort.py` reads the CSVs in
this directory and emits the document; no figure in it is typed in by hand, and a
cell that was not measured renders as a dash rather than as a plausible number.

```sh
python3 doc/perf/short/mkshort.py      # -> doc/perf/SHORT_PROPOSAL.html
```

| file | what it holds |
|---|---|
| `shortlib.py` | the readers: one boot per campaign, sentinels rather than numbers for a run that hit a ceiling or the memory cap |
| `charts.py` | the one chart shape every curve uses, and the per-commit labels |
| `content.py` | the prose of each pull request and each commit, kept apart from the generator so it can be read on its own |
| `mkshort.py` | the sections, the series, and the assembly |
| `short_sweep.csv` | generation, preparation and peak resident set per commit per corpus |
| `short_iterlat.csv` | iteration latency: warm prover, full fingerprint cache, one edit |
| `short_keystroke.csv` | `didChange` to `publishDiagnostics`, at the LSP protocol boundary |

## What the protocol protects against

**One boot.** Absolute values are not comparable across container restarts, or
across machines — this campaign's host is a 2.10 GHz Xeon where an earlier one was
2.80 GHz, and preparation of the 1 800-obligation synthetic is *faster* here
(42.3 s against 51.0 s), so nominal clock does not even order them. Every row
carries `/proc/stat` `btime` and every reader filters to a single boot. A campaign
split by a restart is not averaged: the missing cells stay missing.

**Failures are reported as themselves.** A run stopped at the wall-clock ceiling
and a run that exhausted the 12 GB address-space cap are different facts, and
neither is a number. A ratio against either would be fiction, which is why the
first chart is throughput rather than speedup: on the two private specifications
`main` has no value to divide by.

**`main` twice.** Once at the start of the campaign and once at the end. The gap
between them is the drift the whole curve carries, and it is published rather than
smoothed. On this campaign it is under 1 % on every corpus.

**Resume, not restart.** Keyed on (phase, boot, point, corpus): an interrupted
campaign costs the point in flight, not the pass.

**Pass order chosen for interruption.** Small corpora first, because they give the
whole curve cheaply. On the large corpora, generation for every point before any
preparation.

## What the metrics are

All five are things a user can time from outside tlapm with stock flags on a stock
build. No probe, no patched binary, nothing the proposed commits introduce.

| metric | command |
|---|---|
| generation | `tlapm -N --nofp` |
| preparation | `tlapm --noproving --nofp` |
| peak memory | `/usr/bin/time -f %M` on the preparation run |
| iteration latency | `tlapm --toolbox L H` over a full fingerprint cache, one proof step edited |
| keystroke → diagnostics | an LSP client: `didChange` sent, `publishDiagnostics` received |

The two private specifications are a customer's. They are not in this repository
and are not published; only the measurements taken on them are.
