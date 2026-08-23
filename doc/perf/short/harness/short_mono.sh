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
#   * only a point with no history at all pays the cheap pass first.
S=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
BINS=$S/shortbin; OUT=$S/short_sweep.csv
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
SPEC=${SPEC:-"${CORPUS:-$(git rev-parse --show-toplevel)/_perf}/oom_repro/timer_wheel_l1_mono.tla"}
CAP=12000000; SEEN_STOP=0
sha_of () { grep "^$1:" $S/short_points.txt | cut -d: -f2; }
for pt in ${PTS:-p11 p09 p07 p06 p05 p00}; do
  sha=$(sha_of $pt)
  # already settled?  a completion, or an abort, is the end of the question
  if awk -F, -v p=$pt '$3==p && $5=="mono" && $6=="-2" && ($9==0 || $9==134 || $9==137 || $9==2){f=1} END{exit !f}' $OUT; then
    echo "  have $pt (settled)"; continue
  fi
  # was it stopped at a ceiling before, on any boot?
  PRIOR=0
  awk -F, -v p=$pt '$3==p && $5=="mono" && $6=="-2" && $9==124{f=1} END{exit !f}' $OUT && PRIOR=1
  if [ $PRIOR -eq 1 ] || [ $SEEN_STOP -eq 1 ]; then
    T=3600; ph=L
    [ $PRIOR -eq 1 ] && why="already stopped at the ceiling" || why="a point above it stopped"
    echo "  $pt starts at ${T}s: $why"
  else
    T=900; ph=Ap
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
  [ $rc -ne 0 ] && SEEN_STOP=1
done
echo MONO_DONE
