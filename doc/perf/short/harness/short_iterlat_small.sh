#!/usr/bin/env bash
# Iteration latency on corpora the main harness never covered.
#
# short_iterlat.sh has two loops with the corpus, the fixture directory and the
# ceiling baked into each.  That is fine for the two it was written for, and it
# produced published data, so it is left alone.  What it left out is the small
# end: the 20-obligation control -- the corpus whose entire job is to show that
# small proofs do not get slower -- had no line on the one metric a user feels
# most directly, and neither did the 600-obligation one.
#
# This is the same measurement, generic over the corpus.  Give it quadruples of
# corpus:spec:edit-line:extra-definition; it builds the warm-cache fixture once
# per corpus and replays one edit against every commit's binary.
#
# The fixture discipline matters and is the same as the monolith's: the cache is
# proved ONCE, with one binary, and a fresh copy is handed to every run.  It is
# not a per-commit artefact -- confusing "we cannot warm a cache at this commit"
# with "we cannot warm a cache" is a mistake already made once in this campaign.
#
# THE EDIT.  It lands on a proof step's justification, never on a statement, so
# no corpus gets a systematically easier edit than another, and it names one
# extra DEFINITION -- never a backend.  Naming a backend was the first attempt
# and it is wrong here: `BY Zenon` needs TLAPS in scope, and these synthetic
# corpora EXTEND nothing, so every run died with `Operator "Zenon" not found`
# in 133 ms and exit 3.  A 133 ms failure is indistinguishable from a fast run
# unless the exit status is read, and 108 such rows were written before it was.
# Hence both guards below: the edit is preflighted with the tip's binary and the
# corpus is refused if that run does not exit 0, and no row is written for a run
# whose status is neither success nor the clock.
set -u
S=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
W=$S/shortwt; BINS=$S/shortbin; OUT=$S/short_iterlat.csv
NRUN=${NRUN:-3}; CEIL=${CEIL:-900}
export PATH=/opt/isabelle/bin:$PATH
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
C=${CORPUS:-"$(git rev-parse --show-toplevel)/_perf"}
ALL="p00:$(git rev-parse main) $(i=0; for s in $(git rev-list --reverse main..tlapm-perf-short); do i=$((i+1)); printf 'p%02d:%s ' $i $s; done)"
CORPORA=${CORPORA:-"tiny:$C/Synth_L5_S3_D4_C2.tla:20:Def_0 \
synth100:$C/Synth_L100_S5_D50_C3.tla:405:Def_3"}
[ -f $OUT ] || echo "boot,corpus,point,sha,run,ms,rc,proved,failed,trivial" > $OUT

binfor () { local n=$1 sha=$2
  if [ ! -x $BINS/$n.exe ]; then
    git -C $W checkout -q --detach $sha || return 1
    ( cd $W && dune build src 2>$S/ils_$n.log ) || return 1
    cp $W/_build/default/src/tlapm.exe $BINS/$n.exe || return 1
  fi
  bd=$W/_build/default/lib/tlapm/backends; mkdir -p $bd; rm -rf $bd/Isabelle 2>/dev/null
  ln -s /opt/isabelle $bd/Isabelle 2>/dev/null
  echo $BINS/$n.exe; }

# the tip's binary proves the fixture: one binary, one cache, every commit replays it
TIP=$(binfor p17 "$(git rev-list -1 tlapm-perf-short)") || { echo "no tip binary"; exit 1; }

