#!/usr/bin/env bash
# Where the time goes, from the stock clocks.
#
# tlapm has always had --timing; what it did not have was clocks that add up.
# Generation, fingerprint computation and fingerprint saving were never started,
# so their cost fell into "other" and the table said nothing.  The first three
# commits of this series fix that, which is why this runs at p03: the earliest
# point where the tool tells the truth about itself, and otherwise the base
# commit's behaviour -- p01 to p03 are inert unless --timing is passed.
#
# Public corpora only, and no probe: a reader with the branch and the repository
# reproduces this table with one stock flag.  The finer split inside the
# per-obligation loop needs instrumentation this branch deliberately does not
# carry; doc/perf/ANALYSIS.md has it, from a separate campaign.
set -u
S=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
R=$(git rev-parse --show-toplevel)
BINS=$S/shortbin; OUT=$S/short_phases.csv; NRUN=${NRUN:-3}
LIB=${TLAPM_LIB:-"$R/_build/default/library"}
PT=${PT:-p03}
export PATH=/opt/isabelle/bin:$PATH
BOOT=$(awk '/btime/{print $2}' /proc/stat)
sha=$(grep "^$PT:" $S/short_points.txt | cut -d: -f2)
[ -x $BINS/$PT.exe ] || { echo "no $PT binary"; exit 1; }
[ -f $OUT ] || echo "boot,point,sha,corpus,run,clock,seconds" > $OUT
CORPORA=${CORPORA:-"idemo:$R/doc/perf/short/instance_demo/L2Proofs.tla \
synth300:$R/_perf/Synth_L300_S5_D50_C3.tla"}
for entry in $CORPORA; do
  cp=${entry%%:*}; spec=${entry#*:}
  for r in $(seq 1 $NRUN); do
    grep -q "^$BOOT,$PT,$sha,$cp,$r," $OUT && continue
    d=$(mktemp -d); cp -r $(dirname $spec)/*.tla $d/ 2>/dev/null
    ( cd $d && timeout 1800 $BINS/$PT.exe --noproving --nofp --timing -I $LIB -I . \
        --cache-dir $d/c $(basename $spec) ) > $d/o 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then
      echo "  [phases] $cp run$r BROKEN rc=$rc -- no rows"
      grep -aviE '^\(\*|^$|^@!!' $d/o | head -2 | sed 's/^/    /'
      rm -rf $d; continue
    fi
    n=$(sed -n 's/^(\* *\([a-z_]*\) *| *\([0-9][0-9.]*\).*$/\1,\2/p' $d/o | tee $d/cl | wc -l)
    [ "$n" -lt 5 ] && { echo "  [phases] $cp run$r: no clock table in the output"; rm -rf $d; continue; }
    while IFS=, read -r clock secs; do
      echo "$BOOT,$PT,$sha,$cp,$r,$clock,$secs" >> $OUT
    done < $d/cl
    echo "  [phases] $cp run$r total $(awk -F, '$1=="total"{print $2}' $d/cl)s over $n clocks"
    rm -rf $d
  done
done
echo PHASES_DONE
