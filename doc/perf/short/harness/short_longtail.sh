#!/usr/bin/env bash
# A ceiling answers "did it finish in 900 s", which is the wrong question for a
# point that finishes in 950.  Here the neighbouring commit completes the chain in
# 734 s, so the one before it is plausibly just over the line -- and "completes,
# slower than its successor" is a different claim from "does not complete".
#
# Re-run, with an hour, every chain point that the campaign stopped at the clock.
# Memory aborts are excluded: more time cannot help a run that ran out of address
# space.  Rows are phase L and the reader prefers them over a ceiling.
set -u
WORK=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
CORPUS=${CORPUS:-"$(git rev-parse --show-toplevel)/_perf"}
S=$WORK
BINS=$S/shortbin; OUT=$S/short_sweep.csv
P=$CORPUS
BOOT=$(awk '/btime/{print $2}' /proc/stat)
LONG_T=${LONG_T:-3600}; CAP=12000000
SPEC=$P/abstractgrpc/FfiGrpcTheorems_proofs.tla
ALL=$(tr '\n' ' ' < $S/short_points.txt)
sha_of () { for p in $ALL; do [ "${p%%:*}" = "$1" ] && echo "${p##*:}"; done; }

# tip-first, so if the pass is cut short the points nearest the completing ones
# -- the informative ones -- are already in
# Only run a point the evidence says can finish.  Every commit is measured on the
# public 1 800-obligation corpus, where nothing fails, so the ratio between two
# adjacent commits there estimates the ratio here; applied to the nearest chain
# point that did complete, it gives an expected time.  Spending an hour to learn
# that a point estimated at seventy minutes does not finish in sixty buys nothing.
PTS=$(python3 - "$OUT" "$BOOT" "$LONG_T" <<'PYEOF'
import csv, sys
out, boot, budget = sys.argv[1], sys.argv[2], float(sys.argv[3])
sy, ch = {}, {}
for r in csv.DictReader(open(out)):
    if r["phase"] != "Ap" or r["boot"] != boot or int(r["prep_ms"]) == -2:
        continue
    if r["corpus"] == "synth300" and int(r["prep_rc"]) == 0:
        sy[r["point"]] = int(r["prep_ms"]) / 1000.0
    if r["corpus"] == "ffi":
        ch[r["point"]] = (int(r["prep_ms"]) / 1000.0, int(r["prep_rc"]))
done = [(p, v) for p, (v, rc) in sorted(ch.items()) if rc == 0]
if not done:
    sys.exit(0)
ref_p, ref_v = done[0]                      # lowest-numbered completing point
run = []
for p in sorted((p for p, (_, rc) in ch.items() if rc == 124), reverse=True):
    if p not in sy or ref_p not in sy:
        continue
    est = ref_v * sy[p] / sy[ref_p]
    ok = est <= 0.9 * budget
    print("%s estimated %.0f s -- %s" % (p, est, "run" if ok else "skip, over budget"),
          file=sys.stderr)
    if ok:
        run.append(p)
print(" ".join(run))
PYEOF
)
echo "chain points worth an extended clock: ${PTS:-none}"
for pt in $PTS; do
  sha=$(sha_of $pt)
  grep -q "^L,$BOOT,$pt,$sha,ffi," $OUT && continue
  d=$(mktemp -d); t0=$(date +%s%N)
  ( ulimit -v $CAP; cd $(dirname $SPEC) && /usr/bin/time -f "%M" -o $d/r \
      timeout $LONG_T $BINS/$pt.exe --noproving --nofp --cache-dir $d/p $SPEC ) >/dev/null 2>&1
  rc=$?; ms=$(( ($(date +%s%N)-t0)/1000000 )); pk=$(tail -1 $d/r 2>/dev/null)
  case "${pk:-}" in ''|*[!0-9]*) pk=0;; esac
  rm -rf $d
  echo "L,$BOOT,$pt,$sha,ffi,-2,0,$ms,$rc,$pk" >> $OUT
  echo "  [L] $pt ffi ${ms}ms rc=$rc ${pk}kB"
  [ $rc -ne 0 ] && { echo "  stopping: $pt did not finish inside ${LONG_T}s either, so the ones below it will not"; break; }
done
echo LONGTAIL_DONE
