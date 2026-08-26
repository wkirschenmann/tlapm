# Re-measuring the chain's preparation line

The five leftmost cells of the chain's preparation line read "did not finish in
15 min" because that is all the first campaign spent on them. This run replaces
the whole line -- p00 to p17 -- on a single machine, so the ratios along it are
internally consistent whatever the host is worth in absolute terms.

Rows land in `chain_reline.csv`, same columns as `short_sweep.csv`.

- `phase A` -- one run of the anchor cell (p14) taken before the line, with no
  warm-up, when the plan was still to vouch for the host rather than re-measure
  everything. 168 s against the 146.6-158.5 s recorded on the first campaign's
  host, and 437 MB against 430 MB. Kept because the line re-measures p14 anyway:
  the two p14 values give the factor between the two hosts, which is what any
  later stitching of a cell that is not re-measured would need.
- `phase N` -- the line itself, left to right, one run per point, 12 GB address
  space, three hours per point, one untimed warm-up of each binary first.

`prep_ms` is wall clock; `prep_rc` is 0 for a run that finished, 124 for the
timeout, 134 or 137 for an abort on memory. `peak_kb` is maximum resident set.

## Folding the rows back

`harness/merge_reline.py` appends the phase-N rows to `short_sweep.csv` as
phase L, and skips rows it has already folded, so it can be run after each
point lands. Phase L is not decoration: an abort verdict transfers between
machines -- the cap is 12 GB wherever the run happens -- while a duration does
not. So every verdict this campaign settles reaches the document as soon as it
is measured, and its timings wait until the new boot owns the whole line and a
curve can be drawn from one machine.
