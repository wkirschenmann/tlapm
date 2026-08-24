#!/usr/bin/env bash
# Final campaign for the short proposal branch, one boot, one machine.
set -u
# Set WORK to a scratch directory (worktree, cached binaries, CSVs) and
# CORPUS to the directory holding the .tla corpora.  Both default to values
# that suit a checkout of this repository.
WORK=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
CORPUS=${CORPUS:-"$(git rev-parse --show-toplevel)/_perf"}
mkdir -p "$WORK"
S=$WORK
W=$S/shortwt
[ -d "$W" ] || git worktree add -f --detach "$W" tlapm-perf-short
OUT=$S/short_sweep.csv
BINS=$S/shortbin
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
P=$CORPUS
GEN_T=600; PREP_T=900; CAP=12000000
# The binaries are copied out of the worktree into $BINS, and a copied tlapm does
# not find the standard library from there.  It never showed because the three
# synthetic corpora EXTEND nothing at all: the first corpus in this campaign that
# needs FiniteSets came back rc=3 on all eighteen points, in forty seconds, which
# reads exactly like a fast run if the return code is not looked at.
LIB=${TLAPM_LIB:-"$(git rev-parse --show-toplevel)/_build/default/library"}
[ -d "$LIB" ] || { echo "no standard library at $LIB -- set TLAPM_LIB" >&2; exit 2; }
mkdir -p $BINS

SMALL="tiny:$P/Synth_L5_S3_D4_C2.tla synth100:$P/Synth_L100_S5_D50_C3.tla synth300:$P/Synth_L300_S5_D50_C3.tla"
LARGE="ffi:$P/abstractgrpc/FfiGrpcTheorems_proofs.tla mono:$P/oom_repro/timer_wheel_l1_mono.tla"
# The one corpus on these curves that lives in the repository.  It is a
# refinement stack, not a flat synthetic file: preparation on the base commit
# costs 80 s and 1.6 GB for a 3,239-line proof, so it reaches the regime the
# two private corpora are here for -- and unlike them it can be published, run
# and disputed by anyone.  Measured at every point, not just the PR endpoints,
# because it is cheap enough: the whole 18-point pass is minutes.
PUBLIC="idemo:$(git rev-parse --show-toplevel)/doc/perf/short/instance_demo/L2Proofs.tla"

# p00 = main; p01..p16 = the short branch in order; p00b re-measures main at the end.
ALL="p00:4600b24 $(i=0; for s in $(git rev-list --reverse main..tlapm-perf-short); do i=$((i+1)); printf 'p%02d:%s ' $i $s; done) p00b:4600b24"
# PR endpoints, the points the large corpora are measured at
ENDS="p00:4600b24 p05 p06 p07 p09 p11 p14 p15 p16 p17 p00b:4600b24"
ENDPOINTS=""
for e in $ENDS; do
  case $e in *:*) ENDPOINTS="$ENDPOINTS $e";;
    *) for a in $ALL; do [ "${a%%:*}" = "$e" ] && ENDPOINTS="$ENDPOINTS $a"; done;;
  esac
done
REV=$(for p in $ENDPOINTS; do echo $p; done | tac | tr '\n' ' ')

[ -f $OUT ] || echo "phase,boot,point,sha,corpus,gen_ms,gen_rc,prep_ms,prep_rc,peak_kb" > $OUT

binfor () {  # $1 point $2 sha -> path, building once and caching
  local n=$1 sha=$2
  if [ ! -x $BINS/$n.exe ]; then
    git -C $W checkout -q --detach $sha || return 1
    ( cd $W && dune build src 2>$S/sb_$n.log ) || return 1
    cp $W/_build/default/src/tlapm.exe $BINS/$n.exe || return 1
  fi
  echo $BINS/$n.exe
}

measure () {  # $1 phase $2 gen|prep|both $3 points  $4.. corpora
  local ph=$1 met=$2 pts=$3; shift 3; local corpora="$*"
  for p in $pts; do
    n=${p%%:*}; sha=${p##*:}
    todo=0
    for cp in $corpora; do grep -q "^$ph,$BOOT,$n,$sha,${cp%%:*}," $OUT || todo=1; done
    [ $todo -eq 0 ] && continue
    b=$(binfor $n $sha) || { echo "$n: build failed" >&2; continue; }
    for cp in $corpora; do
      cn=${cp%%:*}; spec=${cp##*:}
      grep -q "^$ph,$BOOT,$n,$sha,$cn," $OUT && continue
      d=$(mktemp -d); gen=-2; grc=0; prep=-2; prc=0; peak=0
      if [ "$met" != prep ]; then
        t0=$(date +%s%N)
        ( cd $(dirname $spec) && timeout $GEN_T $b -I $LIB -N --nofp --cache-dir $d/g $spec ) >/dev/null 2>&1; grc=$?
        gen=$(( ($(date +%s%N)-t0)/1000000 ))
      fi
      if [ "$met" != gen ]; then
        t0=$(date +%s%N)
        ( ulimit -v $CAP; cd $(dirname $spec) && timeout $PREP_T /usr/bin/time -f "%M" -o $d/r \
            $b -I $LIB --noproving --nofp --cache-dir $d/p $spec ) >/dev/null 2>&1; prc=$?
        prep=$(( ($(date +%s%N)-t0)/1000000 ))
        peak=$(tail -1 $d/r 2>/dev/null); case "${peak:-}" in ''|*[!0-9]*) peak=0;; esac
      fi
      rm -rf $d
      echo "$ph,$BOOT,$n,$sha,$cn,$gen,$grc,$prep,$prc,$peak" >> $OUT
      echo "  [$ph] $n $cn gen=${gen}(rc$grc) prep=${prep}(rc$prc) peak=${peak}kB"
    done
  done
  echo "PHASE_${ph}_DONE"
}

# PHASES selects which of them to run, so one phase can be measured without
# dragging the others along.  Without it, adding a corpus meant re-running the
# two private specifications as well -- hours of prepare-until-the-cap on a
# machine that was only wanted for twelve minutes of the new one.
PHASES=${PHASES:-"A P B0 B1"}
want () { case " $PHASES " in *" $1 "*) return 0;; *) return 1;; esac; }

want A  && measure A  both "$ALL"       $SMALL
want P  && measure P  both "$ALL"       $PUBLIC
want B0 && measure B0 gen  "$ENDPOINTS" $LARGE
want B1 && measure B1 prep "$REV"       $LARGE
echo SHORT_SWEEP_DONE
