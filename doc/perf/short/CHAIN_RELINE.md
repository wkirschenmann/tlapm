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

## The two control corpora, repeated

`controls.csv` holds a separate sweep: the 20-obligation and 600-obligation
corpora, all eighteen points, twelve repeats each, both metrics, with nothing
else running on the machine. Its purpose is the split between the front end and
preparation proper.

`tlapm -N` sets `suppress_all`, which skips `process_obs` -- the whole
per-obligation pipeline. `--noproving` runs that pipeline and sends nothing to
the backends. So preparation proper is the difference of the two, and on the
20-obligation control that difference is 17 ms out of 108: one run of each
cannot measure it, because the noise on either is the same size as the answer.
Twelve of each, compared on medians, can.

Columns are the sweep's; phase R, one row per run, `-2` in the metric the run
did not measure.

## Counting how far an aborted run got -- and how not to

`partial_oom.csv` holds, per aborted cell, how many obligations were prepared
before the cap refused the run.

The first attempt counted `@!!status:to be proved` and was wrong. That message is
printed for the whole obligation array in one loop *before* `process_obs`
(tlapm_lib.ml:1126), so counting it returns the corpus total wherever the run
dies. It reported 29 965 of 29 965 on the monolith at two different commits,
which read as "preparation completes and the run dies holding the result" -- and
that reading cannot be true, because the prefix-resume caches of PR6 would then
have nothing to speed up.

An obligation has been prepared when it reaches `really_ship` (prep.ml:1810),
which under `--printallobs` prints `normalized`. `really_ship` runs more than
once per obligation, so distinct ids are counted, and the trivial ones are added
because they are decided without being shipped: on the 20-obligation control,
15 normalized plus 5 trivial.

One caveat stays. `--printallobs` forces the shipped form to be built, which
plain `--noproving` skips, so these runs do more per obligation than the timed
ones and their wall can fall at a different index. The count is a measure of
progress through preparation, not a reading of the timed run.