for entry in $CORPORA; do
  IFS=: read -r CP SPEC LINE EXTRA <<< "$entry"
  F=$S/iters_$CP; BASE=$(basename $SPEC)
  if [ ! -d $F/cache ]; then
    echo "=== $CP: proving $BASE once to warm the cache ==="
    rm -rf $F; mkdir -p $F; cp $SPEC $F/orig.tla
    ( cd $F && cp orig.tla $BASE && timeout 3600 $TIP --toolbox 0 0 --threads 4 \
        --cache-dir $F/cache $BASE ) > $F/cold.log 2>&1
    rc=$?
    echo "  cold rc=$rc proved=$(grep -cE '^@!!status:proved' $F/cold.log) \
failed=$(grep -cE '^@!!status:failed' $F/cold.log)"
    [ $rc -ne 0 ] && { echo "COLD_FAILED on $CP -- no fixture, so no line"; continue; }
  fi
  # The edit names one extra DEFINITION on the chosen step's justification, and
  # nothing else.  Three shapes occur across these corpora and each needs its own
  # rewrite to stay valid TLA+:
  #
  #   ... BY f DEF X   ->  ... BY f DEF X, EXTRA     (extend the DEF list)
  #   ... OBVIOUS      ->  ... BY DEF EXTRA
  #   ... BY f         ->  ... BY f DEF EXTRA        (facts precede DEF)
  #
  # Whatever the shape, only the justification changes: the statement, and so the
  # obligation's goal, is untouched, and every other fingerprint stays valid.
  awk -v n="$LINE" -v x="$EXTRA" 'NR==n {
      if ($0 ~ / DEF /)        sub(/$/, ", " x)
      else if ($0 ~ /OBVIOUS/) sub(/OBVIOUS/, "BY DEF " x)
      else if ($0 ~ /BY /)     sub(/$/, " DEF " x)
    } {print}' $F/orig.tla > $F/edited.tla
  if cmp -s $F/orig.tla $F/edited.tla; then
    echo "EDIT_NOOP on $CP at line $LINE -- refusing, this would measure the cache"
    continue
  fi
  # Preflight: the edited file must still be something tlapm can check.  Without
  # this the loop happily records eighteen commits' worth of parse failures.
  d=$(mktemp -d); cp -r $F/cache $d/c; cp $F/edited.tla $d/$BASE
  ( cd $d && timeout $CEIL $TIP --toolbox 0 0 --threads 4 --cache-dir $d/c $BASE ) \
      > $d/pre 2>&1
  prc=$?
  if [ $prc -ne 0 ]; then
    echo "EDIT_INVALID on $CP: the edited file exits $prc --"
    grep -aviE '^\(\*|^$|^@!!' $d/pre | head -3 | sed 's/^/    /'
    rm -rf $d; continue
  fi
  rm -rf $d
  echo "=== $CP: edit at line $LINE (+DEF $EXTRA) preflights clean ==="
  for p in $ALL; do
    n=${p%%:*}; sha=${p##*:}
    [ "$(grep -c "^$BOOT,$CP,$n,$sha," $OUT 2>/dev/null)" -ge "$NRUN" ] && continue
    b=$(binfor $n $sha) || { echo "  $n build failed"; continue; }
    for r in $(seq 1 $NRUN); do
      grep -q "^$BOOT,$CP,$n,$sha,$r," $OUT && continue
      d=$(mktemp -d); cp -r $F/cache $d/c; cp $F/edited.tla $d/$BASE
      cd $d; t0=$(date +%s%N)
      timeout $CEIL $b --toolbox 0 0 --threads 4 --cache-dir $d/c $BASE > $d/o 2>&1; rc=$?
      ms=$(( ($(date +%s%N)-t0)/1000000 ))
      pv=$(grep -cE '^@!!status:proved' $d/o||true)
      fl=$(grep -cE '^@!!status:failed' $d/o||true)
      tv=$(grep -cE '^@!!status:trivial' $d/o||true)
      cd $S; rm -rf $d
      case $rc in
        0|124) echo "$BOOT,$CP,$n,$sha,$r,$ms,$rc,$pv,$fl,$tv" >> $OUT
               echo "  [iter $CP] $n run$r ${ms}ms rc=$rc obl=$((pv+tv))" ;;
        *)     echo "  [iter $CP] $n run$r BROKEN rc=$rc after ${ms}ms -- no row" ;;
      esac
      [ $rc -eq 124 ] && break
    done
  done
done
echo ITER_SMALL_DONE
