#!/usr/bin/env bash
# Iteration latency: warm prover, full fingerprint cache, one edit.
# Synthetic corpus (all 17 points) and the private refinement chain (13 points).
set -u
# Set WORK to a scratch directory (worktree, cached binaries, CSVs) and
# CORPUS to the directory holding the .tla corpora.  Both default to values
# that suit a checkout of this repository.
WORK=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
CORPUS=${CORPUS:-"$(git rev-parse --show-toplevel)/_perf"}
mkdir -p "$WORK"
S=$WORK
W=$S/shortwt; BINS=$S/shortbin; OUT=$S/short_iterlat.csv
export PATH=/opt/isabelle/bin:$PATH
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
mkdir -p $BINS
ALL="p00:$(git rev-parse main) $(i=0; for s in $(git rev-list --reverse main..tlapm-perf-short); do i=$((i+1)); printf 'p%02d:%s ' $i $s; done)"
CHAIN_PTS="p00 p05 p06 p07 p08 p09 p10 p11 p12 p13 p14 p15 p16 p17"
read LO HI NOBL < $S/iterchain/range.txt
[ -f $OUT ] || echo "boot,corpus,point,sha,run,ms,rc,proved,failed,trivial" > $OUT

binfor () { local n=$1 sha=$2
  if [ ! -x $BINS/$n.exe ]; then
    git -C $W checkout -q --detach $sha || return 1
    ( cd $W && dune build src 2>$S/il_$n.log ) || return 1
    cp $W/_build/default/src/tlapm.exe $BINS/$n.exe || return 1
  fi
  bd=$W/_build/default/lib/tlapm/backends; mkdir -p $bd; rm -rf $bd/Isabelle 2>/dev/null
  ln -s /opt/isabelle $bd/Isabelle 2>/dev/null
  echo $BINS/$n.exe; }

# --- synthetic, 1800 obligations, 3 runs, 900 s ceiling
for p in $ALL; do
  n=${p%%:*}; sha=${p##*:}
  grep -q ",synth300,$n,$sha,3," $OUT && continue
  b=$(binfor $n $sha) || { echo "$n build failed"; continue; }
  for r in 1 2 3; do
    grep -q ",synth300,$n,$sha,$r," $OUT && continue
    d=$(mktemp -d); cp -r $S/iter/cache $d/c; cp $S/iter/edited.tla $d/Synth_L300_S5_D50_C3.tla
    cd $d; t0=$(date +%s%N)
    timeout 900 $b --toolbox 0 0 --threads 4 --cache-dir $d/c Synth_L300_S5_D50_C3.tla > $d/o 2>&1; rc=$?
    ms=$(( ($(date +%s%N)-t0)/1000000 ))
    pv=$(grep -cE '^@!!status:proved' $d/o||true); fl=$(grep -cE '^@!!status:failed' $d/o||true); tv=$(grep -cE '^@!!status:trivial' $d/o||true)
    cd $W; rm -rf $d
    echo "$BOOT,synth300,$n,$sha,$r,$ms,$rc,$pv,$fl,$tv" >> $OUT
    echo "  [iter synth300] $n run$r ${ms}ms rc=$rc"
    [ $rc -eq 124 ] && break
  done
done
echo ITER_SYNTH_DONE

# --- private refinement chain, 3773 obligations in the measured span, 2 runs, 1800 s ceiling
# The span is not failure-free -- 641 of the 10031 obligations in the cold pass are
# discharged by no prover, so every warm run re-attempts them.  That is a constant
# added to every point of the series, identical across commits, so it does not touch
# a ratio; it does inflate the absolute figure, and an earlier comment here claimed
# the opposite.
for q in $CHAIN_PTS; do
  for p in $ALL; do [ "${p%%:*}" = "$q" ] && { n=$q; sha=${p##*:}; }; done
  grep -q ",chain,$n,$sha,2," $OUT && continue
  grep -qE ",chain,$n,$sha,1,[0-9]+,124," $OUT && continue
  b=$(binfor $n $sha) || { echo "$n build failed"; continue; }
  for r in 1 2; do
    grep -q ",chain,$n,$sha,$r," $OUT && continue
    d=$(mktemp -d); cp -r $S/iterchain/cache $d/c
    for f in $S/iterchain/*.tla; do case $(basename $f) in orig.tla|edited.tla) ;; *) cp $f $d/;; esac; done
    cp $S/iterchain/edited.tla $d/FfiGrpcTheorems_proofs.tla
    cd $d; t0=$(date +%s%N)
    timeout 900 $b --toolbox $LO $HI --threads 4 --cache-dir $d/c FfiGrpcTheorems_proofs.tla > $d/o 2>&1; rc=$?
    ms=$(( ($(date +%s%N)-t0)/1000000 ))
    pv=$(grep -cE '^@!!status:proved' $d/o||true); fl=$(grep -cE '^@!!status:failed' $d/o||true); tv=$(grep -cE '^@!!status:trivial' $d/o||true)
    cd $W; rm -rf $d
    echo "$BOOT,chain,$n,$sha,$r,$ms,$rc,$pv,$fl,$tv" >> $OUT
    echo "  [iter chain] $n run$r ${ms}ms rc=$rc proved=$pv failed=$fl trivial=$tv"
    [ $rc -eq 124 ] && break
  done
done
echo ITER_CHAIN_DONE
