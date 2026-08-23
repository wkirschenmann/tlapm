#!/usr/bin/env bash
# Regenerate doc/perf/short/data/instance_demo.csv.
#
# The four Ladder modules differ in exactly one thing -- how many times they
# INSTANCE L1Theorems -- and each has one obligation, so the per-obligation
# context is a direct reading of what one INSTANCE copies in.
#
# Run this on an idle machine: the counts are deterministic, but the wall times
# are not, and this must never share cores with a timing campaign.
#
# Requires the TLAPM_TRACE_DEFS probe, which lives on the documentation branch,
# not on the proposal branch being measured.
set -eu
R=$(cd "$(dirname "$0")/../../../.." && pwd)
D=$R/doc/perf/short/instance_demo
T=${TLAPM:-$R/_build/default/src/tlapm.exe}
LIB=${TLAPM_LIB:-$R/_build/default/library}
OUT=$R/doc/perf/short/instance_demo.csv
echo "module,instances,obligations,defn_per_obl,hyps_per_obl,frag_j1,frag_j1l0" > $OUT
cd $D
for n in 1 2 3 4; do
  rm -rf $D/.tlacache
  o=$(TLAPM_TRACE_DEFS="J1!,J1!L0!" $T -I $LIB -I $D --noproving --nofp Ladder$n.tla 2>&1 \
        | grep -A1 "module=Ladder$n ")
  eval $(echo "$o" | sed -n 's/.*obligations=\([0-9]*\) total_ctx_hyps=\([0-9]*\).*Defn=\([0-9]*\).*/nob=\1;tot=\2;dfn=\3/p')
  eval $(echo "$o" | sed -n 's/.*J1!=\([0-9]*\)  J1!L0!=\([0-9]*\).*/a=\1;b=\2/p')
  echo "Ladder$n,$n,$nob,$((dfn/nob)),$((tot/nob)),$((a/nob)),$((b/nob))" >> $OUT
done
cat $OUT
