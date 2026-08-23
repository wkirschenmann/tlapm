#!/usr/bin/env bash
# Regenerate doc/perf/short/instance_demo.csv -- every count and timing the
# document quotes about instance_demo/.
#
# Two halves.  The Ladder modules differ in exactly one thing, how many times
# they INSTANCE the same theorems module, and each has one obligation, so the
# per-obligation context is a direct reading of what one INSTANCE copies in.
# L2Proofs.tla is the level-2 proof: what those copies cost once a proof cites
# them, plus the proof's own totals.
#
# Run this on an idle machine.  The counts are deterministic; the four timings
# are not, and this must never share cores with a timing campaign.
#
# Requires the TLAPM_TRACE_DEFS probe, which lives on the documentation branch,
# not on the proposal branch being measured.
set -eu
R=$(cd "$(dirname "$0")/../../../.." && pwd)
D=$R/doc/perf/short/instance_demo
H=$R/doc/perf/short/harness
T=${TLAPM:-$R/_build/default/src/tlapm.exe}
LIB=${TLAPM_LIB:-$R/_build/default/library}
OUT=$R/doc/perf/short/instance_demo.csv
LEMMAS=${LEMMAS:-40}
STACK="L0State L0 L0Theorems L1State L1 L1Theorems L2"

python3 $H/gen_l2proofs.py $LEMMAS
cd $D
probe () {  # $1 = module, $2 = fragment list -> "obl tot max defn frag1 frag2"
  rm -rf $D/.tlacache
  TLAPM_TRACE_DEFS="$2" $T -I $LIB -I . --noproving --nofp "$1.tla" 2>&1 \
    | grep -A1 "module=$1 " \
    | sed -n 's/.*obligations=\([0-9]*\) total_ctx_hyps=\([0-9]*\) max_ctx_hyps=\([0-9]*\) Defn=\([0-9]*\).*/\1 \2 \3 \4/p;s/.*: [^=]*=\([0-9]*\)  [^=]*=\([0-9]*\).*/\1 \2/p' \
    | tr '\n' ' '
}
ms () { local t0=$(date +%s%N); rm -rf $D/.tlacache; "$@" >/dev/null 2>&1 || true
        echo $(( ($(date +%s%N)-t0)/1000000 )); }

echo "kind,key,value" > $OUT
for n in 1 2 3 4; do
  set -- $(probe Ladder$n "J1!,J1!L0!")
  echo "ladder,$n,$(( $2 / $1 ))"      >> $OUT
  echo "ladder_defn_tmp,$n,$(( $4 / $1 ))" >> $OUT
  [ $n = 1 ] && { echo "ladder_frag_one_hop,1,$(( $5 / $1 ))" >> $OUT
                  echo "ladder_frag_two_hop,1,$(( $6 / $1 ))" >> $OUT; }
done
sed -i 's/^ladder_defn_tmp,/ladder_defn,/' $OUT

set -- $(probe L2Proofs "L1!,L1!L0!")
OBL=$1
{ echo "proofs,lemmas,$LEMMAS"
  echo "proofs,lines,$(wc -l < $D/L2Proofs.tla)"
  echo "proofs,obligations,$OBL"
  echo "proofs,depth4_leaves,$(grep -c '^ *<4>1. L1!IndInv =>' $D/L2Proofs.tla)"
  echo "proofs,depth5_leaves,$(grep -c '^ *<5>1. L1!L0!IndInv' $D/L2Proofs.tla)"
  echo "proofs,total_ctx_hyps,$2"
  echo "proofs,max_ctx_hyps,$3"
  echo "proofs,defn_total,$4"
  echo "proofs,frag_one_hop,$5"
  echo "proofs,frag_two_hop,$6"
  echo "proofs,cite_one_hop,$(grep -oE 'L1!Q[0-9]+Holds|L1!RefinesL0|L1!IndInvImpliesInvariant|L1!IndInvPreserved' $D/L2Proofs.tla | wc -l)"
  echo "proofs,cite_two_hop,$(grep -oE 'L1!L0!P[0-9]+Holds' $D/L2Proofs.tla | wc -l)"
  echo "proofs,stack_lines,$(cd $D && cat $(for m in $STACK; do echo $m.tla; done) | wc -l)"
} >> $OUT

# The proving run doubles as the corpus's own gate: the document says every
# obligation is proved, so the counts come out of the run that proves them.
PROVE=$(ms timeout 1800 $T -I $LIB -I . --toolbox 0 0 --threads 4 L2Proofs.tla)
rm -rf $D/.tlacache
$T -I $LIB -I . --toolbox 0 0 --threads 4 L2Proofs.tla > $D/prove.log 2>&1 || true
{ echo "proofs,trivial,$(grep -cE '^@!!status:trivial' $D/prove.log)"
  echo "proofs,smt,$(grep -cE '^@!!prover:smt' $D/prove.log)"
  echo "proofs,zenon,$(grep -cE '^@!!prover:zenon' $D/prove.log)"
  echo "proofs,gen_ms,$(ms $T -I $LIB -I . -N --nofp L2Proofs.tla)"
  echo "proofs,prep_ms,$(ms $T -I $LIB -I . --noproving --nofp L2Proofs.tla)"
  echo "proofs,prove_ms,$PROVE"
} >> $OUT
rm -rf $D/.tlacache
PK=$( { /usr/bin/time -f "%M" $T -I $LIB -I . --noproving --nofp L2Proofs.tla >/dev/null; } 2>&1 | tail -1)
echo "proofs,peak_kb,$PK" >> $OUT
fail=$(grep -cE '^@!!status:failed' $D/prove.log || true)
rm -f $D/prove.log; rm -rf $D/.tlacache
[ "$fail" = 0 ] || { echo "REFUSING: $fail obligations failed -- the document claims none do"; exit 1; }
echo "--- $OUT"; cat $OUT
