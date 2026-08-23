#!/usr/bin/env bash
# keystroke -> diagnostics on every corpus, not just the refinement chain.
#
# The figure had one series because the harness had one spec and one line number
# baked in.  Both are arguments now, and the CSV carries the corpus, so the chart
# can show the metric the way the other four charts show theirs: five corpora,
# the small one as the control that must not get slower.
#
# The edit line is chosen the same way for every corpus -- the middle proof step
# that carries a justification -- so the edit lands inside a proof body rather
# than in a statement, and no corpus gets a systematically easier edit than another.
set -u
S=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
W=$S/shortwt; OUT=$S/short_keystroke.csv
NRUN=${NRUN:-3}
export PATH=/opt/isabelle/bin:$PATH
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
ALL=$(tr '\n' ' ' < $S/short_points.txt)
PTS=${PTS:-$(tr "\n" " " < $S/short_points.txt | sed "s|:[0-9a-f]*||g")}
[ -f $OUT ] || echo "boot,corpus,point,sha,kind,idx,seconds,n" > $OUT
# corpus : spec : edit line
C=${CORPUS:-"$(git rev-parse --show-toplevel)/_perf"}
# corpus:spec:line -- one workspace directory per spec, since the server opens a
# directory; the line is the middle proof step carrying a justification
CORPORA=${CORPORA:-"tiny:$S/ksw_tiny/Synth_L5_S3_D4_C2.tla:20 \
synth100:$S/ksw_synth100/Synth_L100_S5_D50_C3.tla:405 \
synth300:$S/ksw_synth300/Synth_L300_S5_D50_C3.tla:1105"}
for spec in $CORPORA; do
  CP=${spec%%:*}; rest=${spec#*:}; SPEC=${rest%%:*}; LINE=${rest##*:}
  echo "=== keystroke: $CP ($(basename $SPEC) line $LINE) ==="
  for q in $PTS; do
    for p in $ALL; do [ "${p%%:*}" = "$q" ] && { n=$q; sha=${p##*:}; }; done
    grep -q ",$CP,$n,$sha,edit,$((NRUN-1)),.*,$NRUN$" $OUT && { echo "  skip $n"; continue; }
    git -C $W checkout -q --detach $sha || continue
    ( cd $W && dune build lsp src 2>$S/ks_$n.log ) || { echo "  $n BUILD FAILED"; continue; }
    bd=$W/_build/default/lib/tlapm/backends; mkdir -p $bd; rm -rf $bd/Isabelle 2>/dev/null
    ln -s /opt/isabelle $bd/Isabelle 2>/dev/null
    out=$(timeout 2400 python3 $(dirname "$0")/lsp_keystroke_client.py $W/_build/default/lsp/bin/tlapm_lsp.exe \
            $SPEC $LINE $NRUN 2>/dev/null)
    o=$(echo "$out" | sed -n 's/^open->markers: \([0-9.]*\)s/\1/p')
    [ -n "$o" ] && echo "$BOOT,$CP,$n,$sha,open,0,$o,$NRUN" >> $OUT
    echo "$out" | sed -n 's/^edit\([0-9]*\)->diag: \([0-9.]*\)s.*/\1 \2/p' | while read i v; do
      echo "$BOOT,$CP,$n,$sha,edit,$i,$v,$NRUN" >> $OUT
    done
    e=$(echo "$out" | sed -n 's/^edit[0-9]*->diag: \([0-9.]*\)s.*/\1/p' | tr '\n' ' ')
    [ -z "$e" ] && e="(none -- see $S/ks_$n.log)"
    echo "  [ks/$CP] $n open=${o}s edits=$e"
  done
done
echo KS_MULTI_DONE
