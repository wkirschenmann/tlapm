#!/usr/bin/env bash
# The monolith's remaining pull-request endpoints.
#
# The fifteen-minute ceiling earns its keep in exactly one place: a FIRST pass over a
# line whose shape is unknown, where it stops one hanging point from eating the
# campaign.  It earns nothing anywhere else, and the previous version of this script
# proved it -- p11 already had its ceiling row from this boot, and the script re-ran
# it at the same ceiling before escalating, so the point cost 900 s + 3600 s to learn
# what 3600 s alone would have said.  Fifteen minutes thrown away per such point.
#
# So the clock is chosen from what the CSV already knows about each point:
#   * a point already stopped at the ceiling starts at the hour -- there is nothing
#     left to learn at fifteen minutes;
#   * once any point on the line has stopped, every point below it starts at the hour
#     too, since a slower commit cannot be quicker;
#   * and the same holds when a point above merely took LONGER than the cheap clock
#     without stopping -- a point that completed in 1277 s tells us just as surely
#     that the ones below it will not finish in 900.  Reading only failures missed
#     this and sent one point back to the cheap clock it could not possibly meet;
#   * only a point with no history at all, below nothing slow, pays the cheap pass.
S=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
BINS=$S/shortbin; OUT=$S/short_sweep.csv
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
SPEC=${SPEC:-"${CORPUS:-$(git rev-parse --show-toplevel)/_perf}/oom_repro/timer_wheel_l1_mono.tla"}
CAP=12000000; CHEAP=900; LONG=3600
sha_of () { grep "^$1:" $S/short_points.txt | cut -d: -f2; }
for pt in ${PTS:-p11 p09 p07 p06 p05 p00}; do
  sha=$(sha_of $pt)
  # already settled?  a completion, or an abort, is the end of the question
  if awk -F, -v p=$pt '$3==p && $5=="mono" && $6=="-2" && ($9==0 || $9==134 || $9==137 || $9==2){f=1} END{exit !f}' $OUT; then
    echo "  have $pt (settled)"; continue
  fi
  # Both questions are asked of the CSV, not of a variable accumulated in this loop.
  # A resumed run skips the points it already has, so a variable misses what they
  # said -- which is how a point that completed in 1277 s failed to stop the point
  # below it from being sent back to a 900 s clock it could not possibly meet.
  PRIOR=0; ABOVE=0
  awk -F, -v p=$pt '$3==p && $5=="mono" && $6=="-2" && $9==124{f=1} END{exit !f}' $OUT && PRIOR=1
  # any commit LATER than this one -- so, faster -- that needed more than the cheap
  # clock, or did not finish at all
  awk -F, -v p=$pt -v c=$((CHEAP * 1000)) '
      $5=="mono" && $6=="-2" {
        q=substr($3,2)+0; me=substr(p,2)+0
        if (q > me && ($9 != 0 || $8+0 > c)) f=1
      } END{exit !f}' $OUT && ABOVE=1
  if [ $PRIOR -eq 1 ] || [ $ABOVE -eq 1 ]; then
    T=$LONG; ph=L
    [ $PRIOR -eq 1 ] && why="already stopped at the ${CHEAP}s ceiling" \
                     || why="a faster commit already needed more than ${CHEAP}s"
    echo "  $pt starts at ${T}s: $why"
  else
    T=$CHEAP; ph=Ap
  fi
  d=$(mktemp -d); t0=$(date +%s%N)
  ( ulimit -v $CAP; cd $(dirname $SPEC) && /usr/bin/time -f "%M" -o $d/r \
      timeout $T $BINS/$pt.exe --noproving --nofp --cache-dir $d/p $SPEC ) >/dev/null 2>&1
  rc=$?; ms=$(( ($(date +%s%N)-t0)/1000000 )); pk=$(tail -1 $d/r 2>/dev/null)
  case "${pk:-}" in ''|*[!0-9]*) pk=0;; esac
  rm -rf $d
  echo "$ph,$BOOT,$pt,$sha,mono,-2,0,$ms,$rc,$pk" >> $OUT
  case $rc in
    134|137|2) v="OOM -- the cap refused an allocation";;
    124)       v="still running at ${T}s";;
    0)         v="completed";;
    *)         v="exit $rc";;
  esac
  echo "  [$ph] $pt mono $((ms/1000))s $((pk/1024))MB : $v"
  # nothing to accumulate: the row just written is what the next point will read
done
echo MONO_DONE
